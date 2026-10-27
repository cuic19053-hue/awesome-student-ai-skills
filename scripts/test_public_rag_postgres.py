#!/usr/bin/env python3
"""Run public RAG database security regression in an isolated disposable Docker container."""
from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "codex-rag-test-" + uuid.uuid4().hex[:10]
IMAGE = "pgvector/pgvector@sha256:47af0b65960b14f1c6945aa4ccae37836c632e9a6fe0eea9160936e616e5b2e9"


def run_sql(sql: str) -> None:
    subprocess.run(["docker", "exec", "-i", "-e", "PGPASSWORD=disposable-test", NAME,
                    "psql", "-h", "127.0.0.1", "-U", "postgres", "-v", "ON_ERROR_STOP=1"],
                   input=sql, text=True, check=True)


def main() -> None:
    try:
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--name", NAME,
                        "-e", "POSTGRES_PASSWORD=disposable-test", "-d", IMAGE], check=True)
        for _ in range(30):
            # The temporary initialization server uses a socket only; wait
            # for the final server to accept TCP connections.
            ready = subprocess.run(["docker", "exec", NAME, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("临时 PostgreSQL 未启动。")
        run_sql("create schema extensions; create role anon; create role authenticated; create role service_role bypassrls;")
        run_sql((ROOT / "supabase/migrations/20261027053127_rag_public_knowledge.sql").read_text())
        run_sql((ROOT / "server/evals/sql/public_rag_security.sql").read_text())
        print("公共知识库数据库安全与回滚测试通过。")
    finally:
        subprocess.run(["docker", "stop", NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
