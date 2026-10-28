"""Read-only, content-free inspection of one provider receipt for operators."""
from decimal import Decimal, InvalidOperation
import re

from .official_pricing import official_2x_charge, official_v1_charge
from .wopally_client import WopallyClient, WopallyUnavailable

REQUEST_ID = r"^(?:o2x1_|o90v1_|m12_)?[a-f0-9]{32}$"
NUMERIC_FIELDS = (
    "input_tokens", "output_tokens", "cache_read_tokens", "image_output_tokens",
    "image_input_tokens", "image_count", "input_cost", "output_cost",
    "cache_read_cost", "total_cost", "actual_cost",
)


def inspect_receipt(request_id: str, api_key_id: int, client=None):
    """Never invokes inference, changes balances, or returns prompts/credentials."""
    if not re.fullmatch(REQUEST_ID, request_id) or api_key_id <= 0:
        raise ValueError("Invalid receipt lookup")
    client = client or WopallyClient(timeout=8)
    matches = []
    for page in range(1, 6):
        data = client._request(
            f"/api/v1/usage?page={page}&page_size=100&api_key_id={api_key_id}"
        )
        rows = data if isinstance(data, list) else data.get(
            "items", data.get("records", data.get("list", []))
        )
        if not isinstance(rows, list):
            raise WopallyUnavailable("中转站用量格式无法识别")
        for row in rows:
            if isinstance(row, dict) and row.get("user_agent") == f"StardustWorkbench/{request_id}":
                matches.append(row)
        if len(rows) < 100:
            break
    if not matches:
        return {"status": "receipt_not_found", "pages_scanned": page}
    if len(matches) != 1:
        return {"status": "ambiguous_receipts", "match_count": len(matches)}
    row = matches[0]
    if row.get("api_key_id") != api_key_id:
        return {"status": "ownership_mismatch"}
    model = row.get("model")
    if model not in {"deepseek-v4-flash", "gpt-image-2"}:
        return {"status": "unsupported_model"}
    # Whitelist numeric fields only. Never return the arbitrary provider object.
    sample = {}
    for key in NUMERIC_FIELDS:
        if key not in row:
            continue
        value = row[key]
        try:
            number = Decimal(str(value))
            if not isinstance(value, bool) and number.is_finite() and 0 <= number <= 10**15:
                sample[key] = str(number)
        except (ValueError, InvalidOperation):
            pass
    result = {"model": model, "numeric_usage": sample}
    try:
        if request_id.startswith("o2x1_"):
            charge = official_2x_charge(row, model)
        elif request_id.startswith("o90v1_"):
            charge = official_v1_charge(row, model)
        else:
            return {**result, "status": "historical_price_requires_review"}
    except (KeyError, ValueError, TypeError, InvalidOperation):
        return {**result, "status": "invalid_receipt_pricing"}
    provider_id = str(row.get("id") or row.get("request_id") or "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", provider_id):
        return {**result, "status": "invalid_provider_id"}
    return {**result, "status": "confirmed", "actual_micro_cny": charge,
            "provider_request_id": provider_id}
