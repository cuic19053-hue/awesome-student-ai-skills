"""Server-owned registration cutoff and permanent paid-account billing policy."""

from datetime import datetime
from typing import Any

# User-approved boundary: 2026-10-18 16:51:47 Asia/Shanghai.
# Keep this fixed and identical to the database migration; never use deployment time.
TRIAL_REGISTRATION_CUTOFF = "2026-10-18T08:51:47+00:00"
FREE_CHAT_LIMIT = 3


def normalize_trial_wallet(
    wallet: dict[str, Any],
    *,
    registered_at: str | None = None,
    require_registration: bool = False,
) -> dict[str, Any]:
    result = dict(wallet)
    try:
        registration = registered_at if require_registration else registered_at or wallet.get("created_at")
        created = datetime.fromisoformat(str(registration).replace("Z", "+00:00"))
        eligible = (
            created.tzinfo is not None
            and created > datetime.fromisoformat(TRIAL_REGISTRATION_CUTOFF)
            and all(
                int(wallet.get(key, 0) or 0) == 0
                for key in ("balance_micro_cny", "total_credited_micro_cny", "total_spent_micro_cny")
            )
        )
        remaining = min(FREE_CHAT_LIMIT, max(0, int(wallet.get("free_chat_count", 0) or 0)))
    except (ValueError, TypeError, OverflowError):
        eligible, remaining = False, 0
    result["trial_eligible"] = eligible
    result["free_chat_count"] = remaining if eligible else 0
    return result
