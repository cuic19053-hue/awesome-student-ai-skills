"""Isolated PostgreSQL only: capability, stable membership, receipts and retention."""
import hashlib
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_material_postgres import ROOT, UID, sql, submit, worker

API_KEY = "synthetic-api-capability-" + "a" * 32
OPS_KEY = "synthetic-ops-capability-" + "b" * 32
UPLOAD_KEY = "synthetic-upload-capability-" + "c" * 32


@pytest.fixture
def obs(sql):
    sql("""create table public.workbench_credit_transactions(
      id uuid default gen_random_uuid(), user_id uuid, request_id text, kind text);""")
    sql(next((ROOT / "supabase/migrations").glob("*_observability_events_and_archive.sql")).read_text())
    for scope, key in (("api", API_KEY), ("ops", OPS_KEY), ("upload", UPLOAD_KEY)):
        sql(f"insert into observability.capabilities values('{scope}',sha256(convert_to('{key}','UTF8')),'{scope}',true)")
    sql("update observability.config set enabled=true,soft_bytes=1000000000000,hard_bytes=1000000000001")
    return sql


def call(sql, action, args=None, key=OPS_KEY, ok=True):
    result = sql(f"set role anon; select public.observability_api('{key}','{action}','{json.dumps(args or {})}');", ok=ok)
    return json.loads(result) if ok and result else None


def event(**changes):
    return {"event_id": str(uuid.uuid4()), "trace_id": "a" * 32,
            "occurred_at": "2026-10-25T00:00:00Z", "event": "model.completed",
            "stage": "response_received", "status": "completed", "level": "info",
            "owner_id": UID, "metadata": {"prompt_tokens": 12}, **changes}


def append(sql, e):
    return call(sql, "append", {"events": [e]}, key=API_KEY)


def old(sql):
    sql("update observability.task_events set ingested_at=now()-interval '31 days' where archive_batch_id is null")


def receipt(batch, **changes):
    return {"batch_id": batch["id"], "event_count": batch["event_count"],
            "plaintext_sha256": batch["plaintext_sha256"],
            "ciphertext_sha256": "e" * 64, "key_id": "f" * 32, **changes}


def test_capabilities_rls_whitelist_and_dedup(obs):
    for role in ("anon", "authenticated"):
        obs(f"set role {role}; select * from observability.task_events", ok=False)
        obs(f"set role {role}; insert into observability.config values(false)", ok=False)
    call(obs, "list", key="x" * 40, ok=False)
    call(obs, "append", {"events": [event()]}, ok=False)  # ops cannot write
    call(obs, "list", key=API_KEY, ok=False)
    call(obs, "purge", key=UPLOAD_KEY, ok=False)
    call(obs, "append", {"events": [event()]}, key=UPLOAD_KEY, ok=False)
    for metadata in ({"body": "private"}, {"mime_type": {"key": "secret"}},
                     {"url": "https://signed.test/?token=secret"}, {"filename": "private.docx"}):
        call(obs, "append", {"events": [event(metadata=metadata)]}, key=API_KEY, ok=False)
    e = event()
    assert append(obs, e) == {"written": 1}
    assert append(obs, e) == {"written": 1}
    rows = call(obs, "list")["events"]
    assert len(rows) == 1 and "archive_batch_id" not in rows[0]
    assert rows[0]["component"] == "api"
    assert "private" not in json.dumps(rows)


def test_stable_batch_late_arrivals_and_receipt_idempotency(obs):
    append(obs, event())
    old(obs)
    batch = call(obs, "claim")
    # A record committed after claim never joins an existing batch.
    late = event()
    append(obs, late)
    old(obs)
    assert call(obs, "claim")["id"] == batch["id"]
    page = call(obs, "page", {"batch_id": batch["id"], "offset": 0})
    raw = ("\n".join(page["lines"]) + "\n").encode()
    assert hashlib.sha256(raw).hexdigest() == batch["plaintext_sha256"]
    assert len(page["lines"]) == 1
    for args in ({"batch_id": batch["id"]}, receipt(batch, plaintext_sha256="0" * 64),
                 receipt(batch, event_count=None)):
        call(obs, "ack", args, ok=False)
    assert call(obs, "purge") == {"deleted": 0}
    assert call(obs, "ack", receipt(batch)) == {"verified": True}
    assert call(obs, "ack", receipt(batch)) == {"verified": True}
    call(obs, "ack", receipt(batch, ciphertext_sha256="d" * 64), ok=False)
    second = call(obs, "claim")
    assert second["id"] != batch["id"] and second["event_count"] == 1


def test_purge_only_verified_old_events_and_never_business_records(obs):
    append(obs, event())
    old(obs)
    batch = call(obs, "claim")
    append(obs, event())  # recent, not archived
    call(obs, "ack", receipt(batch))
    assert call(obs, "purge")["deleted"] == 1
    assert len(call(obs, "list")["events"]) == 1
    assert obs("select count(*) from projects") == "2"
    assert obs("select count(*) from workbench_credit_transactions") == "0"
    # Recent verified records must also remain.
    obs("update observability.task_events set ingested_at=now()-interval '3 minutes'")
    recent = call(obs, "claim")
    call(obs, "ack", receipt(recent))
    assert call(obs, "purge")["deleted"] == 0


def test_worker_lease_and_capacity_fail_open(obs):
    job_id = "a" * 32
    project_id = "b" * 32
    obs(f"insert into projects(id,owner_id) values('{project_id}','{UID}')")
    submit(obs, project_id="b" * 32)
    job = worker(obs, "claim")
    payload = json.dumps(event(event="task.checkpoint", stage="model_request"))
    statement = f"select public.observability_worker_event('worker-test-secret','{job_id}','{job['lease']}','{payload}')"
    assert obs("set role anon; " + statement) == "t"
    obs("set role anon; " + statement.replace(job["lease"], "0" * 32), ok=False)
    obs(f"set role anon; select public.observability_worker_event('worker-test-secret','{job_id}','{job['lease']}',null)", ok=False)
    row = [e for e in call(obs, "list")["events"] if e["component"] == "worker"][0]
    assert row["owner_id"] == UID and row["job_id"] == job_id
    obs("update observability.config set hard_bytes=1")
    assert append(obs, event()) == {"written": 0}
    # Logging errors cannot roll back business commits.
    worker(obs, "checkpoint", job, step="still_working")
    assert obs(f"select step from material_jobs where id='{job_id}'") == "still_working"
    obs(f"insert into workbench_credit_transactions(user_id,kind) values('{UID}','card_redeem')")
    assert obs("select count(*) from workbench_credit_transactions") == "1"


def test_concurrent_commit_cannot_disappear_behind_archive_cursor(obs):
    append(obs, event())
    old(obs)
    late = event()
    query = f"""begin; set role anon;
      select public.observability_api('{API_KEY}','append','{json.dumps({"events": [late]})}');
      reset role;
      update observability.task_events set ingested_at=now()-interval '31 days'
        where event_id='{late["event_id"]}';
      select pg_sleep(2) /* observability_late_commit_test */; commit;"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(obs, query)
        for _ in range(50):
            if obs("""select count(*) from pg_stat_activity where wait_event='PgSleep'
                and query like '%observability_late_commit_test%'""") != "0":
                break
            time.sleep(.02)
        else:
            pytest.fail("late transaction never reached commit barrier")
        batch = call(obs, "claim")
        assert batch["event_count"] == 1
        future.result()
    assert call(obs, "claim")["id"] == batch["id"]
    call(obs, "ack", receipt(batch))
    next_batch = call(obs, "claim")
    lines = call(obs, "page", {"batch_id": next_batch["id"], "offset": 0})["lines"]
    assert len(lines) == 1 and json.loads(lines[0])["event_id"] == late["event_id"]


def test_batch_limit_page_limit_and_capacity_thresholds(obs):
    append(obs, event())
    obs("""insert into observability.task_events(event_id,ingested_at,occurred_at,trace_id,
      event,operation,stage,status,level,component,version,environment,metadata)
      select gen_random_uuid(),now()-interval '31 days',now(),'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'model.completed','model','invoke','completed','info','api','unknown','test','{}'
      from generate_series(1,5001)""")
    b = call(obs, "claim")
    assert b["event_count"] == 5000
    assert len(call(obs, "page", {"batch_id": b["id"], "offset": 0})["lines"]) == 200
    assert len(call(obs, "page", {"batch_id": b["id"], "offset": 5000})["lines"]) == 0
    obs("update observability.config set soft_bytes=1")
    assert append(obs, event())["written"] == 0
    assert append(obs, event(status="failed", level="error", error_code="UPSTREAM_FAILED"))["written"] == 1
    assert call(obs, "stats")["unarchived"] >= 1
