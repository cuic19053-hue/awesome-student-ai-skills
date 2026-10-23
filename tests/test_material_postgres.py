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
