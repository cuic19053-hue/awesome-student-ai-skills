from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

import server.app as server_app
from proposal.credit_security import card_code_digest, encrypt_card_code, workbench_voucher_digest
from proposal.storage import CreditRateLimitError, Store
from proposal.wopally_client import WopallyCardRejected, WopallyUnavailable


client = TestClient(server_app.app)


@pytest.fixture
def isolated_store(monkeypatch, tmp_path):
    local_store = Store(tmp_path)
    monkeypatch.setattr(server_app, "store", local_store)
    return local_store


class FakeWopallyClient:
    calls = 0
    result = {"value_cny": "1", "provider_user_id": 9001}
    error: Exception | None = None

    def __init__(self):
        pass

    def redeem_balance_code(self, code):
        type(self).calls += 1
        if type(self).error:
            raise type(self).error
        return dict(type(self).result)

    def find_redeemed_balance_code(self, code):
        return None


def enable_local_card_redeem(monkeypatch):
    monkeypatch.setenv("WORKBENCH_CARD_REDEMPTION_APPROVED", "true")
    monkeypatch.setenv("WORKBENCH_CARD_REDEMPTION_PAUSED", "false")
    monkeypatch.setenv("WOPALLY_REDEEM_API_VERIFIED", "true")
    monkeypatch.setenv("WORKBENCH_LOCAL_CARD_REDEMPTION", "true")
    monkeypatch.setenv("WOPALLY_SERVICE_ACCESS_TOKEN", "test-only-token")
    monkeypatch.setenv("WOPALLY_CARD_REDEEM_PATH", "/test/redeem")
    monkeypatch.setenv("WOPALLY_CARD_REDEEM_HISTORY_PATH", "/test/redeem/history")
    monkeypatch.setenv("WOPALLY_CARD_SHOP_URL", "https://shop.example.test")
    monkeypatch.setenv("WOPALLY_ALLOWED_CARD_VALUES_CNY", "1,5,10,20,50")
    monkeypatch.setenv(
        "WORKBENCH_REDEEM_ENCRYPTION_KEY",
        base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="),
    )
    monkeypatch.setattr(server_app, "WopallyClient", FakeWopallyClient)
    FakeWopallyClient.calls = 0
    FakeWopallyClient.error = None
    FakeWopallyClient.result = {"value_cny": "1", "provider_user_id": 9001}


def test_card_redemption_is_off_until_owner_approval_and_credentials(monkeypatch):
    monkeypatch.delenv("WORKBENCH_CARD_REDEMPTION_APPROVED", raising=False)
    monkeypatch.delenv("WOPALLY_SERVICE_ACCESS_TOKEN", raising=False)
    assert client.get("/api/config").json()["card_redemption_enabled"] is False
    response = client.post("/api/pay/redeem", json={"code": "FAKE-CARD-CODE-123"})
    assert response.status_code == 400


def test_paid_pilot_fingerprint_never_redeems_or_credits(monkeypatch, isolated_store):
    code = "AGT1-12345678-90ABCDEF-12345678-90ABCDEF"
    response = client.post("/api/pay/card-fingerprint", json={"code": code})
    assert response.status_code == 200
    assert response.json()["fingerprint"] == workbench_voucher_digest(code).hex()
    labeled = client.post("/api/pay/card-fingerprint", json={"code": "卡密：" + code + "，请回工作台兑换"})
    assert labeled.json()["fingerprint"] == workbench_voucher_digest(code).hex()
    assert isolated_store.get_workbench_credit_balance("local_user")["balance_micro_cny"] == 0
    assert client.post("/api/pay/card-fingerprint", json={"code": "bad"}).status_code == 400


def test_card_redemption_requires_a_verified_upstream_api_contract(monkeypatch):
    enable_local_card_redeem(monkeypatch)
    monkeypatch.setenv("WOPALLY_REDEEM_API_VERIFIED", "false")
    assert client.get("/api/config").json()["card_redemption_enabled"] is False
    response = client.post("/api/pay/redeem", json={"code": "FAKE-CARD-CODE-123"})
    assert response.status_code == 400
    assert FakeWopallyClient.calls == 0


def test_admin_pause_switch_disables_card_redemption(monkeypatch):
    enable_local_card_redeem(monkeypatch)
    monkeypatch.setenv("WORKBENCH_CARD_REDEMPTION_PAUSED", "true")
    assert client.get("/api/config").json()["card_redemption_enabled"] is False
    response = client.post("/api/pay/redeem", json={"code": "FAKE-CARD-CODE-123"})
    assert response.status_code == 400
    assert FakeWopallyClient.calls == 0


def test_old_direct_checkout_and_unverified_hosted_models_fail_closed():
    checkout = client.post("/api/pay/create", json={"plan_id": "basic", "pay_type": "alipay"})
    assert checkout.status_code == 410
    assert client.get("/api/models/preset").json() == {"models": [], "plans": []}


def test_preset_configuration_check_does_not_consume_credits(monkeypatch, isolated_store):
    monkeypatch.setattr(server_app, "_platform_bundle_ready", lambda: True)
    response = client.post("/api/model-config/test", json={
        "provider": "preset", "model": "workbench-bundle"
    })
    assert response.status_code == 200
    assert response.json()["model"] == "workbench-bundle"
    assert isolated_store.get_workbench_credit_balance("local_user")["balance_micro_cny"] == 0


def _signed_sub2_payment(body: dict, secret: str) -> tuple[bytes, str]:
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, f"sha256={signature}"


def test_sub2_payment_webhook_credits_only_paid_user_once(monkeypatch, isolated_store):
    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    monkeypatch.setenv("SUB2_PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")
    body = {
        "event_id": "sub2-order-12345678",
        "workbench_user_id": "user-paid",
        "amount_cny": "1.25",
        "currency": "CNY",
        "status": "paid",
    }
    raw, signature = _signed_sub2_payment(body, "test-webhook-secret")

    response = client.post(
        "/api/pay/notify",
        content=raw,
        headers={"content-type": "application/json", "x-sub2-payment-signature": signature},
    )
    assert response.status_code == 200
    assert response.json()["credits_added"] == 12.5
    assert response.json()["balance"] == 12.5

    replay = client.post(
        "/api/pay/notify",
        content=raw,
        headers={"content-type": "application/json", "x-sub2-payment-signature": signature},
    )
    assert replay.status_code == 200
    assert replay.json()["duplicate"] is True
    assert replay.json()["balance"] == 12.5
    assert len(isolated_store.get_workbench_credit_transactions("user-paid")) == 1


def test_sub2_payment_webhook_rejects_unpaid_and_invalid_signatures(
    monkeypatch, isolated_store
):
    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    monkeypatch.setenv("SUB2_PAYMENT_WEBHOOK_SECRET", "test-webhook-secret")
    body = {
        "event_id": "sub2-order-unpaid",
        "workbench_user_id": "user-unpaid",
        "amount_cny": "9.9",
        "currency": "CNY",
        "status": "pending",
    }
    raw, signature = _signed_sub2_payment(body, "test-webhook-secret")
    unpaid = client.post(
        "/api/pay/notify",
        content=raw,
        headers={"content-type": "application/json", "x-sub2-payment-signature": signature},
    )
    assert unpaid.status_code == 400

    paid_body = {**body, "event_id": "sub2-order-paid", "status": "paid"}
    raw, _ = _signed_sub2_payment(paid_body, "test-webhook-secret")
    forged = client.post(
        "/api/pay/notify",
        content=raw,
        headers={"content-type": "application/json", "x-sub2-payment-signature": "sha256=00"},
    )
    assert forged.status_code == 401
    assert isolated_store.get_workbench_credit_balance("user-unpaid")["balance_micro_cny"] == 0


def test_payment_event_cannot_credit_multiple_workbench_users(tmp_path):
    store = Store(tmp_path)
    store.grant_workbench_payment_credits("user-a", "same-event-12345", 100_000)
    with pytest.raises(ValueError, match="关联到其他工作台账户"):
        store.grant_workbench_payment_credits("user-b", "same-event-12345", 100_000)
    assert store.get_workbench_credit_balance("user-b")["balance_micro_cny"] == 0


def test_wopally_card_credits_only_the_authenticated_workbench_user(monkeypatch, isolated_store):
    enable_local_card_redeem(monkeypatch)
    start = client.get("/api/user/balance").json()
    assert start["credits"] == 0

    response = client.post("/api/pay/redeem", json={"code": "ABCD-EFGH-1234"})
    assert response.status_code == 200
    assert response.json()["credits_added"] == 10
    assert response.json()["balance"] == 10
    assert FakeWopallyClient.calls == 1

    # Replaying the same card never calls Wopally again or adds a second credit.
    replay = client.post("/api/pay/redeem", json={"code": "ABCD-EFGH-1234"})
    assert replay.status_code == 200
    assert replay.json()["duplicate"] is True
    assert replay.json()["balance"] == 10
    assert FakeWopallyClient.calls == 1

    balance = client.get("/api/user/balance").json()
    assert balance["credits"] == 10
    assert balance["total_credited"] == 10


def test_workbench_voucher_requires_activation_and_is_atomic(monkeypatch, isolated_store):
    code = "AGT1-12345678-90ABCDEF-12345678-90ABCDEF"
    enable_local_card_redeem(monkeypatch)
    digest = workbench_voucher_digest(code)
    isolated_store.import_workbench_voucher_drafts(
        "batch-a", [(digest, 1_000_000)]
    )
    assert isolated_store.activate_workbench_voucher_batch("batch-a") == 0
    with pytest.raises(ValueError, match="尚未启用"):
        isolated_store.lookup_paired_voucher(digest)
    assert isolated_store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 0

    ciphertext = encrypt_card_code("PRIVATE-UPSTREAM-CODE")
    isolated_store.pair_workbench_voucher(digest, ciphertext)
    assert isolated_store.activate_workbench_voucher_batch("batch-a") == 1
    intent = isolated_store.begin_workbench_card_redemption("alice", digest, ciphertext)
    assert isolated_store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 0
    first = isolated_store.complete_paired_voucher(intent["id"], 1_000_000, 9001)
    assert first["duplicate"] is False
    assert first["balance_micro_cny"] == 1_000_000
    replay = isolated_store.complete_paired_voucher(intent["id"], 1_000_000, 9001)
    assert replay["duplicate"] is True
    with pytest.raises(ValueError, match="其他工作台账户"):
        isolated_store.begin_workbench_card_redemption("bob", digest, ciphertext)
    assert isolated_store.get_workbench_credit_balance("bob")["balance_micro_cny"] == 0
    assert len(isolated_store.get_workbench_credit_transactions("alice")) == 1

    _enable_paired_vouchers(monkeypatch)
    response = client.post("/api/pay/redeem", json={"code": code})
    assert response.status_code == 400  # Local user cannot claim Alice's code.


def _enable_paired_vouchers(monkeypatch):
    enable_local_card_redeem(monkeypatch)
    monkeypatch.setenv("WORKBENCH_VOUCHERS_APPROVED", "true")
    monkeypatch.setenv("WORKBENCH_VOUCHERS_PAUSED", "false")
    monkeypatch.setenv("WORKBENCH_MODEL_BUNDLE_READY", "true")
    monkeypatch.setenv("WORKBENCH_LOCAL_VOUCHERS", "true")
    monkeypatch.setenv("WOPALLY_SERVICE_USER_ID", "9001")
    monkeypatch.setattr(server_app, "_platform_bundle_ready", lambda: True)


def test_workbench_voucher_api_is_fail_closed_until_models_are_ready(monkeypatch, isolated_store):
    code = "AGT1-AAAAAAAA-BBBBBBBB-CCCCCCCC-DDDDDDDD"
    isolated_store.import_workbench_voucher_drafts(
        "batch-b", [(workbench_voucher_digest(code), 5_000_000)]
    )
    enable_local_card_redeem(monkeypatch)
    isolated_store.pair_workbench_voucher(
        workbench_voucher_digest(code), encrypt_card_code("PRIVATE-CODE-B")
    )
    isolated_store.activate_workbench_voucher_batch("batch-b")
    monkeypatch.setenv("WORKBENCH_VOUCHERS_APPROVED", "true")
    monkeypatch.setenv("WORKBENCH_VOUCHERS_PAUSED", "false")
    monkeypatch.setenv("WORKBENCH_LOCAL_VOUCHERS", "true")
    monkeypatch.delenv("WORKBENCH_MODEL_BUNDLE_READY", raising=False)
    assert client.post("/api/pay/redeem", json={"code": code}).status_code == 503
    assert isolated_store.get_workbench_credit_balance("local_user")["balance_micro_cny"] == 0

    _enable_paired_vouchers(monkeypatch)
    FakeWopallyClient.result = {"value_cny": "5", "provider_user_id": 9001}
    credited = client.post("/api/pay/redeem", json={"code": code})
    assert credited.status_code == 200
    assert credited.json()["credits_added"] == 50
    assert credited.json()["balance"] == 50
    assert FakeWopallyClient.calls == 1
    assert client.post("/api/pay/redeem", json={"code": code}).json()["duplicate"] is True
    assert FakeWopallyClient.calls == 1


def test_paired_voucher_rejects_wrong_provider_face_without_credit(monkeypatch, isolated_store):
    code = "AGT1-11111111-22222222-33333333-44444444"
    digest = workbench_voucher_digest(code)
    isolated_store.import_workbench_voucher_drafts("batch-c", [(digest, 1_000_000)])
    _enable_paired_vouchers(monkeypatch)
    isolated_store.pair_workbench_voucher(digest, encrypt_card_code("PRIVATE-CODE-C"))
    isolated_store.activate_workbench_voucher_batch("batch-c")
    FakeWopallyClient.result = {"value_cny": "5", "provider_user_id": 9001}
    response = client.post("/api/pay/redeem", json={"code": code})
    assert response.status_code == 409
    assert isolated_store.get_workbench_credit_balance("local_user")["balance_micro_cny"] == 0


def test_card_hash_cannot_be_claimed_by_another_user(monkeypatch, isolated_store):
    monkeypatch.setenv(
        "WORKBENCH_REDEEM_ENCRYPTION_KEY",
        base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="),
    )
    store = isolated_store
    digest = card_code_digest("ABCD-EFGH-1234")
    ciphertext = encrypt_card_code("ABCD-EFGH-1234")
    store.begin_workbench_card_redemption("user-a", digest, ciphertext)
    with pytest.raises(ValueError, match="其他工作台账户"):
        store.begin_workbench_card_redemption("user-b", digest, ciphertext)


def test_card_redemption_has_per_user_hourly_rate_limit(tmp_path):
    store = Store(tmp_path)
    for _ in range(10):
        store.begin_workbench_card_redemption("user-a", uuid.uuid4().bytes, b"encrypted")
    with pytest.raises(CreditRateLimitError):
        store.begin_workbench_card_redemption("user-a", uuid.uuid4().bytes, b"encrypted")
    # The guard is account-scoped; another user retains their own allowance.
    other = store.begin_workbench_card_redemption("user-b", uuid.uuid4().bytes, b"encrypted")
    assert other["status"] == "pending"


def test_wopally_invalid_card_is_rejected_without_credit(monkeypatch, isolated_store):
    enable_local_card_redeem(monkeypatch)
    FakeWopallyClient.error = WopallyCardRejected("卡密无效、已使用或不适用于余额充值")
    response = client.post("/api/pay/redeem", json={"code": "BAD-CARD-12345"})
    assert response.status_code == 400
    assert client.get("/api/user/balance").json()["credits"] == 0


def test_uncertain_redemption_stays_pending_and_replay_is_not_forwarded(monkeypatch, isolated_store):
    enable_local_card_redeem(monkeypatch)
    FakeWopallyClient.error = WopallyUnavailable("网络超时")
    response = client.post("/api/pay/redeem", json={"code": "PEND-CARD-12345"})
    assert response.status_code == 503
    assert client.get("/api/user/balance").json()["credits"] == 0
    assert FakeWopallyClient.calls == 1

    # An uncertain provider result is not blindly submitted again.
    replay = client.post("/api/pay/redeem", json={"code": "PEND-CARD-12345"})
    assert replay.status_code == 202
    assert FakeWopallyClient.calls == 1


def test_unapproved_face_value_is_not_credited_but_is_flagged(monkeypatch, isolated_store):
    enable_local_card_redeem(monkeypatch)
    FakeWopallyClient.result = {"value_cny": "2", "provider_user_id": 9001}
    response = client.post("/api/pay/redeem", json={"code": "UNLISTED-CARD-123"})
    assert response.status_code == 409
    assert client.get("/api/user/balance").json()["credits"] == 0


def test_credit_reservation_settlement_and_refund(tmp_path):
    store = Store(tmp_path)
    store.get_workbench_credit_balance("alice")
    card = store.begin_workbench_card_redemption("alice", uuid.uuid4().bytes, b"encrypted")
    store.complete_workbench_card_redemption(card["id"], 1_000_000, 10)
    reserve = store.reserve_workbench_usage("alice", "req_12345678", "model-a", 200_000, 55)
    assert reserve["balance_micro_cny"] == 800_000

    settled = store.settle_workbench_usage("req_12345678", 75_000, "wopally-req")
    assert settled["status"] == "settled"
    assert settled["balance_micro_cny"] == 925_000
    assert store.get_workbench_credit_balance("alice")["total_spent_micro_cny"] == 75_000

    store.reserve_workbench_usage("alice", "req_87654321", "model-a", 100_000, 55)
    refunded = store.refund_workbench_usage("req_87654321")
    assert refunded["balance_micro_cny"] == 925_000


def test_credit_wallets_are_isolated_between_users(tmp_path):
    store = Store(tmp_path)
    card_a = store.begin_workbench_card_redemption("user-a", uuid.uuid4().bytes, b"encrypted-a")
    card_b = store.begin_workbench_card_redemption("user-b", uuid.uuid4().bytes, b"encrypted-b")
    store.complete_workbench_card_redemption(card_a["id"], 1_000_000)
    store.complete_workbench_card_redemption(card_b["id"], 500_000)

    assert store.get_workbench_credit_balance("user-a")["balance_micro_cny"] == 1_000_000
    assert store.get_workbench_credit_balance("user-b")["balance_micro_cny"] == 500_000
    assert store.get_workbench_credit_balance("user-a")["total_credited_micro_cny"] == 1_000_000


def test_concurrent_credit_reservations_cannot_overdraw_user_wallet(tmp_path):
    store = Store(tmp_path)
    card = store.begin_workbench_card_redemption("user-a", uuid.uuid4().bytes, b"encrypted")
    store.complete_workbench_card_redemption(card["id"], 1_000_000)

    def reserve(request_id):
        try:
            return store.reserve_workbench_usage("user-a", request_id, "model-a", 700_000)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, ["req_parallel_0001", "req_parallel_0002"]))

    assert sum(result is not None for result in results) == 1
    assert store.get_workbench_credit_balance("user-a")["balance_micro_cny"] == 300_000


def test_supabase_begin_redemption_normalizes_rpc_id_field(monkeypatch, tmp_path):
    from proposal.supabase_store import SupabaseStore, request_identity

    store = SupabaseStore("https://example.supabase.co", "publishable", tmp_path, "service-role")
    monkeypatch.setattr(
        store,
        "_service_rpc",
        lambda *_args, **_kwargs: {
            "intent_id": "intent-123",
            "status": "pending",
            "duplicate": False,
        },
    )
    token = request_identity.set({"access_token": "user-jwt", "user_id": "user-123"})
    try:
        intent = store.begin_workbench_card_redemption("user-123", b"x" * 32, b"cipher")
    finally:
        request_identity.reset(token)

    assert intent["id"] == "intent-123"
    assert intent["status"] == "pending"


def test_usage_cost_exceeding_reservation_is_held_for_review(tmp_path):
    store = Store(tmp_path)
    store.get_workbench_credit_balance("alice")
    card = store.begin_workbench_card_redemption("alice", uuid.uuid4().bytes, b"encrypted")
    store.complete_workbench_card_redemption(card["id"], 1_000_000, 10)
    store.reserve_workbench_usage("alice", "req_12345678", "model-a", 100_000, 55)
    result = store.settle_workbench_usage("req_12345678", 150_000, "wopally-req")
    assert result["status"] == "needs_review"
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 900_000
