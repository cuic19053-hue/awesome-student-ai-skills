from __future__ import annotations

import io
import json
import urllib.request

import pytest

import server.app  # loads the server's proposal module path
from proposal.storage import InsufficientCreditsError, Store
from proposal.supabase_store import SupabaseStore, request_identity
from proposal.workbench_metering import WorkbenchMeter
from proposal.wopally_usage import UsageUnavailable, WopallyUsage
from proposal.wopally_transport import wopally_urlopen
from proposal.official_pricing import official_v1_charge


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_usage_matches_unique_marker_and_key_and_uses_exact_decimal(monkeypatch):
    request_id = "b" * 32
    def open_request(request, timeout):
        return FakeResponse(json.dumps({"code": 0, "data": {"items": [
            {"id": 55, "api_key_id": 684, "model": "deepseek-v4-flash",
             "user_agent": f"StardustWorkbench/{request_id}", "actual_cost": "0.00000025"},
        ]}}).encode())

    monkeypatch.setattr("proposal.wopally_usage.urllib.request.urlopen", open_request)
    assert WopallyUsage(token="test-only").find(request_id, 684, "deepseek-v4-flash") == (1, "55")
    with pytest.raises(UsageUnavailable, match="归属不符"):
        WopallyUsage(token="test-only").find(request_id, 999, "deepseek-v4-flash")


def test_new_requests_charge_official_ninety_percent(monkeypatch, tmp_path):
    store = Store(tmp_path)
    store.grant_workbench_payment_credits("alice", "paid-test-event-1", 1_000_000)
    meter = WorkbenchMeter(store, "alice", 684)
    request_id = meter.reserve("deepseek-v4-flash")
    assert request_id.startswith("o90v1_")

    def open_request(request, timeout):
        return FakeResponse(json.dumps({"code": 0, "data": {"items": [
            {"id": 55, "api_key_id": 684, "model": "deepseek-v4-flash",
             "user_agent": f"StardustWorkbench/{request_id}", "actual_cost": "999",
             "input_tokens": 10000, "output_tokens": 10000, "cache_read_tokens": 0,
             "input_cost": ".02", "output_cost": ".08", "cache_read_cost": 0,
             "total_cost": ".10"},
        ]}}).encode())

    monkeypatch.setattr("proposal.wopally_usage.urllib.request.urlopen", open_request)
    assert WopallyUsage(token="test-only").find(request_id, 684, "deepseek-v4-flash") == (90_000, "55")
    meter.usage = WopallyUsage(token="test-only")
    meter.settle(request_id, "deepseek-v4-flash")
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 910_000


@pytest.mark.parametrize(("legacy_request_id", "expected"), [
    ("a" * 32, 30_000), ("m12_" + "a" * 32, 120_000),
])
def test_pending_pre_change_request_keeps_original_price(monkeypatch, legacy_request_id, expected):

    def open_request(request, timeout):
        return FakeResponse(json.dumps({"code": 0, "data": {"items": [
            {"id": 56, "api_key_id": 684, "model": "deepseek-v4-flash",
             "user_agent": f"StardustWorkbench/{legacy_request_id}", "actual_cost": "0.01"},
        ]}}).encode())

    monkeypatch.setattr("proposal.wopally_usage.urllib.request.urlopen", open_request)
    assert WopallyUsage(token="test-only").find(legacy_request_id, 684, "deepseek-v4-flash") == (expected, "56")


def test_official_image_standard_token_prices_and_fixed_fx():
    row = {"input_tokens": 1000, "output_tokens": 1650, "image_output_tokens": 1650,
           "image_count": 1}
    # ($0.005 + $0.0495) * 6.705025 * 0.9, rounded up to micro-CNY.
    assert official_v1_charge(row, "gpt-image-2") == 328882
    row.pop("image_output_tokens")
    with pytest.raises(KeyError):
        official_v1_charge(row, "gpt-image-2")


def test_official_deepseek_off_peak_and_tariff_validation():
    row = {"input_tokens": 10000, "output_tokens": 10000, "cache_read_tokens": 10000,
           "input_cost": ".01", "output_cost": ".04", "cache_read_cost": ".0002",
           "total_cost": ".0502"}
    assert official_v1_charge(row, "deepseek-v4-flash") == 45180
    row["total_cost"] = ".1"
    with pytest.raises(ValueError, match="tariff"):
        official_v1_charge(row, "deepseek-v4-flash")


@pytest.mark.parametrize("value", [None, -1, 1.5, True, "1000"])
def test_official_price_rejects_unverified_usage(value):
    with pytest.raises((ValueError, KeyError)):
        official_v1_charge({"input_tokens": value}, "gpt-image-2")


def test_meter_reserves_once_then_refunds_difference_without_cross_user_spend(tmp_path):
    store = Store(tmp_path)
    store.grant_workbench_payment_credits("alice", "paid-test-event-1", 500_000)
    meter = WorkbenchMeter(store, "alice", 684)
    request_id = meter.reserve("deepseek-v4-flash")
    with pytest.raises(InsufficientCreditsError):
        WorkbenchMeter(store, "bob", 684).reserve("deepseek-v4-flash")
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 0
    meter.usage.find = lambda *args: (150_000, "provider-log-55")
    meter.settle(request_id, "deepseek-v4-flash")
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 350_000
    assert store.get_workbench_credit_balance("bob")["balance_micro_cny"] == 0
    meter.settle(request_id, "deepseek-v4-flash")
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 350_000


def test_supabase_narrow_capability_uses_verified_user_jwt(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKBENCH_BACKEND_SECRET", "test-server-capability")
    store = SupabaseStore(
        "https://project.example.test", "public-test-key",
        data_dir=tmp_path, service_role_key="",
    )
    seen = {}

    def fake_open(request, timeout):
        seen["url"] = request.full_url
        seen["authorization"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data)
        return FakeResponse(b'{"status":"reserved","balance_micro_cny":0}')

    monkeypatch.setattr("proposal.supabase_store.urllib.request.urlopen", fake_open)
    context = request_identity.set({"access_token": "signed-user-jwt", "user_id": "alice"})
    try:
        store.reserve_workbench_usage("alice", "request-12345", "deepseek-v4-flash", 1_000_000, 692)
    finally:
        request_identity.reset(context)
    assert seen["url"].endswith("/rpc/workbench_backend_reserve_usage")
    assert seen["authorization"] == "Bearer signed-user-jwt"
    assert seen["body"]["p_server_secret"] == "test-server-capability"
    assert seen["body"]["p_user_id"] == "alice"


def test_supabase_existing_balance_code_completion_uses_narrow_capability(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKBENCH_BACKEND_SECRET", "test-server-capability")
    store = SupabaseStore("https://project.example.test", "public-test-key",
                          data_dir=tmp_path, service_role_key="")
    seen = {}

    def fake_open(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data)
        return FakeResponse(b'{"status":"credited","balance_micro_cny":1000000}')

    monkeypatch.setattr("proposal.supabase_store.urllib.request.urlopen", fake_open)
    context = request_identity.set({"access_token": "signed-user-jwt", "user_id": "alice"})
    try:
        store.complete_workbench_card_redemption("intent-123", 1_000_000, 9001)
    finally:
        request_identity.reset(context)
    assert seen["url"].endswith("/rpc/workbench_backend_complete_card_redemption")
    assert seen["body"]["p_server_secret"] == "test-server-capability"
    assert seen["body"]["p_face_value_micro_cny"] == 1_000_000


def test_pinned_origin_rejects_other_hosts_and_private_ips(monkeypatch):
    monkeypatch.setenv("WOPALLY_ORIGIN_IP", "138.91.107.2")
    with pytest.raises(ValueError, match="verified HTTPS host"):
        wopally_urlopen(urllib.request.Request("https://example.com/v1/models"))
    monkeypatch.setenv("WOPALLY_ORIGIN_IP", "127.0.0.1")
    with pytest.raises(ValueError, match="public IP"):
        wopally_urlopen(urllib.request.Request("https://api.wopally.cn/health"))
