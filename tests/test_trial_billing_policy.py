from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

import server.app as app
from fastapi.testclient import TestClient
from proposal.billing_policy import TRIAL_REGISTRATION_CUTOFF, normalize_trial_wallet
from proposal.storage import Store
from proposal.supabase_store import SupabaseStore, request_identity

CUTOFF = datetime.fromisoformat(TRIAL_REGISTRATION_CUTOFF)
OLD = (CUTOFF - timedelta(seconds=1)).isoformat()
NEW = (CUTOFF + timedelta(seconds=1)).isoformat()


@pytest.mark.parametrize("registered_at,expected", [
    (OLD, 0), (TRIAL_REGISTRATION_CUTOFF, 0), (NEW, 3),
    ("", 0), ("invalid", 0), ("2026-10-18", 0),
])
def test_registration_cutoff_is_fixed_and_inclusive(registered_at, expected):
    wallet = {"free_chat_count": 3, "created_at": NEW}
    result = normalize_trial_wallet(wallet, registered_at=registered_at, require_registration=True)
    assert result["free_chat_count"] == expected


@pytest.mark.parametrize("field", [
    "balance_micro_cny", "total_credited_micro_cny", "total_spent_micro_cny",
])
def test_any_credit_history_disables_trial_even_if_balance_is_now_zero(field):
    wallet = {"free_chat_count": 3, "created_at": NEW, field: 1}
    result = normalize_trial_wallet(wallet)
    assert result["free_chat_count"] == 0
    assert result["trial_eligible"] is False


def test_sqlite_legacy_user_loses_only_free_count_and_never_gets_it_back(tmp_path):
    store = Store(tmp_path)
    store.grant_workbench_payment_credits("old", "old-payment", 1_000_000)
    with store.connect() as db:
        db.execute(
            "UPDATE workbench_credit_wallets SET created_at=?, free_chat_count=3 WHERE user_id='old'",
            (OLD,),
        )
    before = store.get_workbench_credit_balance("old")
    assert before["free_chat_count"] == 0
    assert before["balance_micro_cny"] == 1_000_000
    assert store.consume_free_chat("old") == -1
    assert store.refund_free_chat("old") == 0
    store = Store(tmp_path)  # Reinitialization must not re-grant anything.
    assert store.get_workbench_credit_balance("old") == before


def test_old_unfunded_user_does_not_get_a_trial(tmp_path):
    store = Store(tmp_path)
    store.get_workbench_credit_balance("old")
    with store.connect() as db:
        db.execute("UPDATE workbench_credit_wallets SET created_at=? WHERE user_id='old'", (OLD,))
    assert store.get_workbench_credit_balance("old")["free_chat_count"] == 0
    assert store.consume_free_chat("old") == -1
    assert store.refund_free_chat("old") == 0


def test_new_user_has_exactly_three_free_turns_and_payment_permanently_switches_mode(tmp_path):
    store = Store(tmp_path)
    assert store.get_workbench_credit_balance("new")["free_chat_count"] == 3
    assert store.consume_free_chat("new") == 2
    assert store.refund_free_chat("new") == 3  # Restore only this failed attempt.
    assert [store.consume_free_chat("new") for _ in range(4)] == [2, 1, 0, -1]
    store.grant_workbench_payment_credits("new", "new-payment", 1_000_000)
    assert store.refund_free_chat("new") == 0
    assert store.consume_free_chat("new") == -1
    request_id = "request-spend-all"
    store.reserve_workbench_usage("new", request_id, "deepseek-v4-flash", 1_000_000, 684)
    store.settle_workbench_usage(request_id, 1_000_000, "test-usage")
    balance = store.get_workbench_credit_balance("new")
    assert balance["balance_micro_cny"] == 0
    assert balance["free_chat_count"] == 0
    assert balance["trial_eligible"] is False


def test_payment_before_trial_exhaustion_and_late_failure_cannot_restore_trial(tmp_path):
    store = Store(tmp_path)
    assert store.consume_free_chat("new") == 2
    store.grant_workbench_payment_credits("new", "first-payment", 1_000_000)
    assert store.get_workbench_credit_balance("new")["free_chat_count"] == 0
    assert store.refund_free_chat("new") == 0
    assert store.get_workbench_credit_balance("new")["balance_micro_cny"] == 1_000_000


def test_free_turns_are_atomic_across_concurrent_requests(tmp_path):
    store = Store(tmp_path)
    store.get_workbench_credit_balance("new")
    with ThreadPoolExecutor(max_workers=8) as pool:
        remaining = list(pool.map(lambda _: store.consume_free_chat("new"), range(8)))
    assert sorted(remaining) == [-1, -1, -1, -1, -1, 0, 1, 2]


@pytest.mark.parametrize("registered_at,credited,expected", [
    (OLD, 0, 0), (NEW, 0, 3), (NEW, 1_000_000, 0),
])
def test_cloud_uses_verified_auth_registration_not_wallet_creation_time(
    tmp_path, monkeypatch, registered_at, credited, expected
):
    store = SupabaseStore("https://example.supabase.co", "public", tmp_path)
    row = {
        "user_id": "owner", "free_chat_count": 3, "created_at": NEW,
        "balance_micro_cny": 0, "total_credited_micro_cny": credited, "total_spent_micro_cny": 0,
    }
    monkeypatch.setattr(store, "_rest", lambda *_args, **_kwargs: [row])
    context = request_identity.set({
        "user_id": "owner", "access_token": "fake", "registered_at": registered_at,
    })
    try:
        assert store.get_workbench_credit_balance()["free_chat_count"] == expected
    finally:
        request_identity.reset(context)


def test_missing_cloud_wallet_or_registration_does_not_invent_free_turns(tmp_path, monkeypatch):
    store = SupabaseStore("https://example.supabase.co", "public", tmp_path)
    monkeypatch.setattr(store, "_rest", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(store, "_service_rpc", lambda *_args: pytest.fail("No free RPC for missing wallet"))
    context = request_identity.set({"user_id": "old", "access_token": "fake", "registered_at": OLD})
    try:
        assert store.get_workbench_credit_balance()["free_chat_count"] == 0
        assert store.consume_free_chat("old") == -1
    finally:
        request_identity.reset(context)


@pytest.mark.parametrize("registered_at,recharge", [(OLD, False), (OLD, True), (NEW, True)])
def test_old_and_recharged_accounts_never_use_free_chat_branch(
    tmp_path, monkeypatch, registered_at, recharge
):
    store = Store(tmp_path)
    store.get_workbench_credit_balance("local_user")
    with store.connect() as db:
        db.execute(
            "UPDATE workbench_credit_wallets SET created_at=? WHERE user_id='local_user'",
            (registered_at,),
        )
    if recharge:
        store.grant_workbench_payment_credits("local_user", "test-payment", 1_000_000)
    project = store.create_project(title="计费模式回归")
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "_platform_bundle_ready", lambda: False)
    monkeypatch.setattr(store, "consume_free_chat", lambda *_: pytest.fail("Must not consume free turns"))
    monkeypatch.setattr(app, "_metered_invoke", lambda *_: {"message": "paid response"})
    with TestClient(app.app) as client:
        balance = client.get("/api/user/balance").json()
        assert balance["free_chats_remaining"] == 0
        assert balance["billing_mode"] == "credits"
        response = client.post(
            f"/api/projects/{project['id']}/chat",
            json={"message": "test", "llm_config": {"provider": "preset"}},
        )
    assert response.status_code == 200
    assert response.json()["free_chat"] is False
    assert response.json()["free_chats_remaining"] == 0
