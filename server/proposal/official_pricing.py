"""Versioned official price reference.

v1 (o90v1): 0.9x official price (frozen on 2026-10-14).
v2 (o2x1): 2.0x official price.
DeepSeek CNY: https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
GPT Image 2 Standard: https://developers.openai.com/api/docs/pricing
USD/CNY reference: https://open.er-api.com/v6/latest/USD (2026-10-14).
Changing prices or FX requires a NEW version; retain historical ones for reconciliation.
"""
from decimal import Decimal, ROUND_CEILING
from typing import Any

PRICE_VERSION = "o2x1"
USD_CNY_V1 = Decimal("6.705025")
DISCOUNT_V1 = Decimal("0.9")
MULTIPLIER_V2 = Decimal("2.0")


def _count(row: dict[str, Any], key: str) -> int:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Invalid usage field: {key}")
    return value


def _money(row: dict[str, Any], key: str) -> Decimal:
    value = Decimal(str(row[key]))
    if not value.is_finite() or value < 0:
        raise ValueError(f"Invalid cost field: {key}")
    return value


def _calculate_official_cny(row: dict[str, Any], model: str) -> Decimal:
    """Validate reported usage and return official CNY cost before multiplier."""
    input_tokens = _count(row, "input_tokens")
    output_tokens = _count(row, "output_tokens")
    if model == "deepseek-v4-flash":
        cached = _count(row, "cache_read_tokens")
        observed = [_money(row, k) for k in
                    ("input_cost", "output_cost", "cache_read_cost", "total_cost")]
        official = None
        for rates in ((Decimal(1), Decimal(4), Decimal(".02")),
                      (Decimal(2), Decimal(8), Decimal(".04"))):
            costs = [n * p / 1_000_000 for n, p in
                     zip((input_tokens, output_tokens, cached), rates)]
            expected = costs + [sum(costs)]
            if all(abs(a - b) <= Decimal("0.0000000001")
                   for a, b in zip(observed, expected)):
                official = sum(costs)
                break
        if official is None:
            raise ValueError("Relay tariff does not match official DeepSeek CNY pricing")
        return official
    elif model == "gpt-image-2":
        image_output = _count(row, "image_output_tokens")
        if image_output <= 0 or output_tokens != image_output or _count(row, "image_count") != 1:
            raise ValueError("Incomplete image output usage")
        if row.get("image_input_tokens", 0) != 0 or row.get("cache_read_tokens", 0) != 0:
            raise ValueError("Unexpected cached/image input for text-only generation")
        usd = (input_tokens * Decimal(5) + image_output * Decimal(30)) / 1_000_000
        return usd * USD_CNY_V1
    else:
        raise ValueError("No verified official price for this model")


def official_v1_charge(row: dict[str, Any], model: str) -> int:
    """Historical v1 pricing: 0.9x official price."""
    cny = _calculate_official_cny(row, model) * DISCOUNT_V1
    return int((cny * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def official_2x_charge(row: dict[str, Any], model: str) -> int:
    """Current v2 pricing: 2.0x official price."""
    cny = _calculate_official_cny(row, model) * MULTIPLIER_V2
    return int((cny * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
