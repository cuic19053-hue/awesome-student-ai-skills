from __future__ import annotations

import hashlib
import os
import secrets
import urllib.parse
from decimal import Decimal
from typing import Any


class EPayClient:
    """通用聚合支付客户端（易支付标准协议，支持支付宝与微信双通道）。"""

    def __init__(
        self,
        pid: str | None = None,
        key: str | None = None,
        gateway_url: str | None = None,
        notify_url: str | None = None,
        return_url: str | None = None,
    ):
        self.pid = (pid if pid is not None else os.environ.get("PAY_PID", "")).strip()
        self.key = (key if key is not None else os.environ.get("PAY_KEY", "")).strip()
        self.gateway_url = (
            gateway_url if gateway_url is not None else os.environ.get("PAY_GATEWAY_URL", "")
        ).strip().rstrip("/")
        self.notify_url = (notify_url if notify_url is not None else os.environ.get("PAY_NOTIFY_URL", "")).strip()
        self.return_url = (return_url if return_url is not None else os.environ.get("PAY_RETURN_URL", "")).strip()

    @property
    def is_configured(self) -> bool:
        gateway = urllib.parse.urlparse(self.gateway_url)
        callback = urllib.parse.urlparse(self.notify_url)
        landing = urllib.parse.urlparse(self.return_url)
        return bool(
            self.pid and self.key and self.return_url
            and gateway.scheme == "https" and gateway.hostname
            and callback.scheme == "https" and callback.hostname
            and landing.scheme == "https" and landing.hostname
            and gateway.hostname not in {"example.com", "pay.example.com"}
        )

    def build_sign(self, params: dict[str, Any]) -> str:
        filtered = {
            k: str(v)
            for k, v in params.items()
            if k not in ("sign", "sign_type") and v is not None and str(v) != ""
        }
        sorted_keys = sorted(filtered.keys())
        query_str = "&".join(f"{k}={filtered[k]}" for k in sorted_keys)
        payload = query_str + self.key
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    def verify_notify(self, params: dict[str, Any]) -> bool:
        if not self.is_configured or str(params.get("pid", "")) != self.pid:
            return False
        if str(params.get("sign_type", "MD5")).upper() != "MD5":
            return False
        received_sign = params.get("sign", "")
        if not received_sign:
            return False
        expected_sign = self.build_sign(params)
        return hmac_equal(received_sign.lower(), expected_sign.lower())

    def build_pay_url(
        self,
        order_id: str,
        amount_cny: float,
        name: str,
        pay_type: str = "alipay",
        client_ip: str = "127.0.0.1",
    ) -> str:
        if not self.is_configured:
            raise ValueError("支付网关未配置完成")
        params: dict[str, Any] = {
            "pid": self.pid,
            "type": pay_type,
            "out_trade_no": order_id,
            "notify_url": self.notify_url,
            "return_url": self.return_url,
            "name": name,
            "money": f"{Decimal(str(amount_cny)):.2f}",
        }
        sign = self.build_sign(params)
        params["sign"] = sign
        params["sign_type"] = "MD5"
        query = urllib.parse.urlencode(params)
        return f"{self.gateway_url}/submit.php?{query}"


def hmac_equal(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)


def generate_recharge_code(prefix: str = "STAR") -> str:
    part1 = secrets.token_hex(2).upper()
    part2 = secrets.token_hex(2).upper()
    part3 = secrets.token_hex(2).upper()
    return f"{prefix}-{part1}-{part2}-{part3}"


def calculate_profit_share(
    gross_revenue: float,
    total_prompt_tokens: int = 0,
    total_completion_tokens: int = 0,
    per_million_cost_cny: float = 1.5,
    share_ratio: float = 0.7,
) -> dict[str, Any]:
    """
    计算 70% 利润分成（合作方拿七成，平台留三成）：
    总收入 - API 底层成本 = 净利润；合作方应得分成 = 净利润 * 70%
    """
    ratio_env = os.environ.get("PROFIT_SHARE_RATIO")
    if ratio_env:
        try:
            share_ratio = float(ratio_env)
        except ValueError:
            pass
    total_tokens = total_prompt_tokens + total_completion_tokens
    api_cost = round((total_tokens / 1_000_000) * per_million_cost_cny, 4)
    net_profit = max(0.0, round(gross_revenue - api_cost, 2))
    your_share = round(net_profit * share_ratio, 2)
    platform_share = round(net_profit - your_share, 2)
    return {
        "gross_revenue": round(gross_revenue, 2),
        "total_tokens": total_tokens,
        "api_cost": api_cost,
        "net_profit": net_profit,
        "your_share_70": your_share,
        "share_ratio": share_ratio,
        "platform_share": platform_share,
        "margin_percent": round((net_profit / gross_revenue * 100), 1) if gross_revenue > 0 else 100.0,
    }
