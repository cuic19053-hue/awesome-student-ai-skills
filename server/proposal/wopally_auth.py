from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

from .wopally_transport import wopally_urlopen


class ServiceLoginUnavailable(RuntimeError):
    pass


_lock = threading.Lock()
_cached_token = ""
_expires_at = 0.0


def service_token(base_url: str, *, timeout: float = 10) -> str:
    """Use only a dedicated low-privilege service login, never an admin password."""
    global _cached_token, _expires_at
    email = os.environ.get("WOPALLY_SERVICE_EMAIL", "").strip()
    password = os.environ.get("WOPALLY_SERVICE_PASSWORD", "")
    if not email or not password:
        # Explicitly supplied short-lived token is useful for staged testing,
        # but production should configure the dedicated service login.
        token = os.environ.get("WOPALLY_SERVICE_ACCESS_TOKEN", "").strip()
        if token:
            return token
        raise ServiceLoginUnavailable("工作台专用账户尚未配置")
    if _cached_token and time.monotonic() < _expires_at:
        return _cached_token
    deadline = time.monotonic() + timeout
    if not _lock.acquire(timeout=max(0, timeout)):
        raise ServiceLoginUnavailable("工作台专用账户登录繁忙")
    try:
        if _cached_token and time.monotonic() < _expires_at:
            return _cached_token
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ServiceLoginUnavailable("工作台专用账户登录超时")
        request = urllib.request.Request(
            base_url.rstrip("/") + "/api/v1/auth/login",
            data=json.dumps({"email": email, "password": password}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with wopally_urlopen(request, timeout=remaining) as response:
                body = json.load(response)
            data = body.get("data", body)
            if body.get("code") not in (None, 0) or not isinstance(data, dict):
                raise ValueError("login denied")
            token = str(data.get("access_token") or "")
            if not token:
                raise ValueError("missing access token")
            expected_id = os.environ.get("WOPALLY_SERVICE_USER_ID", "").strip()
            user = data.get("user") or {}
            if expected_id and str(user.get("id") or "") != expected_id:
                raise ValueError("dedicated service account mismatch")
            _cached_token = token
            _expires_at = time.monotonic() + max(30, min(int(data.get("expires_in") or 600) - 60, 600))
            return token
        except urllib.error.HTTPError as exc:
            raise ServiceLoginUnavailable(f"工作台专用账户登录被中转站拒绝（HTTP {exc.code}）") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError) as exc:
            raise ServiceLoginUnavailable("工作台专用账户登录失败") from exc
    finally:
        _lock.release()


def clear_cached_token() -> None:
    global _cached_token, _expires_at
    with _lock:
        _cached_token = ""
        _expires_at = 0.0
