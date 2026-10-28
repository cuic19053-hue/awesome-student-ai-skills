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
