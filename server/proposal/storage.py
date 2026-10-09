from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


class Store:
    """Small local SQLite store. Uploaded files are kept outside the repository."""

    def __init__(self, data_dir: str | Path | None = None):
        configured = data_dir or os.environ.get("PROPOSAL_AGENT_DATA_DIR")
        self.data_dir = Path(configured or (Path(__file__).resolve().parents[2] / ".agent-data"))
        self.data_dir = self.data_dir.expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir = self.data_dir / "projects"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "agent.sqlite3"
        self._init_db()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 30000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _init_db(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT '',
                    discipline TEXT NOT NULL DEFAULT '',
                    school TEXT NOT NULL DEFAULT '',
                    state_json TEXT NOT NULL DEFAULT '{}',
                    outline_json TEXT NOT NULL DEFAULT '[]',
                    sections_json TEXT NOT NULL DEFAULT '{}',
                    diagrams_json TEXT NOT NULL DEFAULT '[]',
                    template_document_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    original_name TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'source',
                    content_type TEXT NOT NULL DEFAULT '',
                    extracted_text TEXT NOT NULL DEFAULT '',
                    extraction_status TEXT NOT NULL DEFAULT 'pending',
                    extraction_warning TEXT NOT NULL DEFAULT '',
                    low_confidence_count INTEGER NOT NULL DEFAULT 0,
                    confirmed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    source_name TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project_id);
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id, created_at);
                CREATE TABLE IF NOT EXISTS token_usages (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    task_type TEXT NOT NULL DEFAULT "chat",
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    key_fingerprint TEXT NOT NULL DEFAULT "local",
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_token_usages_project ON token_usages(project_id, created_at);
                """
            )

    @staticmethod
    def _decode_json(value: str, fallback: Any) -> Any:
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback

    def create_project(
        self,
        title: str = "我的大创项目",
        level: str = "",
        discipline: str = "",
        school: str = "",
    ) -> dict[str, Any]:
        project_id = new_id()
        now = utc_now()
        title = str(title).strip()[:160] or "我的大创项目"
        level = str(level).strip()[:40]
        discipline = str(discipline).strip()[:100]
        school = str(school).strip()[:120]
        with self.connect() as db:
            db.execute(
                """INSERT INTO projects
                (id,title,level,discipline,school,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?)""",
                (project_id, title, level, discipline, school, now, now),
            )
        (self.files_dir / project_id).mkdir(parents=True, exist_ok=True)
        return self.get_project(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [self._project_row(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return self._project_row(row) if row else None

    def _project_row(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for field, fallback in (
            ("state_json", {}),
            ("outline_json", []),
            ("sections_json", {}),
            ("diagrams_json", []),
        ):
            result[field.removesuffix("_json")] = self._decode_json(result.pop(field), fallback)
        return result

    def update_project(self, project_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {"title", "level", "discipline", "school", "state", "outline", "sections", "diagrams"}
        updates: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            column = f"{key}_json" if key in {"state", "outline", "sections", "diagrams"} else key
            updates.append(f"{column}=?")
            values.append(json.dumps(value, ensure_ascii=False) if column.endswith("_json") else value)
        if not updates:
            return self.get_project(project_id)
        updates.append("updated_at=?")
        values.extend([utc_now(), project_id])
        with self.connect() as db:
            cur = db.execute(f"UPDATE projects SET {','.join(updates)} WHERE id=?", values)
            if not cur.rowcount:
                return None
        return self.get_project(project_id)

    def add_document(
        self,
        project_id: str,
        original_name: str,
        stored_path: str,
        kind: str,
        content_type: str,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        document_id = document_id or new_id()
        with self.connect() as db:
            db.execute(
                """INSERT INTO documents
                (id,project_id,original_name,stored_path,kind,content_type,created_at)
                VALUES (?,?,?,?,?,?,?)""",
                (document_id, project_id, original_name, stored_path, kind, content_type, utc_now()),
            )
            db.execute("UPDATE projects SET updated_at=? WHERE id=?", (utc_now(), project_id))
        return self.get_document(document_id)  # type: ignore[return-value]

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        return dict(row) if row else None

    def list_documents(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM documents WHERE project_id=? ORDER BY created_at",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_document_extraction(
        self,
        document_id: str,
        text: str,
        status: str,
        warning: str = "",
        low_confidence_count: int = 0,
        confirmed: bool = False,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """UPDATE documents SET extracted_text=?, extraction_status=?,
                extraction_warning=?, low_confidence_count=?, confirmed=? WHERE id=?""",
                (text, status, warning, low_confidence_count, int(confirmed), document_id),
            )

    def set_template_document(self, project_id: str, document_id: str | None) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE projects SET template_document_id=?, updated_at=? WHERE id=?",
                (document_id, utc_now(), project_id),
            )

    def replace_chunks(self, document_id: str, chunks: list[dict[str, Any]]) -> None:
        with self.connect() as db:
            doc = db.execute(
                "SELECT project_id,original_name FROM documents WHERE id=?",
                (document_id,),
            ).fetchone()
            if not doc:
                return
            db.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
            for chunk in chunks:
                db.execute(
                    """INSERT INTO chunks
                    (id,project_id,document_id,source_name,source_ref,content,embedding_json,created_at)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        new_id(),
                        doc["project_id"],
                        document_id,
                        doc["original_name"],
                        chunk["source_ref"],
                        chunk["content"],
                        json.dumps(chunk.get("embedding", [])),
                        utc_now(),
                    ),
                )

    def chunks_for_project(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT c.* FROM chunks c
                JOIN documents d ON d.id=c.document_id
                WHERE c.project_id=? AND d.confirmed=1 AND d.kind != 'template'""",
                (project_id,),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["embedding"] = self._decode_json(item.pop("embedding_json"), [])
            results.append(item)
        return results

    def add_message(self, project_id: str, role: str, content: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO messages(id,project_id,role,content,created_at) VALUES (?,?,?,?,?)",
                (new_id(), project_id, role, content, utc_now()),
            )
            db.execute("UPDATE projects SET updated_at=? WHERE id=?", (utc_now(), project_id))

    def messages(self, project_id: str, limit: int = 30) -> list[dict[str, str]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT role,content FROM messages WHERE project_id=?
                ORDER BY created_at DESC LIMIT ?""",
                (project_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def delete_document(self, document_id: str) -> dict[str, Any] | None:
        doc = self.get_document(document_id)
        if not doc:
            return None
        with self.connect() as db:
            db.execute("DELETE FROM documents WHERE id=?", (document_id,))
            db.execute(
                "UPDATE projects SET updated_at=? WHERE id=?",
                (utc_now(), doc["project_id"]),
            )
        return doc

    def delete_project(self, project_id: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
            if not row:
                return False
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
        folder = self.files_dir / project_id
        if folder.exists():
            for path in folder.iterdir():
                if path.is_file():
                    path.unlink()
            folder.rmdir()
        return True

    def record_token_usage(
        self,
        project_id: str,
        task_type: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: int = 0,
        key_fingerprint: str = "local",
    ) -> None:
        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens
        try:
            with self.connect() as db:
                db.execute(
                    """
                    INSERT INTO token_usages (id, project_id, task_type, model, prompt_tokens, completion_tokens, total_tokens, latency_ms, key_fingerprint, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (new_id(), project_id, task_type, model, prompt_tokens, completion_tokens, total_tokens, latency_ms, key_fingerprint, utc_now()),
                )
        except Exception:
            pass

    def get_token_stats(self, project_id: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            if project_id:
                cursor = db.execute(
                    """
                    SELECT
                        COUNT(*) as call_count,
                        COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                        COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                        COALESCE(SUM(total_tokens), 0) as grand_total_tokens,
                        COALESCE(AVG(latency_ms), 0) as avg_latency_ms
                    FROM token_usages WHERE project_id = ?
                    """,
                    (project_id,),
                )
                by_task = db.execute(
                    """
                    SELECT task_type, COUNT(*) as count, SUM(total_tokens) as tokens
                    FROM token_usages WHERE project_id = ?
                    GROUP BY task_type
                    """,
                    (project_id,),
                ).fetchall()
            else:
                cursor = db.execute(
                    """
                    SELECT
                        COUNT(*) as call_count,
                        COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                        COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                        COALESCE(SUM(total_tokens), 0) as grand_total_tokens,
                        COALESCE(AVG(latency_ms), 0) as avg_latency_ms
                    FROM token_usages
                    """
                )
                by_task = db.execute(
                    """
                    SELECT task_type, COUNT(*) as count, SUM(total_tokens) as tokens
                    FROM token_usages GROUP BY task_type
                    """
                ).fetchall()
            summary = dict(cursor.fetchone() or {})
            summary["by_task"] = [dict(row) for row in by_task]
            return summary
