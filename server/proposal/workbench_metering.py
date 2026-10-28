from __future__ import annotations

import logging
import os
import sqlite3
import time
import uuid
from typing import Any

from .wopally_usage import UsageUnavailable, WopallyUsage
from .official_pricing import PRICE_VERSION
from . import observability as obs

logger = logging.getLogger("proposal_agent.metering")

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

    def reserve(self, model: str, hold_micro_cny: int | None = None) -> str:
        request_id = f"{PRICE_VERSION}_{uuid.uuid4().hex}"
        self.store.reserve_workbench_usage(
            self.user_id, request_id, model,
            hold_micro_cny or self.TEXT_HOLD_MICRO_CNY, self.api_key_id,
        )
        obs.bind(owner_id=self.user_id, project_id=self.project_id)
        obs.emit("billing.reserved", stage="reserve_confirmed", status="accepted",
                 usage_request_id=request_id, metadata={"billable": True})
        return request_id

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
