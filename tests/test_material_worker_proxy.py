import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from proposal import material_worker_proxy as proxy


def test_context_rpc_uses_only_worker_capability_and_short_job_scope(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "publishable")
    calls = []

    def fake_open(request, timeout=15):
        calls.append((request, timeout))
        return io.BytesIO(json.dumps({
            "id": "a" * 32,
            "project_id": "b" * 32,
            "owner_id": "user-id",
            "kind": "section",
            "payload": {"paid": True, "platform": True},
        }).encode())

    monkeypatch.setattr(proxy, "supabase_urlopen", fake_open)
    bridge = proxy.MaterialWorkerBridge("worker-secret-not-logged", "a" * 32, "c" * 32)

    assert bridge.context()["kind"] == "section"
    request, timeout = calls[0]
    body = json.loads(request.data)
    assert request.full_url.endswith("/rest/v1/rpc/material_worker_context")
    assert body == {"p_secret": "worker-secret-not-logged", "p_job_id": "a" * 32, "p_lease": "c" * 32}
    assert request.get_header("Authorization") == "Bearer publishable"
    assert timeout == 15


def test_meter_adapter_keeps_reserve_settle_and_refund_inside_job_lease(monkeypatch):
    actions = []

    class Bridge:
        def worker_rpc(self, action, **args):
            actions.append((action, args))
            return {"status": action}

    meter_store = proxy.MaterialWorkerMeterStore(Bridge())
    assert meter_store.reserve_workbench_usage("user", "req", "deepseek-v4-flash", 200_000, 17) == {
        "status": "reserve"
    }
    assert meter_store.settle_workbench_usage("req", 120_000, "provider-row") == {"status": "settle"}
    assert meter_store.refund_workbench_usage("req", "bad response") == {"status": "refund"}
    assert [action for action, _ in actions] == ["reserve", "settle", "refund"]
    assert actions[0][1]["request_id"] == "req"
    assert actions[0][1]["api_key_id"] == 17
    assert actions[1][1]["provider_id"] == "provider-row"
    assert actions[2][1]["reason"] == "bad response"


def test_byok_authorization_rpc_scopes_operation_to_one_active_lease(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "publishable")
    seen = []

    def fake_open(request, timeout=15):
        seen.append((request.full_url, json.loads(request.data)))
        return io.BytesIO(b'{"ok":true}')

    monkeypatch.setattr(proxy, "supabase_urlopen", fake_open)
    bridge = proxy.MaterialWorkerBridge("worker-secret-not-logged", "a" * 32, "c" * 32)
    assert bridge.authorize_byok("d" * 32, "image") == {"ok": True}
    url, body = seen[0]
    assert url.endswith("/rest/v1/rpc/material_worker_authorize_byok")
    assert body == {
        "p_secret": "worker-secret-not-logged",
        "p_job_id": "a" * 32,
        "p_lease": "c" * 32,
        "p_call_id": "d" * 32,
        "p_operation": "image",
    }


def test_bridge_transport_errors_never_echo_secret_or_database_body(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "publishable")

    def fail(_request, timeout=15):
        raise OSError("worker-secret-not-logged")

    monkeypatch.setattr(proxy, "supabase_urlopen", fail)
    bridge = proxy.MaterialWorkerBridge("worker-secret-not-logged", "a" * 32, "c" * 32)
    with pytest.raises(proxy.MaterialWorkerBridgeError) as err:
        bridge.context()
    assert str(err.value) == "worker bridge unavailable"
    assert "worker-secret-not-logged" not in str(err.value)
