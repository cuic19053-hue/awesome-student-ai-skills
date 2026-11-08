"""Real migration/RLS/lease/CAS tests, isolated Docker PostgreSQL only."""
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UID = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
JOB = "a" * 32
SUBMIT_SECRET = "isolated-test-submission-capability-0123456789"


def test_archive_mime_migration_is_private_size_preserving_and_idempotent(sql):
    sql("""create schema storage;
      create table storage.buckets(id text primary key,public boolean,
        file_size_limit bigint,allowed_mime_types text[]);
      insert into storage.buckets values
        ('stardust-project-files',false,50000000,array['application/pdf','image/png']),
        ('unrelated',false,100,array['text/plain']);""")
    migration = next((ROOT / "supabase/migrations").glob("*_allow_material_export_archives.sql")).read_text()
    sql(migration)
    sql(migration)
    result = sql("""select public||'|'||file_size_limit||'|'||array_to_string(allowed_mime_types,',')
      from storage.buckets where id='stardust-project-files'""")
    assert result == "false|50000000|application/pdf,image/png,application/zip"
    assert sql("select array_to_string(allowed_mime_types,',') from storage.buckets where id='unrelated'") == "text/plain"


@pytest.fixture
def sql():
    if os.environ.get("RUN_POSTGRES_POLICY_TESTS") != "1":
        pytest.skip("Opt-in temporary PostgreSQL; never connects to production")
    name = "stardust-material-qa-" + uuid.uuid4().hex[:10]
    subprocess.run(["docker","run","--rm","--pull=never","--network=none","-d",
        "--name",name,"-e","POSTGRES_HOST_AUTH_METHOD=trust","postgres:15-alpine"],
        check=True,capture_output=True,timeout=30)
    def run(source, ok=True):
        result = subprocess.run(["docker","exec","-i",name,"psql","-U","postgres","-Atq","-v","ON_ERROR_STOP=1"],
            input=source,capture_output=True,text=True,timeout=30)
        if ok:
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode != 0, result.stdout
        return result.stdout.strip()
    try:
        for _ in range(80):
            probe = subprocess.run(["docker","exec",name,"pg_isready","-h","127.0.0.1","-U","postgres"],capture_output=True)
            if probe.returncode == 0:
                break
            time.sleep(.1)
        run("""
        create role anon; create role authenticated;
        create schema auth; create table auth.users(id uuid primary key);
        create function auth.uid() returns uuid language sql stable as $$
          select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
        grant usage on schema auth to anon,authenticated;
        create table public.projects(
          id text primary key,owner_id uuid references auth.users(id),title text default '',
          school text default '',level text default '',discipline text default '',
          state_json jsonb default '{}',outline_json jsonb default '[]',
          sections_json jsonb default '{}',diagrams_json jsonb default '[]',
          template_document_id text,updated_at timestamptz default now());
        alter table public.projects enable row level security;
        grant select,insert,update,delete on public.projects to authenticated;
        create policy owners on public.projects for all to authenticated
         using(owner_id=(select auth.uid())) with check(owner_id=(select auth.uid()));
        create function public.workbench_reserve_usage(uuid,text,text,bigint,bigint) returns jsonb
          language sql as $$ select jsonb_build_object('status','reserved','user_id',$1) $$;
        create function public.workbench_settle_usage(text,bigint,text) returns jsonb
          language sql as $$ select '{"status":"settled"}'::jsonb $$;
        create function public.workbench_refund_usage(text,text) returns jsonb
          language sql as $$ select '{"status":"refunded"}'::jsonb $$;
        """)
        run((ROOT/"supabase/migrations/20261022154243_material_pipeline.sql").read_text())
        run((ROOT/"supabase/migrations/20261023143437_enable_worker_capability_rls.sql").read_text())
        run((ROOT/"supabase/migrations/20261023164211_material_worker_context.sql").read_text())
        run((ROOT/"supabase/migrations/20261023165858_authorize_worker_byok_calls.sql").read_text())
        run(next((ROOT/"supabase/migrations").glob("*_material_pipeline_all_skills.sql")).read_text())
        run(f"""
         insert into auth.users values('{UID}'),('{OTHER}');
         insert into public.projects(id,owner_id,sections_json) values('p','{UID}','{{"abstract":"old"}}'),('other','{OTHER}','{{}}');
         insert into material_private.worker_capability values(true,sha256(convert_to('worker-test-secret','UTF8')));
        """)
        yield run
    finally:
        subprocess.run(["docker","rm","-f",name],capture_output=True,timeout=20)


def as_user(source, uid=UID):
    return f"set role authenticated; set request.jwt.claim.sub='{uid}'; {source}"


def submit(sql, **changes):
    args = {"id":JOB,"project_id":"p","kind":"section","target":"abstract","idempotency":"click",
            "payload":{"paid":True,"platform":True,"base_revision":0}}
    args.update(changes)
    return json.loads(sql(as_user(f"select public.material_jobs_api('submit','{json.dumps(args)}');")))


def worker(sql, action, job=None, **args):
    params = {**({"id":job["id"],"lease":job["lease"]} if job else {}),**args}
    result = sql(f"set role anon; select public.material_worker_rpc('worker-test-secret','{action}','{json.dumps(params)}');")
    return json.loads(result) if result else None


@pytest.fixture
def hardened_sql(sql):
    sql((ROOT / "supabase/migrations/20261108010000_harden_material_job_authority.sql").read_text())
    sql("insert into material_private.submit_capability values"
        f"(true,sha256(convert_to('{SUBMIT_SECRET}','UTF8')));")
    return sql


def hardened_call(sql, action, args, *, secret=SUBMIT_SECRET, uid=UID, ok=True):
    secret_arg = "null" if secret is None else "'" + secret + "'"
    result = sql(as_user(f"select public.material_jobs_api('{action}','{json.dumps(args)}',{secret_arg});", uid), ok=ok)
    return json.loads(result) if result else None


def hardened_submit(sql, **changes):
    args = {"id": JOB, "project_id": "p", "kind": "section", "target": "abstract", "idempotency": "click",
            "payload": {"paid": True, "platform": True, "base_revision": 0}}
    args.update(changes)
    return hardened_call(sql, "submit", args)


def test_sql_ownership_idempotency_and_cas(sql):
    first = submit(sql)
    assert submit(sql)["id"] == first["id"]
    sql(as_user("select public.material_jobs_api('get','{\"project_id\":\"p\",\"id\":\""+JOB+"\"}');", OTHER),ok=False)
    assert sql(as_user("select count(*) from public.material_jobs;",OTHER)) == "0"
    sql("set role anon; select public.material_jobs_api('list','{\"project_id\":\"p\"}');",ok=False)
    result = json.loads(sql(as_user("select public.material_patch('p',0,'{\"sections\":{\"abstract\":\"human\"}}');")))
    assert result["material_revision"] == 1
    conflict = json.loads(sql(as_user("select public.material_patch('p',0,'{\"sections\":{\"abstract\":\"lost\"}}');")))
    assert conflict["conflict"]
    assert sql("select sections_json->>'abstract' from projects where id='p'") == "human"


def test_catalogue_job_types_and_owner_isolation(sql):
    skills = json.loads((ROOT / "index.json").read_text())["skills"]
    assert len(skills) == 35
    for index, skill in enumerate(skills):
        project = f"skill_{index}"
        sql(f"insert into public.projects(id,owner_id,state_json) values"
            f"('{project}','{UID}', '{{\"skill_id\":\"{skill['name']}\"}}');")
        args = {"id": f"{index:032x}", "project_id": project, "kind": "export",
                "target": "", "idempotency": "one", "payload": {"base_revision": 0}}
        result = json.loads(sql(as_user(f"select public.material_jobs_api('submit','{json.dumps(args)}');")))
        assert result["id"] == args["id"]
        sql(as_user(f"select public.material_jobs_api('list','{json.dumps({'project_id': project})}');", OTHER),
            ok=False)
    sql(f"insert into public.projects(id,owner_id,state_json) values"
        f"('unknown','{UID}', '{{\"skill_id\":\"unknown-skill\"}}');")
    args = {"id": "f" * 32, "project_id": "unknown", "kind": "export",
            "target": "", "idempotency": "one", "payload": {"base_revision": 0}}
    sql(as_user(f"select public.material_jobs_api('submit','{json.dumps(args)}');"), ok=False)


def test_worker_capability_budget_lease_and_cross_job_metering(sql):
    submit(sql)
    sql("set role anon; select public.material_worker_rpc('bad','claim','{}');",ok=False)
    job = worker(sql,"claim")
    assert job["status"] == "running"
    assert worker(sql,"claim") is None
    result = worker(sql,"reserve",job,request_id="o2x1_test",model="deepseek-v4-flash",api_key_id=127)
    assert result["status"] == "reserved"
    sql("set role anon; select public.material_worker_rpc('worker-test-secret','settle',"
        f"'{{\"id\":\"{JOB}\",\"lease\":\"{job['lease']}\",\"request_id\":\"someone-else\",\"amount\":1}}');",ok=False)
    sql(f"update material_jobs set lease_until=now()-interval '1 second' where id='{JOB}'")
    assert worker(sql,"claim") is None
    assert sql(f"select status from material_jobs where id='{JOB}'") == "needs_review"


def test_owner_cannot_directly_requeue_job_or_clear_call_budget(hardened_sql):
    sql = hardened_sql
    hardened_submit(sql)
    job = worker(sql, "claim")
    worker(sql, "reserve", job, request_id="o2x1_test", model="deepseek-v4-flash", api_key_id=127)
    # A project owner may observe a job, but execution state and the billing
    # call list must only be modified by a trusted, lease-checked worker.
    sql(as_user(f"update public.material_jobs set status='pending', calls='[]'::jsonb, "
                f"lease=null, lease_until=null where id='{JOB}';"), ok=False)


def test_owner_cannot_submit_paid_job_payload_directly_to_rpc(hardened_sql):
    sql = hardened_sql
    args = {"id": JOB, "project_id": "p", "kind": "section", "target": "abstract", "idempotency": "direct",
            "payload": {"paid": True, "platform": True, "base_revision": 0}}
    # No trusted application-side confirmation or signed snapshot exists here.
    sql(as_user(f"select public.material_jobs_api('submit','{json.dumps(args)}');"), ok=False)


def test_hardened_submit_read_apply_and_revision_permissions(hardened_sql):
    sql = hardened_sql
    job = hardened_submit(sql)
    assert hardened_submit(sql)["id"] == job["id"]
    assert hardened_call(sql, "find", {"project_id": "p", "idempotency": "click"}, secret=None)["id"] == JOB
    public = hardened_call(sql, "get", {"project_id": "p", "id": JOB}, secret=None)
    assert not {"payload", "calls", "lease", "trusted_submission"} & public.keys()
    assert hardened_call(sql, "list", {"project_id": "p"}, secret=None)[0]["id"] == JOB
    sql(as_user("select * from public.material_jobs;"), ok=False)
    sql(as_user(f"select public.material_jobs_api('raw','{{\"project_id\":\"p\",\"id\":\"{JOB}\"}}');"), ok=False)
    hardened_call(sql, "raw", {"project_id": "p", "id": JOB}, secret="incorrect", ok=False)
    hardened_call(sql, "raw", {"project_id": "p", "id": JOB}, uid=OTHER, ok=False)
    assert hardened_call(sql, "raw", {"project_id": "p", "id": JOB})["payload"]["paid"]
    claimed = worker(sql, "claim")
    worker(sql, "finish", claimed, status="completed", result={"content": "AI content"})
    # A user may save their own manual version but cannot preempt a worker job ID.
    sql(as_user("insert into public.material_revisions(project_id,section_id,content,source) "
                "values('p','abstract','manual','user_edit');"))
    sql(as_user("insert into public.material_revisions(project_id,section_id,content,source,job_id) "
                f"values('p','abstract','forged','ai_generated','{JOB}');"), ok=False)
    sql(as_user("select public.material_patch('p',0,'{\"sections\":{\"abstract\":\"human edit\"}}');"))
    args = json.dumps({"project_id": "p", "id": JOB, "fields": {"sections": {"abstract": "AI content"}}})
    sql(as_user(f"select public.material_apply('{args}');"), ok=False)
    result = json.loads(sql(as_user(f"select public.material_apply('{args}','{SUBMIT_SECRET}');")))
    assert result["applied"] is True
    assert result["conflict_status"] == "user_edit_preserved"
    assert sql("select sections_json->>'abstract' from public.projects where id='p'") == "human edit"
    assert sql(f"select count(*) from public.material_revisions where job_id='{JOB}'") == "1"
    assert sql(f"select source from public.material_revisions where job_id='{JOB}'") == "ai_generated_alternative"
    sql(as_user(f"select public.material_apply('{args}','{SUBMIT_SECRET}');"))
    assert sql(f"select count(*) from public.material_revisions where job_id='{JOB}'") == "1"
    other_job = "c" * 32
    hardened_submit(sql, id=other_job, idempotency="cancel", target="other", payload={
        "paid": True, "platform": True, "base_revision": 1})
    running = worker(sql, "claim")
    assert running["id"] == other_job
    assert hardened_call(sql, "cancel", {"project_id": "p", "id": other_job}, secret=None)["status"] == "cancelled"
    for action, extra in [("finish", {"status": "completed"}),
                          ("reserve", {"request_id": "cancelled-call", "model": "deepseek-v4-flash"})]:
        params = {"id": other_job, "lease": running["lease"], **extra}
        sql(f"set role anon; select public.material_worker_rpc('worker-test-secret','{action}','{json.dumps(params)}');", ok=False)


def test_hardened_cleanup_paths_are_scoped_paginated_and_minimal(hardened_sql):
    sql = hardened_sql
    prefix = f"{UID}/p/_material/"
    hardened_submit(sql, payload={"base_revision": 0, "output_path": prefix + JOB + ".zip",
                                  "image_path": prefix + JOB + "-image.png", "private": "do not expose"})
    second = "b" * 32
    hardened_submit(sql, id=second, idempotency="other", target="other", payload={
        "base_revision": 0, "output_path": f"{OTHER}/p/_material/{second}.zip",
        "image_path": prefix + "../outside.png"})
    assert hardened_call(sql, "has_jobs", {"project_id": "p"}, secret=None) is True
    assert hardened_call(sql, "has_jobs", {"project_id": "other"}, secret=None, uid=OTHER) is False
    hardened_call(sql, "cleanup_paths", {"project_id": "p"}, secret=None, ok=False)
    hardened_call(sql, "cleanup_paths", {"project_id": "p"}, uid=OTHER, ok=False)
    first = hardened_call(sql, "cleanup_paths", {"project_id": "p", "offset": 0, "limit": 1})
    latter = hardened_call(sql, "cleanup_paths", {"project_id": "p", "offset": 1, "limit": 1})
    assert first == [{"output_path": prefix + JOB + ".zip", "image_path": prefix + JOB + "-image.png"}]
    assert latter == [{"output_path": None, "image_path": None}]
    hardened_call(sql, "cleanup_paths", {"project_id": "p", "limit": 501}, ok=False)


def test_hardening_quarantines_legacy_jobs_and_preserves_completed_result(sql):
    submit(sql)
    running = worker(sql, "claim")
    completed_id = "b" * 32
    sql("insert into public.material_jobs(id,project_id,owner_id,kind,target,idempotency,payload,status,result) "
        f"values('{completed_id}','p','{UID}','section','other','old',"
        "'{\"base_revision\":0}','completed','{\"content\":\"preserved old result\"}');")
    sql((ROOT / "supabase/migrations/20261108010000_harden_material_job_authority.sql").read_text())
    sql("insert into material_private.submit_capability values"
        f"(true,sha256(convert_to('{SUBMIT_SECRET}','UTF8')));")
    assert sql(f"select status||'|'||(lease is null)::text from material_jobs where id='{JOB}'") == "needs_review|true"
    assert sql(f"select status from material_jobs where id='{completed_id}'") == "completed"
    assert worker(sql, "claim") is None
    sql("set role anon; select public.material_worker_rpc('worker-test-secret','finish',"
        f"'{{\"id\":\"{JOB}\",\"lease\":\"{running['lease']}\",\"status\":\"completed\"}}');", ok=False)
    item = hardened_call(sql, "get", {"project_id": "p", "id": completed_id}, secret=None)
    assert item["status"] == "needs_review" and item["result"]["content"] == "preserved old result"
    hardened_call(sql, "raw", {"project_id": "p", "id": completed_id}, ok=False)
    args = json.dumps({"project_id": "p", "id": completed_id, "fields": {}})
    sql(as_user(f"select public.material_apply('{args}','{SUBMIT_SECRET}');"), ok=False)


def test_atomic_apply_preserves_clear_and_creates_one_alternative(sql):
    submit(sql)
    job = worker(sql,"claim")
    worker(sql,"finish",job,status="completed",result={"content":"AI content"})
    sql(as_user("select public.material_patch('p',0,'{\"sections\":{\"abstract\":\"\"}}');"))
    args = json.dumps({"project_id":"p","id":JOB,"revision":0,"fields":{"sections":{"abstract":"AI content"}}})
    result = json.loads(sql(as_user(f"select public.material_apply('{args}');")))
    assert result["conflict_status"] == "user_edit_preserved"
    assert sql("select sections_json->>'abstract' from projects where id='p'") == ""
    assert sql("select source from material_revisions") == "ai_generated_alternative"
    sql(as_user(f"select public.material_apply('{args}');"))
    assert sql("select count(*) from material_revisions") == "1"
    assert sql(as_user("select count(*) from material_revisions",OTHER)) == "0"


def test_cancelled_job_cannot_finish_or_reserve(sql):
    submit(sql)
    job = worker(sql,"claim")
    sql(as_user(f"select public.material_jobs_api('cancel','{{\"project_id\":\"p\",\"id\":\"{JOB}\"}}');"))
    sql("set role anon; select public.material_worker_rpc('worker-test-secret','finish',"
        f"'{{\"id\":\"{JOB}\",\"lease\":\"{job['lease']}\",\"status\":\"completed\"}}');",ok=False)
    assert sql(f"select status from material_jobs where id='{JOB}'") == "cancelled"


def test_worker_context_is_scoped_to_secret_live_lease_and_minimal_payload(sql):
    payload = {
        "paid": True, "platform": False, "base_revision": 0,
        "config_ciphertext": "cipher-only",
        "messages": [{"content": "should-not-return"}],
        "image_upload_url": "https://storage.invalid/upload",
    }
    submit(sql, payload=payload)
    job = worker(sql, "claim")
    result = json.loads(sql(
        "set role anon; select public.material_worker_context("
        f"'worker-test-secret','{JOB}','{job['lease']}');"
    ))
    assert result["owner_id"] == UID
    assert result["payload"]["config_ciphertext"] == "cipher-only"
    assert result["payload"]["image_upload_url"] == "https://storage.invalid/upload"
    assert "messages" not in result["payload"]
    sql("set role anon; select public.material_worker_context("
        f"'wrong-secret','{JOB}','{job['lease']}');", ok=False)
    sql("set role anon; select public.material_worker_context("
        f"'worker-test-secret','{JOB}','{'f' * 32}');", ok=False)
    assert sql("select relrowsecurity::text from pg_class c join pg_namespace n "
               "on n.oid=c.relnamespace where n.nspname='material_private' "
               "and c.relname='worker_capability'") == "true"


def test_byok_worker_calls_are_authorized_once_and_bounded(sql):
    submit(sql, payload={"paid": True, "platform": False, "base_revision": 0})
    job = worker(sql, "claim")
    result = json.loads(sql(
        "set role anon; select public.material_worker_authorize_byok("
        f"'worker-test-secret','{JOB}','{job['lease']}','{'1' * 32}','text');"
    ))
    assert result["ok"]
    sql("set role anon; select public.material_worker_authorize_byok("
        f"'worker-test-secret','{JOB}','{job['lease']}','{'1' * 32}','text');", ok=False)
    for i in range(2, 7):
        sql("set role anon; select public.material_worker_authorize_byok("
            f"'worker-test-secret','{JOB}','{job['lease']}','{i:032x}','text');")
    sql("set role anon; select public.material_worker_authorize_byok("
        f"'worker-test-secret','{JOB}','{job['lease']}','{'7' * 32}','text');", ok=False)


def test_byok_image_call_is_limited_to_one_per_confirmed_figure_job(sql):
    submit(sql, kind="figure", target="scene", payload={
        "paid": True, "platform": False, "base_revision": 0,
        "spec": {"renderer": "gpt"},
    })
    job = worker(sql, "claim")
    result = json.loads(sql(
        "set role anon; select public.material_worker_authorize_byok("
        f"'worker-test-secret','{JOB}','{job['lease']}','{'2' * 32}','image');"
    ))
    assert result["ok"]
    sql("set role anon; select public.material_worker_authorize_byok("
        f"'worker-test-secret','{JOB}','{job['lease']}','{'3' * 32}','image');", ok=False)
