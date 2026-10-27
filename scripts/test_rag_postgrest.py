#!/usr/bin/env python3
"""Exercise RAG RPCs through disposable PostgREST and PostgreSQL containers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUFFIX = uuid.uuid4().hex[:10]
NETWORK = "codex-rag-http-" + SUFFIX
DB = "codex-rag-db-" + SUFFIX
REST = "codex-rag-rest-" + SUFFIX
SECRET = "temporary-test-secret-at-least-32-bytes"
PG_IMAGE = "pgvector/pgvector@sha256:47af0b65960b14f1c6945aa4ccae37836c632e9a6fe0eea9160936e616e5b2e9"
REST_IMAGE = "postgrest/postgrest@sha256:729bf65c733b73f5b52777f0e4b853f22ed73aa67a22d38269d289779b0a8401"
CURL_IMAGE = "curlimages/curl@sha256:58adaa4e8dca9c988bae2aba4ab3434a0bb2da16bbe3f92dec39ec7785166777"


def command(args: list[str], **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def sql(text: str) -> None:
    command(["docker", "exec", "-i", "-e", "PGPASSWORD=temporary-test", DB,
             "psql", "-h", "127.0.0.1", "-U", "postgres", "-v", "ON_ERROR_STOP=1"],
            input=text, text=True, stdout=subprocess.DEVNULL)


def jwt(sub: str, role: str = "authenticated") -> str:
    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = b64(json.dumps({"sub": sub, "role": role, "exp": int(time.time()) + 600}, separators=(",", ":")).encode())
    signature = b64(hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def post(path: str, payload: dict | list, token: str) -> tuple[int, object]:
    result = command(["docker", "run", "--rm", "-i", "--network", NETWORK, CURL_IMAGE,
                      "-sS", "--max-time", "8", "-w", "\n%{http_code}",
                      "-H", "Content-Type: application/json", "-H", f"Authorization: Bearer {token}",
                      "--data-binary", "@-", f"http://{REST}:3000/{path}"],
                     input=json.dumps(payload, ensure_ascii=False), text=True, capture_output=True)
    raw, code = result.stdout.rsplit("\n", 1)
    return int(code), json.loads(raw) if raw else None


def rpc(name: str, payload: dict, token: str) -> tuple[int, object]:
    return post("rpc/" + name, payload, token)


def main() -> None:
    try:
        command(["docker", "network", "create", "--internal", NETWORK], stdout=subprocess.DEVNULL)
        command(["docker", "run", "--rm", "--network", NETWORK, "--name", DB,
                 "-e", "POSTGRES_PASSWORD=temporary-test", "-d", PG_IMAGE], stdout=subprocess.DEVNULL)
        for _ in range(30):
            if subprocess.run(["docker", "exec", DB, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("隔离数据库未启动。")
        sql('''create schema extensions; create schema auth;
create role anon; create role authenticated; create role service_role bypassrls;
create role authenticator login noinherit password 'temporary-test';
grant anon, authenticated, service_role to authenticator;
create function auth.uid() returns uuid language sql stable as $$
 select nullif(current_setting('request.jwt.claims',true)::jsonb->>'sub','')::uuid $$;
grant usage on schema auth to authenticated;
create table public.projects(id text primary key, owner_id uuid not null);
create table public.documents(id text primary key,project_id text not null references public.projects(id),confirmed bool not null,kind text not null,original_name text not null default '',extracted_text text not null default '');
create table public.chunks(id text primary key,project_id text not null references public.projects(id),document_id text not null references public.documents(id),source_name text not null,source_ref text not null,content text not null,embedding_json jsonb not null default '[]'::jsonb,created_at timestamptz not null default now());
alter table public.projects enable row level security; alter table public.documents enable row level security; alter table public.chunks enable row level security;
grant select,insert,update,delete on public.projects,public.documents,public.chunks to authenticated;
create policy own_projects on public.projects for all to authenticated using (owner_id=(select auth.uid())) with check (owner_id=(select auth.uid()));
create policy own_documents on public.documents for all to authenticated using (exists(select 1 from public.projects p where p.id=documents.project_id and p.owner_id=(select auth.uid()))) with check (exists(select 1 from public.projects p where p.id=documents.project_id and p.owner_id=(select auth.uid())));
create policy own_chunks on public.chunks for all to authenticated using (exists(select 1 from public.projects p where p.id=chunks.project_id and p.owner_id=(select auth.uid()))) with check (exists(select 1 from public.projects p where p.id=chunks.project_id and p.owner_id=(select auth.uid())));
''')
        sql((ROOT / "supabase/migrations/20261027051631_rag_project_search.sql").read_text())
        sql((ROOT / "supabase/migrations/20261027053127_rag_public_knowledge.sql").read_text())
        sql('''insert into public.projects values('a','00000000-0000-0000-0000-000000000001'),('b','00000000-0000-0000-0000-000000000002');
insert into public.documents(id,project_id,confirmed,kind,confirmation_origin) values('d1','a',true,'source','user'),('d2','b',true,'source','user'),('d3','a',true,'source','');
update public.documents set original_name='A', extracted_text='用户确认内容' where id='d1';
insert into public.chunks(id,project_id,document_id,source_name,source_ref,content) values('c1','a','d1','A','第1段','图像识别项目'),('c2','b','d2','B','第1段','图像识别项目'),('c3','a','d3','旧资料','第1段','图像识别项目'),('c4','a','d1','A','第2段','只有向量的新材料');
insert into public.rag_chunk_embeddings select 'c1','bge-m3','revision1',array_fill(0.01::real,ARRAY[1024])::extensions.vector;
insert into public.rag_public_sources(id,skill_id,kind,title,school,application_year,source_sha256,published) values('s1','innovation-research','official','学校通知','东南大学',2026,repeat('a',64),true);
insert into public.rag_public_chunks select 'p1','s1','第一条','项目申请条件','bge-m3','revision1',array_fill(0.01::real,ARRAY[1024])::extensions.vector;
''')
        command(["docker", "run", "--rm", "--network", NETWORK, "--name", REST,
                 "-e", f"PGRST_DB_URI=postgres://authenticator:temporary-test@{DB}:5432/postgres",
                 "-e", "PGRST_DB_SCHEMAS=public", "-e", "PGRST_DB_ANON_ROLE=anon",
                 "-e", "PGRST_DB_EXTRA_SEARCH_PATH=public,extensions", "-e", f"PGRST_JWT_SECRET={SECRET}",
                 "-d", REST_IMAGE], stdout=subprocess.DEVNULL)
        owner = jwt("00000000-0000-0000-0000-000000000001")
        other = jwt("00000000-0000-0000-0000-000000000002")
        for _ in range(30):
            try:
                status, _ = rpc("rag_project_search", {"p_project_id":"a", "p_terms":["项目"]}, owner)
                if status == 200:
                    break
            except (subprocess.CalledProcessError, ValueError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError("隔离 PostgREST 未就绪。")
        status, rows = rpc("rag_project_search", {"p_project_id":"a", "p_terms":["图像"]}, owner)
        assert status == 200 and [row["id"] for row in rows] == ["c1"], (status, rows)
        status, rows = rpc("rag_project_search", {"p_project_id":"a", "p_terms":["图像"]}, other)
        assert status == 200 and rows == [], (status, rows)
        status, rows = rpc("rag_project_search", {"p_project_id":"a", "p_terms":["未命中"],
                          "p_embedding":[.01]*1024, "p_model":"bge-m3", "p_model_revision":"revision1"}, owner)
        assert status == 200 and [row["id"] for row in rows] == ["c1"], (status, rows)
        status, rows = rpc("rag_project_search", {"p_project_id":"a", "p_terms":["未命中"],
                          "p_embedding":[.01]*1024, "p_model":"bge-m3", "p_model_revision":"wrong"}, owner)
        assert status == 200 and rows == [], (status, rows)
        status, _ = post("rag_chunk_embeddings", [{"chunk_id":"c4", "model":"bge-m3",
                         "model_revision":"revision1", "embedding":[.01]*1024}], owner)
        assert status in {200, 201, 204}, status
        status, _ = post("rag_chunk_embeddings", [{"chunk_id":"c2", "model":"bge-m3",
                         "model_revision":"revision1", "embedding":[.01]*1024}], owner)
        assert status in {401, 403}, status
        replacement = [{"id":"1"*32, "source_ref":"第1段", "content":"用户确认内容",
                        "embedding_model":"bge-m3", "embedding_revision":"revision1", "embedding":[.01]*1024}]
        status, _ = rpc("rag_replace_project_chunks",
                        {"p_document_id":"d1", "p_expected_sha256":"0"*64, "p_chunks":replacement}, owner)
        assert status == 409, status
        status, rows = rpc("rag_project_search", {"p_project_id":"a", "p_terms":["图像"]}, owner)
        assert status == 200 and [row["id"] for row in rows] == ["c1"], (status, rows)
        text_hash = hashlib.sha256("用户确认内容".encode()).hexdigest()
        status, count = rpc("rag_replace_project_chunks",
                            {"p_document_id":"d1", "p_expected_sha256":text_hash, "p_chunks":replacement}, owner)
        assert status == 200 and count == 1, (status, count)
        status, _ = rpc("rag_replace_project_chunks",
                        {"p_document_id":"d2", "p_expected_sha256":text_hash, "p_chunks":replacement}, owner)
        assert status in {401, 403}, status
        public = {"p_skill_id":"innovation-research", "p_school":"东南大学", "p_year":2026,
                  "p_terms":["申请"], "p_filters":{}, "p_variant":"", "p_official_only":True}
        status, rows = rpc("rag_search_public_knowledge", public, owner)
        assert status == 200 and [row["id"] for row in rows] == ["p1"], (status, rows)
        status, rows = rpc("rag_search_public_knowledge", {**public, "p_school":"其他大学"}, owner)
        assert status == 200 and rows == [], (status, rows)
        status, rows = rpc("rag_search_public_knowledge", {**public, "p_terms":["未命中"],
                           "p_embedding":[.01]*1024, "p_embedding_revision":"revision1"}, owner)
        assert status == 200 and [row["id"] for row in rows] == ["p1"], (status, rows)
        status, _ = rpc("rag_publish_public_source", {"p_source":{}, "p_chunks":[]}, owner)
        assert status in {401, 403, 404}, status
        service = jwt("00000000-0000-0000-0000-000000000001", "service_role")
        source = {"id":"s2", "skill_id":"national-scholarship", "kind":"official", "title":"规则",
                  "school":"河南大学", "application_year":2026, "source_sha256":"b"*64}
        chunks = [{"id":"p2", "source_ref":"第一条", "content":"申请条件", "embedding_model":"bge-m3",
                   "embedding_revision":"revision1", "embedding":[.01]*1024}]
        status, count = rpc("rag_publish_public_source", {"p_source":source,"p_chunks":chunks}, service)
        assert status == 200 and count == 1, (status, count)
        example = {"id":"e1", "skill_id":"national-scholarship", "kind":"example", "title":"已授权范例",
                   "source_url":"https://example.edu.cn/example", "school":"河南大学", "application_year":2026,
                   "source_sha256":"c"*64, "license":"CC-BY", "rights_evidence_url":"https://example.edu.cn/license",
                   "rights_review_status":"no_conflict", "approval_reference":"review-test", "privacy_reviewed":True,
                   "structure_reviewed":True, "example_structure":"学习与实践结构", "example_match_type":"cross_track",
                   "attribution":"公开作者署名（测试）"}
        example_chunks = [{"id":"e1c", "source_ref":"第一段", "content":"历史范文学习与实践结构"}]
        status, count = rpc("rag_publish_public_source", {"p_source":example,"p_chunks":example_chunks}, service)
        assert status == 200 and count == 1, (status, count)
        request = {"p_skill_id":"national-scholarship", "p_school":"其他大学", "p_year":2027,
                   "p_terms":["范文"], "p_filters":{}, "p_variant":""}
        status, rows = rpc("rag_search_public_knowledge", request, owner)
        assert status == 200 and rows == [], (status, rows)
        status, rows = rpc("rag_search_public_knowledge", {**request, "p_include_examples":True}, owner)
        assert status == 200 and [row["id"] for row in rows] == ["e1c"], (status, rows)
        assert rows[0]["example_match_type"] == "cross_track" and rows[0]["attribution"], rows
        status, rows = rpc("rag_search_public_knowledge",
                           {**request, "p_include_examples":True, "p_official_only":True}, owner)
        assert status == 200 and rows == [], (status, rows)
        print("PostgREST JWT/RLS、向量 RPC、范围过滤及发布权限隔离通过。")
    finally:
        for name in (REST, DB):
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "network", "rm", NETWORK], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
