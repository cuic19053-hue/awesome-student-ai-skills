from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from .wopally_usage import UsageUnavailable, WopallyUsage

logger = logging.getLogger("proposal_agent.metering")


class WorkbenchMeter:
    """Reserve each upstream request independently, including tool-loop requests."""

    # A ¥0.5 balance card can cover one bounded request. The actual charge
    # (3x provider cost) is reconciled, and the unused portion is returned.
    # Actual charge is 3x the authoritative Wopally cost; unused hold is returned.
    TEXT_HOLD_MICRO_CNY = 500_000

    def __init__(self, store: Any, user_id: str, api_key_id: int, project_id: str = ""):
        self.store = store
        self.user_id = user_id
        self.api_key_id = api_key_id
        self.project_id = project_id
        self.usage = WopallyUsage()

    def reserve(self, model: str, hold_micro_cny: int | None = None) -> str:
        request_id = uuid.uuid4().hex
        self.store.reserve_workbench_usage(
            self.user_id, request_id, model,
            hold_micro_cny or self.TEXT_HOLD_MICRO_CNY, self.api_key_id,
        )
        return request_id

    def settle(self, request_id: str, model: str) -> dict[str, Any] | None:
        found = None
        for attempt in range(3):
            try:
                found = self.usage.find(request_id, self.api_key_id, model)
            except UsageUnavailable:
                logger.warning("Provider usage delayed or unavailable; request_id=%s", request_id)
                return None  # Keep the hold until an authoritative record is recovered.
            if found is not None:
                break
            if attempt < 2:
                time.sleep(0.35)
        if found is None:
            return None
        amount, provider_id = found
        result = self.store.settle_workbench_usage(request_id, amount, provider_id)
        if result.get("status") == "needs_review":
            logger.error("Provider charge exceeded reservation; request_id=%s", request_id)
        return result

    def refund(self, request_id: str) -> None:
        self.store.refund_workbench_usage(request_id, "provider_failed")
