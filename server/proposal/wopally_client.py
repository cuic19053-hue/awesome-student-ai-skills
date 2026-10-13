from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any

from .wopally_auth import ServiceLoginUnavailable, clear_cached_token, service_token
from .wopally_transport import wopally_urlopen

class WopallyUnavailable(RuntimeError):
    pass


class WopallyCardRejected(ValueError):
    pass


class WopallyClient:
    """Server-side adapter for the station's authenticated user APIs."""

    def __init__(
        self,
        base_url: str | None = None,
        access_token: str | None = None,
        redeem_path: str | None = None,
        history_path: str | None = None,
        timeout: int = 15,
    ):
        self.base_url = (
            base_url if base_url is not None else os.environ.get("WOPALLY_API_URL", "https://api.wopally.cn")
        ).rstrip("/")
        self.access_token = (
            access_token if access_token is not None else os.environ.get("WOPALLY_SERVICE_ACCESS_TOKEN", "")
        ).strip()
        self.redeem_path = (
            redeem_path if redeem_path is not None else os.environ.get("WOPALLY_CARD_REDEEM_PATH", "")
        ).strip()
        self.history_path = (
            history_path if history_path is not None else os.environ.get("WOPALLY_CARD_REDEEM_HISTORY_PATH", "")
        ).strip()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        parsed = urllib.parse.urlparse(self.base_url)
        return bool(
            (self.access_token or (
                os.environ.get("WOPALLY_SERVICE_EMAIL", "").strip()
                and os.environ.get("WOPALLY_SERVICE_PASSWORD", "")
            ))
            and self.redeem_path.startswith("/")
            and self.history_path.startswith("/")
            and parsed.scheme == "https"
            and parsed.hostname
        )

    def _request(
        self, path: str, method: str = "GET", body: dict[str, Any] | None = None,
        retried_login: bool = False,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if not self.is_configured:
            raise WopallyUnavailable("工作台代兑尚未配置 Wopally 服务账户凭证")
        url = f"{self.base_url}/{path.lstrip('/')}"
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            token = self.access_token or service_token(self.base_url)
        except ServiceLoginUnavailable as exc:
            raise WopallyUnavailable(str(exc)) from exc
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with wopally_urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Never include credential material or arbitrary response bodies in client errors.
            if path.split("?", 1)[0] == self.redeem_path and exc.code in {400, 404, 422}:
                raise WopallyCardRejected("卡密无效、已使用或不适用于余额充值") from exc
            if exc.code in {401, 403}:
                if exc.code == 401 and not self.access_token and not retried_login:
                    clear_cached_token()
                    return self._request(path, method, body, retried_login=True)
                raise WopallyUnavailable("Wopally 服务账户凭证失效或权限不足") from exc
            if exc.code == 429:
                raise WopallyUnavailable("Wopally 请求频率受限，请稍后重试") from exc
            raise WopallyUnavailable(f"Wopally 请求失败（HTTP {exc.code}）") from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise WopallyUnavailable("暂时无法确认 Wopally 的处理结果，请保留订单并稍后核对") from exc
        if not isinstance(result, dict):
            raise WopallyUnavailable("Wopally 返回格式无法识别")
        if result.get("code") not in (None, 0, "0"):
            if path.split("?", 1)[0] == self.redeem_path:
                raise WopallyCardRejected("卡密无效、已使用或不适用于余额充值")
            raise WopallyUnavailable("Wopally 拒绝了请求")
        data = result.get("data", result)
        if not isinstance(data, (dict, list)):
            raise WopallyUnavailable("Wopally 返回格式无法识别")
        return data

    def redeem_balance_code(self, code: str) -> dict[str, Any]:
        if not self.redeem_path:
            raise WopallyUnavailable("Wopally 卡密兑换 API 尚未核实")
        result = self._request(self.redeem_path, "POST", {"code": code})
        if not isinstance(result, dict):
            raise WopallyUnavailable("中转站兑换结果格式无效")
        result_type = str(result.get("type") or "").lower()
        if result_type != "balance":
            raise WopallyUnavailable("此卡密不是余额卡密，未发放工作台积分")
        try:
            value = Decimal(str(result["value"]))
        except (KeyError, TypeError, InvalidOperation) as exc:
            raise WopallyUnavailable("Wopally 未返回有效的卡密面值") from exc
        if value <= 0:
            raise WopallyUnavailable("Wopally 返回的卡密面值无效")
        user_info = result.get("user")
        provider_user_id = result.get("user_id")
        if provider_user_id is None and isinstance(user_info, dict):
            provider_user_id = user_info.get("id")
        if provider_user_id is None and not self.access_token and os.environ.get("WOPALLY_SERVICE_EMAIL", "").strip():
            # The dedicated login checks its returned user ID before making
            # this request; some redeem responses omit the user field.
            provider_user_id = os.environ.get("WOPALLY_SERVICE_USER_ID")
        return {
            "value_cny": str(value),
            "provider_user_id": int(provider_user_id) if provider_user_id is not None else None,
            "provider_balance": result.get("new_balance"),
            "message": str(result.get("message") or "兑换成功"),
        }

    def find_redeemed_balance_code(self, code: str, max_pages: int = 5) -> dict[str, Any] | None:
        """Reconcile an uncertain redeem response from the service account's own history."""
        if not self.history_path:
            raise WopallyUnavailable("Wopally 卡密历史查询 API 尚未核实")
        target = "".join(code.split()).upper()
        for page in range(1, max(1, min(max_pages, 10)) + 1):
            query = urllib.parse.urlencode({"page": page, "page_size": 100})
            data = self._request(f"{self.history_path}?{query}")
            items = data if isinstance(data, list) else data.get("items") or data.get("records") or []
            if not isinstance(items, list):
                return None
            for item in items:
                if not isinstance(item, dict):
                    continue
                if "".join(str(item.get("code") or "").split()).upper() != target:
                    continue
                if str(item.get("type") or "").lower() != "balance":
                    return {"type": str(item.get("type") or ""), "value_cny": None}
                try:
                    value = Decimal(str(item.get("value")))
                except (InvalidOperation, TypeError):
                    return None
                return {"type": "balance", "value_cny": str(value)}
            if len(items) < 100:
                break
        return None
