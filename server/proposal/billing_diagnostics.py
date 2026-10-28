"""Read-only, content-free inspection of one provider receipt for operators."""
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import os
import re
import urllib.parse

from .official_pricing import official_2x_charge, official_v1_charge
from .wopally_client import WopallyClient, WopallyUnavailable

REQUEST_ID = r"^(?:o2x1_|o90v1_|m12_)?[a-f0-9]{32}$"
NUMERIC_FIELDS = (
    "input_tokens", "output_tokens", "cache_read_tokens", "image_output_tokens",
    "image_input_tokens", "image_count", "input_cost", "output_cost",
    "cache_read_cost", "total_cost", "actual_cost",
)


class UsageOnlyClient(WopallyClient):
    """Only read usage; unlike redemption, does not depend on card endpoints."""

    @property
    def is_configured(self):
        url = urllib.parse.urlparse(self.base_url)
        has_login = bool(self.access_token or (
            os.environ.get("WOPALLY_SERVICE_EMAIL", "").strip()
            and os.environ.get("WOPALLY_SERVICE_PASSWORD", "")
        ))
        return has_login and url.scheme == "https" and bool(url.hostname)

    def _request(self, path, method="GET", body=None, *, retried_login=False):
        if method != "GET" or body is not None or not re.fullmatch(
            r"/api/v1/usage\?page=[1-5]&page_size=100&api_key_id=[1-9][0-9]*", path
        ):
            raise ValueError("Only bounded read-only usage requests are allowed")
        return super()._request(path, method, body, retried_login=retried_login)


def inspect_receipt(request_id: str, api_key_id: int, client=None):
    """Never invokes inference, changes balances, or returns prompts/credentials."""
    if not re.fullmatch(REQUEST_ID, request_id) or api_key_id <= 0:
        raise ValueError("Invalid receipt lookup")
    client = client or UsageOnlyClient(timeout=8)
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
    # Reaching the page limit with full pages cannot prove uniqueness.
    if page == 5 and len(rows) == 100:
        return {"status": "incomplete_scan", "pages_scanned": page}
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
            cost = Decimal(str(row["actual_cost"]))
            if not cost.is_finite() or cost < 0:
                raise ValueError("invalid historical cost")
            multiplier = 12 if request_id.startswith("m12_") else 3
            charge = int((cost * multiplier * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
    except (KeyError, ValueError, TypeError, InvalidOperation):
        return {**result, "status": "invalid_receipt_pricing"}
    provider_id = str(row.get("id") or row.get("request_id") or "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", provider_id):
        return {**result, "status": "invalid_provider_id"}
    return {**result, "status": "confirmed", "actual_micro_cny": charge,
            "provider_request_id": provider_id}
