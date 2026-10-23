"""Narrow server-side bridge used by the isolated document Worker.

The Worker never receives Wopally credentials or the user-config encryption
key. It can ask the Vercel API to relay an inference request only while it
holds a valid job lease and the one-time worker capability.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .supabase_http import supabase_urlopen


class MaterialWorkerBridgeError(RuntimeError):
    """A generic error that never includes the bearer capability or job data."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


class MaterialWorkerBridge:
    def __init__(self, secret: str, job_id: str, lease: str):
        self.secret = secret
        self.job_id = job_id
        self.lease = lease
        self.supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.publishable_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
        if not self.supabase_url.startswith("https://") or not self.publishable_key:
            raise MaterialWorkerBridgeError("worker bridge unavailable")

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        request = urllib.request.Request(
            f"{self.supabase_url}/rest/v1/rpc/{path}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "apikey": self.publishable_key,
                "Authorization": f"Bearer {self.publishable_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with supabase_urlopen(request, timeout=15) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise MaterialWorkerBridgeError("worker bridge response too large")
            return json.loads(raw) if raw else None
        except MaterialWorkerBridgeError:
            raise
        except urllib.error.HTTPError as exc:
            raise MaterialWorkerBridgeError(
                "worker lease invalid" if exc.code in (401, 403) else "worker bridge unavailable",
                403 if exc.code in (401, 403) else 503,
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            # Deliberately suppress transport/body diagnostics; they can contain
            # capability inputs or private project metadata.
            raise MaterialWorkerBridgeError("worker bridge unavailable") from None

    def context(self) -> dict[str, Any]:
        result = self._post(
            "material_worker_context",
            {"p_secret": self.secret, "p_job_id": self.job_id, "p_lease": self.lease},
        )
        if not isinstance(result, dict):
            raise MaterialWorkerBridgeError("worker lease invalid", 403)
        return result

    def worker_rpc(self, action: str, **args: Any) -> Any:
        return self._post(
            "material_worker_rpc",
            {
                "p_secret": self.secret,
                "p_action": action,
                "p_args": {"id": self.job_id, "lease": self.lease, **args},
            },
        )

    def authorize_byok(self, call_id: str, operation: str) -> Any:
        return self._post(
            "material_worker_authorize_byok",
            {
                "p_secret": self.secret,
                "p_job_id": self.job_id,
                "p_lease": self.lease,
                "p_call_id": call_id,
                "p_operation": operation,
            },
        )


class MaterialWorkerMeterStore:
    """WorkbenchMeter adapter bound to one authenticated job lease."""

    def __init__(self, bridge: MaterialWorkerBridge):
        self.bridge = bridge

    def reserve_workbench_usage(self, user_id, request_id, model, amount, api_key_id=None):
        return self.bridge.worker_rpc(
            "reserve", request_id=request_id, model=model, api_key_id=api_key_id
        )

    def settle_workbench_usage(self, request_id, amount, provider_id):
        return self.bridge.worker_rpc(
            "settle", request_id=request_id, amount=amount, provider_id=provider_id
        )

    def refund_workbench_usage(self, request_id, reason="provider_error"):
        return self.bridge.worker_rpc("refund", request_id=request_id, reason=reason)
