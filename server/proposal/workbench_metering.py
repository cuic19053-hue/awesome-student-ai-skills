from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
import uuid
from typing import Any

from .wopally_usage import UsageUnavailable, WopallyUsage
from .official_pricing import PRICE_VERSION
from . import observability as obs

logger = logging.getLogger("proposal_agent.metering")

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER_SECRET = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
_OPENAI_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")


def _safe_interaction_text(value: str) -> str:
    text = str(value or "")
    text = _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", text)
    text = _BEARER_SECRET.sub("Bearer [REDACTED]", text)
    return _OPENAI_SECRET.sub("[REDACTED]", text)[:200000]

class WorkbenchMeter:
    """Reserve each upstream request independently, including tool-loop requests."""

    # Each request records its price version in the ID so an old in-flight
    # request still settles at the price in effect when it was reserved.
    TEXT_HOLD_MICRO_CNY = 200_000

    def __init__(self, store: Any, user_id: str, api_key_id: int, project_id: str = ""):
        self.store = store
        self.user_id = user_id
        self.api_key_id = api_key_id
        self.project_id = project_id
        self.background_reconciliation = (
            os.environ.get("BILLING_BACKGROUND_RECONCILIATION", "").lower() == "true"
        )
        self.usage = WopallyUsage(
            timeout=2 if self.background_reconciliation else 8,
            max_pages=1 if self.background_reconciliation else 5,
        )

    def reserve(
        self, model: str, hold_micro_cny: int | None = None, *, input_text: str = ""
    ) -> str:
        request_id = f"{PRICE_VERSION}_{uuid.uuid4().hex}"
        self.store.reserve_workbench_usage(
            self.user_id, request_id, model,
            hold_micro_cny or self.TEXT_HOLD_MICRO_CNY, self.api_key_id,
        )
        if self.project_id and hasattr(self.store, "record_workbench_interaction"):
            try:
                self.store.record_workbench_interaction(
                    self.user_id, self.project_id, request_id, model,
                    input_text=_safe_interaction_text(input_text), status="started",
                )
            except Exception:
                try:
                    self.store.refund_workbench_usage(request_id, "interaction_log_unavailable")
                except Exception:
                    logger.warning("Could not refund reservation after interaction logging failed; request_id=%s", request_id)
                raise RuntimeError("本次对话无法安全保存，模型请求未发送。") from None
        obs.bind(owner_id=self.user_id, project_id=self.project_id)
        obs.emit("billing.reserved", stage="reserve_confirmed", status="accepted",
                 usage_request_id=request_id, metadata={"billable": True})
        return request_id

    def complete_interaction(self, request_id: str, model: str, output_text: str) -> None:
        if self.project_id and hasattr(self.store, "record_workbench_interaction"):
            try:
                self.store.record_workbench_interaction(
                    self.user_id, self.project_id, request_id, model,
                    output_text=_safe_interaction_text(output_text), status="completed",
                )
            except Exception:
                logger.warning("Model interaction output could not be saved; request_id=%s", request_id)

    def fail_interaction(
        self, request_id: str, model: str, error_code: str, *, status: str = "failed"
    ) -> None:
        if self.project_id and hasattr(self.store, "record_workbench_interaction"):
            try:
                self.store.record_workbench_interaction(
                    self.user_id, self.project_id, request_id, model,
                    status=status, error_code=error_code,
                )
            except Exception:
                logger.warning("Model interaction status could not be saved; request_id=%s", request_id)

    def settle(self, request_id: str, model: str) -> dict[str, Any] | None:
        found = None
        attempts = 1 if self.background_reconciliation else 3
        for attempt in range(attempts):
            try:
                found = self.usage.find(request_id, self.api_key_id, model)
            except UsageUnavailable:
                logger.warning("Provider usage delayed or unavailable; request_id=%s", request_id)
                obs.emit("billing.reconciliation_pending", stage="provider_usage", status="pending",
                         level="warning", usage_request_id=request_id, code="BILLING_RECONCILIATION_PENDING")
                return None  # Keep the hold until an authoritative record is recovered.
            if found is not None:
                break
            if attempt < attempts - 1:
                time.sleep(0.35)
        if found is None:
            obs.emit("billing.reconciliation_pending", stage="provider_usage", status="pending",
                     level="warning", usage_request_id=request_id, code="BILLING_RECONCILIATION_PENDING")
            return None
        amount, provider_id = found
        try:
            result = self.store.settle_workbench_usage(request_id, amount, provider_id)
            if not isinstance(result, dict) or result.get("status") not in {"settled", "needs_review"}:
                raise RuntimeError("Invalid settlement response")
        except (RuntimeError, ValueError, PermissionError, sqlite3.Error):
            # The upstream answer already exists. A ledger outage (including
            # commit-then-timeout) must not discard it or replay paid inference.
            # The original durable reservation is retried by the worker.
            logger.warning("Ledger settlement deferred; request_id=%s", request_id)
            obs.emit("billing.reconciliation_pending", stage="ledger_confirmation",
                     status="pending", level="warning", usage_request_id=request_id,
                     code="BILLING_LEDGER_UNAVAILABLE")
            return None
        if result.get("status") == "needs_review":
            logger.error("Provider charge exceeded reservation; request_id=%s", request_id)
        obs.emit("billing.settled", stage="ledger_confirmed",
                 status="pending" if result.get("status") == "needs_review" else "completed",
                 usage_request_id=request_id, metadata={"billable": True})
        return result

    def refund(self, request_id: str) -> None:
        self.store.refund_workbench_usage(request_id, "provider_failed")
        obs.emit("billing.refunded", stage="ledger_confirmed", usage_request_id=request_id)
