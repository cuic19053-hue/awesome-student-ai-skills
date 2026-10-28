"""Real billing RPC verification in an opt-in, disposable PostgreSQL container."""
import json
import os
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UID = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"


@pytest.mark.skipif(os.environ.get("RUN_POSTGRES_POLICY_TESTS") != "1",
                    reason="Opt-in isolated PostgreSQL billing integration")
def test_nonblocking_billing_rpc_preserves_wallet_and_authorization():
    name = "stardust-billing-qa-" + uuid.uuid4().hex[:10]
    subprocess.run(["docker", "run", "--rm", "--pull=never", "--network=none", "-d",
                    "--name", name, "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "postgres:15-alpine"],
                   check=True, capture_output=True, timeout=30)

    def sql(source, ok=True):
        result = subprocess.run(
            ["docker", "exec", "-i", name, "psql", "-U", "postgres", "-Atq",
             "-v", "ON_ERROR_STOP=1"],
            input=source, text=True, capture_output=True, timeout=30)
        if ok:
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode != 0, result.stdout
        return result.stdout.strip()

    def reserve(request_id, user=UID, secret="a" * 64, ok=True):
        return sql(f"""
          set role authenticated;
          set request.jwt.claim.sub='{UID}';
          select public.workbench_backend_reserve_usage(
            '{user}', '{request_id}', 'deepseek-v4-flash', 200000, 692, '{secret}');
        """, ok=ok)

    try:
        for _ in range(80):
            result = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                capture_output=True, timeout=5)
            if result.returncode == 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("PostgreSQL did not start")
        sql("""
          create role anon; create role authenticated; create role service_role bypassrls;
          create schema auth; create table auth.users(id uuid primary key);
          create function auth.uid() returns uuid language sql stable as $$
            select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
          grant usage on schema auth to anon, authenticated, service_role;
        """)
        for migration in (
            "20261011173308_workbench_credit_ledger.sql",
            "20261012120000_workbench_backend_capability.sql",
            "20261012123000_workbench_single_inflight.sql",
        ):
            sql((ROOT / "supabase/migrations" / migration).read_text())
        sql(f"""
          update public.workbench_backend_capability
            set secret_hash=sha256(convert_to(repeat('a',64),'UTF8'));
          insert into auth.users values ('{UID}'), ('{OTHER}');
          select public.workbench_grant_payment_credits('{UID}','billing-qa-payment',1000000);
        """)
        reserve("original-request")
        reserve("blocked-request", ok=False)  # Reproduce the previous user-visible lock.
        migration = next((ROOT / "supabase/migrations").glob("*_workbench_nonblocking_reconciliation.sql"))
        sql(migration.read_text())
        sql(migration.read_text())  # Safe to reapply.
        reserve("allowed-request")
        assert json.loads(reserve("allowed-request"))["duplicate"] is True
        sql("select public.workbench_settle_usage('original-request',250000,'receipt-1')")
        reserve("review-does-not-block")
        reserve("wrong-user-request", user=OTHER, ok=False)
        reserve("wrong-secret-request", secret="b" * 64, ok=False)
        sql(f"""set role anon; select public.workbench_backend_reserve_usage(
          '{UID}','anonymous-request','model',200000,692,repeat('a',64))""", ok=False)
        sql(f"""set role authenticated; select public.workbench_backend_reserve_usage(
          '{UID}','missing-identity','model',200000,692,repeat('a',64))""", ok=False)

        def parallel(index):
            try:
                reserve(f"concurrent-request-{index}")
                return True
            except AssertionError:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            assert sum(pool.map(parallel, range(8))) == 2
        assert sql(f"select balance_micro_cny from workbench_credit_wallets where user_id='{UID}'") == "0"
        assert sql("select count(*) from workbench_usage_events") == "5"
        assert sql("select count(*) from workbench_credit_transactions where kind='usage_reserve'") == "5"
        assert sql("select status from workbench_usage_events where request_id='original-request'") == "needs_review"
        assert sql("select count(*) from workbench_credit_transactions where kind='usage_refund'") == "0"
        assert sql(f"""set role authenticated; set request.jwt.claim.sub='{OTHER}';
          select count(*) from workbench_usage_events""") == "0"

        # The background worker is independently authenticated and never
        # treats an absent receipt as proof of a zero-cost request.
        worker_migration = next((ROOT / "supabase/migrations").glob("*_billing_reconciliation_worker.sql"))
        sql(worker_migration.read_text())
        sql("""
          insert into billing_private.worker_capability(secret_hash)
          values(sha256(convert_to(repeat('b',64),'UTF8')));
          update public.workbench_usage_events set created_at=now()-interval '2 hours'
          where request_id in ('original-request','allowed-request');
        """)

        def worker(action, args=None, worker_secret="b" * 64, backend_secret="a" * 64, ok=True):
            payload = json.dumps(args or {}).replace("'", "''")
            return sql(f"""set role anon;
              select public.billing_reconciliation_worker(
                '{backend_secret}','{worker_secret}','{action}','{payload}'::jsonb);""", ok=ok)

        worker("claim", worker_secret="c" * 64, ok=False)
        worker("claim", backend_secret="c" * 64, ok=False)
        sql("set role anon; select * from billing_private.reconciliation_queue", ok=False)
        job = json.loads(worker("claim"))
        assert job["status"] == "claimed" and job["request_id"] == "allowed-request"
        assert json.loads(worker("claim"))["status"] == "idle"
        args = {"request_id": job["request_id"], "lease_id": job["lease_id"]}
        wrong_lease = {**args, "lease_id": str(uuid.uuid4())}
        assert json.loads(worker("complete", {**wrong_lease, "actual_micro_cny": 10000,
                                               "provider_request_id": "provider-1"}))["status"] == "lease_expired"
        assert json.loads(worker("complete", {**args, "actual_micro_cny": 10000,
                                              "provider_request_id": "provider-1"}))["status"] == "settled"
        assert json.loads(worker("complete", {**args, "actual_micro_cny": 10000,
                                              "provider_request_id": "provider-1"}))["status"] == "lease_expired"
        assert sql(f"select balance_micro_cny from workbench_credit_wallets where user_id='{UID}'") == "190000"
        assert json.loads(worker("alerts"))["alert_count"] == 1  # needs_review
        assert json.loads(worker("alerts"))["alert_count"] == 0  # no alert flood
        sql("""update public.workbench_usage_events set created_at=now()-interval '3 minutes'
          where request_id='review-does-not-block';""")
        pending = json.loads(worker("claim"))
        assert pending["request_id"] == "review-does-not-block"
        assert json.loads(worker("defer", {"request_id": pending["request_id"],
          "lease_id": pending["lease_id"], "reason": "receipt_not_found"}))["status"] == "deferred"
        assert sql("select status from workbench_usage_events where request_id='review-does-not-block'") == "reserved"
        assert sql("select count(*) from workbench_credit_transactions where kind='usage_refund'") == "0"
        assert json.loads(worker("claim"))["status"] == "idle"  # exponential backoff
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
