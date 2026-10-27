#!/usr/bin/env python3
"""Run private RAG security regression in a disposable local Docker container."""
from __future__ import annotations
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "codex-private-rag-" + uuid.uuid4().hex[:10]
IMAGE = "pgvector/pgvector@sha256:47af0b65960b14f1c6945aa4ccae37836c632e9a6fe0eea9160936e616e5b2e9"


def sql(text: str) -> None:
    subprocess.run(["docker", "exec", "-i", "-e", "PGPASSWORD=disposable-test", NAME,
                    "psql", "-h", "127.0.0.1", "-U", "postgres", "-v", "ON_ERROR_STOP=1"],
                   input=text, text=True, check=True)


def main() -> None:
    try:
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--name", NAME,
                        "-e", "POSTGRES_PASSWORD=disposable-test", "-d", IMAGE], check=True)
        for _ in range(30):
            # The image's temporary initialization server listens only on a
            # socket and then shuts down. TCP readiness avoids that transient.
            ready = subprocess.run(["docker", "exec", NAME, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("临时 PostgreSQL 未启动。")
        sql('''create schema extensions; create schema auth; create role anon; create role authenticated;
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
grant usage on schema auth to authenticated;
create table public.projects(id text primary key,owner_id uuid not null);
create table public.documents(id text primary key,project_id text not null references public.projects(id),confirmed bool not null,kind text not null,original_name text not null default '',extracted_text text not null default '');
create table public.chunks(id text primary key,project_id text not null references public.projects(id),document_id text not null references public.documents(id),source_name text not null,source_ref text not null,content text not null,embedding_json jsonb not null default '[]'::jsonb,created_at timestamptz not null default now());
alter table public.projects enable row level security; alter table public.documents enable row level security; alter table public.chunks enable row level security;
grant select,insert,update,delete on public.projects,public.documents,public.chunks to authenticated;
create policy own_projects on public.projects for all to authenticated using (owner_id=(select auth.uid())) with check (owner_id=(select auth.uid()));
create policy own_documents on public.documents for all to authenticated using (exists(select 1 from public.projects p where p.id=documents.project_id and p.owner_id=(select auth.uid()))) with check (exists(select 1 from public.projects p where p.id=documents.project_id and p.owner_id=(select auth.uid())));
create policy own_chunks on public.chunks for all to authenticated using (exists(select 1 from public.projects p where p.id=chunks.project_id and p.owner_id=(select auth.uid()))) with check (exists(select 1 from public.projects p where p.id=chunks.project_id and p.owner_id=(select auth.uid())));
''')
        sql((ROOT / "supabase/migrations/20261027051631_rag_project_search.sql").read_text())
        sql((ROOT / "server/evals/sql/private_rag_security.sql").read_text())
        print("私有资料数据库隔离、确认撤销和向量版本测试通过。")
    finally:
        subprocess.run(["docker", "stop", NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
