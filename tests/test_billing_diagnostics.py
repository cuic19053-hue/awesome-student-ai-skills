from fastapi.testclient import TestClient
import pytest
import server.app as app_module
from proposal.billing_diagnostics import inspect_receipt

RID = "o2x1_" + "a" * 32


class UsageClient:
    def __init__(self, rows):
        self.rows = rows
        self.paths = []

    def _request(self, path):
        self.paths.append(path)
        return {"items": self.rows}


def receipt(**changes):
    return {
        "id": 999, "api_key_id": 692, "model": "deepseek-v4-flash",
        "user_agent": f"StardustWorkbench/{RID}",
        "input_tokens": 10000, "output_tokens": 10000, "cache_read_tokens": 0,
        "input_cost": ".02", "output_cost": ".08", "cache_read_cost": "0",
        "total_cost": ".10", "prompt": "never expose", "api_key": "secret",
        **changes,
    }


def test_receipt_confirms_exact_cost_without_content_or_secrets():
    client = UsageClient([receipt()])
    result = inspect_receipt(RID, 692, client)
    assert result["status"] == "confirmed"
    assert result["actual_micro_cny"] == 200000
    assert "secret" not in str(result) and "never expose" not in str(result)
    assert client.paths == ["/api/v1/usage?page=1&page_size=100&api_key_id=692"]


@pytest.mark.parametrize(("rows", "status"), [
    ([], "receipt_not_found"),
    ([receipt(), receipt()], "ambiguous_receipts"),
    ([receipt(api_key_id=111)], "ownership_mismatch"),
    ([receipt(total_cost=".99")], "invalid_receipt_pricing"),
    ([receipt(model="arbitrary")], "unsupported_model"),
])
def test_receipt_never_guesses_a_charge(rows, status):
    result = inspect_receipt(RID, 692, UsageClient(rows))
    assert result["status"] == status
    assert "actual_micro_cny" not in result


def test_diagnostics_endpoint_requires_separate_secret_and_never_writes(monkeypatch):
    client = TestClient(app_module.app)
    monkeypatch.setenv("BILLING_DIAGNOSTIC_TOKEN", "test-only-probe")
    monkeypatch.setenv("WOPALLY_WORKBENCH_API_KEY_ID", "692")
    calls = []

    def inspect(request_id, key_id):
        calls.append((request_id, key_id))
        return {"status": "receipt_not_found"}

    monkeypatch.setattr("proposal.billing_diagnostics.inspect_receipt", inspect)
    assert client.post("/api/admin/provider-usage", json={"request_id": RID}).status_code == 403
    assert calls == []
    response = client.post("/api/admin/provider-usage", json={"request_id": RID},
                           headers={"x-billing-probe-token": "test-only-probe"})
    assert response.status_code == 200
    assert calls == [(RID, 692)]
    assert client.post("/api/admin/provider-usage", json={"request_id": "http://evil"},
                       headers={"x-billing-probe-token": "test-only-probe"}).status_code == 422


@pytest.mark.parametrize(("request_id", "multiplier"), [("a" * 32, 3), ("m12_" + "a" * 32, 12)])
def test_historical_receipt_uses_its_original_price(request_id, multiplier):
    row = receipt(user_agent=f"StardustWorkbench/{request_id}", actual_cost=".01")
    assert inspect_receipt(request_id, 692, UsageClient([row]))["actual_micro_cny"] == 10000 * multiplier


def test_full_five_page_window_does_not_claim_unique_receipt():
    class FullPages:
        def _request(self, path):
            return {"items": [receipt()] + [{}] * 99 if "page=1&" in path else [{}] * 100}

    assert inspect_receipt(RID, 692, FullPages())["status"] == "incomplete_scan"


def test_usage_worker_does_not_depend_on_card_redemption_configuration(monkeypatch):
    from proposal.billing_diagnostics import UsageOnlyClient
    monkeypatch.delenv("WOPALLY_CARD_REDEEM_PATH", raising=False)
    monkeypatch.delenv("WOPALLY_CARD_REDEEM_HISTORY_PATH", raising=False)
    client = UsageOnlyClient(base_url="https://api.wopally.cn", access_token="test", timeout=3)
    assert client.is_configured
    with pytest.raises(ValueError, match="read-only"):
        client._request("/api/v1/cards/redeem", "POST", {})


def test_background_worker_settles_only_confirmed_matched_model():
    from proposal.billing_reconcile import run_once
    calls = []

    def rpc(_store, action, args=None):
        calls.append((action, args))
        if action == "claim":
            return {"status": "claimed", "request_id": RID, "model": "deepseek-v4-flash",
                    "api_key_id": 692, "lease_id": "lease"}
        if action == "complete":
            return {"status": "settled"}
        if action == "alerts":
            return {"alert_count": 0}
        return {"status": "deferred"}

    receipt_data = {"status": "confirmed", "model": "deepseek-v4-flash",
                    "actual_micro_cny": 123, "provider_request_id": "receipt"}
    assert run_once(object(), rpc, lambda *_: receipt_data) == {"status": "settled", "alert_count": 0}
    assert [call[0] for call in calls] == ["claim", "complete", "alerts"]
    calls.clear()
    receipt_data["model"] = "gpt-image-2"
    assert run_once(object(), rpc, lambda *_: receipt_data)["status"] == "deferred"
    assert calls[1][1]["reason"] == "model_mismatch"
    calls.clear()
    assert run_once(object(), rpc, lambda *_: {"status": "receipt_not_found"})["status"] == "deferred"
    assert calls[1][1]["reason"] == "receipt_not_found"


def test_background_endpoint_requires_secret(monkeypatch):
    client = TestClient(app_module.app)
    monkeypatch.setenv("BILLING_DIAGNOSTIC_TOKEN", "test-only-probe")
    monkeypatch.setattr("proposal.billing_reconcile.run_batch",
                        lambda _: {"status": "idle", "alert_count": 0})
    assert client.post("/api/admin/reconcile-usage").status_code == 403
    response = client.post("/api/admin/reconcile-usage",
                           headers={"x-billing-probe-token": "test-only-probe"})
    assert response.json() == {"status": "idle", "alert_count": 0}


def test_background_batch_bounds_work_and_preserves_alerts(monkeypatch):
    from proposal.billing_reconcile import run_batch
    calls = []

    def one(*_args):
        calls.append(1)
        return {"status": "deferred", "alert_count": 1 if len(calls) == 1 else 0}

    monkeypatch.setattr("proposal.billing_reconcile.run_once", one)
    ticks = iter([0, 16])
    assert run_batch(object(), clock=lambda: next(ticks)) == {
        "status": "deferred", "processed": 1, "alert_count": 1,
    }
    calls.clear()
    assert run_batch(object(), clock=lambda: 0) == {
        "status": "deferred", "processed": 5, "alert_count": 1,
    }


def test_balance_never_waits_for_provider_when_background_worker_enabled(monkeypatch, tmp_path):
    from proposal.storage import Store
    store = Store(tmp_path)
    monkeypatch.setattr(app_module, "store", store)
    monkeypatch.setattr(app_module, "CLOUD_MODE", True)
    monkeypatch.setattr(app_module, "_current_user_id", lambda _: "alice")
    monkeypatch.setattr(app_module, "_platform_bundle_ready", lambda: True)
    monkeypatch.setenv("BILLING_BACKGROUND_RECONCILIATION", "true")
    monkeypatch.setattr(store, "pending_workbench_usage",
                        lambda *_: pytest.fail("balance must not query the provider"))
    assert app_module.get_user_balance(None)["user_id"] == "alice"
