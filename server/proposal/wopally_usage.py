from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any

from .wopally_auth import ServiceLoginUnavailable, service_token
from .wopally_transport import wopally_urlopen
from .official_pricing import official_v1_charge

class UsageUnavailable(RuntimeError):
    """The provider's authoritative charge cannot currently be confirmed."""


class WopallyUsage:
    """Price only the service account's confirmed, uniquely matched usage."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.environ.get("WOPALLY_API_URL", "https://api.wopally.cn")).rstrip("/")
        self.token = (token if token is not None else os.environ.get("WOPALLY_SERVICE_ACCESS_TOKEN", "")).strip()

    def find(self, request_id: str, api_key_id: int, model: str) -> tuple[int, str] | None:
        if not request_id or api_key_id <= 0:
            raise UsageUnavailable("中转站用量查询尚未配置")
        try:
            token = self.token or service_token(self.base_url)
        except ServiceLoginUnavailable as exc:
            raise UsageUnavailable("工作台专用账户登录失败") from exc
        marker = f"StardustWorkbench/{request_id}"
        for page in range(1, 6):
            query = urllib.parse.urlencode({"page": page, "page_size": 100, "api_key_id": api_key_id})
            req = urllib.request.Request(
                f"{self.base_url}/api/v1/usage?{query}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            try:
                with wopally_urlopen(req, timeout=8) as resp:
                    body: Any = json.load(resp)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                raise UsageUnavailable("中转站用量暂不可查询") from exc
            if not isinstance(body, dict) or body.get("code") not in (None, 0):
                raise UsageUnavailable("中转站拒绝用量查询")
            data = body.get("data", body)
            if isinstance(data, list):
                rows = data
            elif isinstance(data, dict):
                rows = data.get("items", data.get("records", data.get("list", [])))
            else:
                rows = []
            if not isinstance(rows, list):
                raise UsageUnavailable("中转站用量格式无法识别")
            for row in rows:
                if not isinstance(row, dict) or row.get("user_agent") != marker:
                    continue
                if int(row.get("api_key_id") or 0) != api_key_id or row.get("model") != model:
                    raise UsageUnavailable("中转站用量归属不符")
                try:
                    if re.fullmatch(r"o90v1_[0-9a-f]{32}", request_id):
                        micro = official_v1_charge(row, model)
                    else:
                        # Retain historical 3x/12x pricing across deployments.
                        if not (re.fullmatch(r"[0-9a-f]{32}", request_id)
                                or re.fullmatch(r"m12_[0-9a-f]{32}", request_id)):
                            raise ValueError("Unknown historical price version")
                        cost = Decimal(str(row["actual_cost"]))
                        if not cost.is_finite() or cost < 0:
                            raise ValueError
                        multiplier = 12 if request_id.startswith("m12_") else 3
                        from decimal import ROUND_CEILING
                        micro = int((cost * multiplier * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
                except (KeyError, InvalidOperation, ValueError, TypeError) as exc:
                    raise UsageUnavailable("中转站费用格式无法识别") from exc
                return micro, str(row.get("id") or row.get("request_id") or "")
            if len(rows) < 100:
                return None
        return None
