from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .credit_security import workbench_voucher_digest
from .models_config import DEFAULT_INITIAL_CREDITS
from .billing_policy import TRIAL_REGISTRATION_CUTOFF, normalize_trial_wallet


class CreditRateLimitError(RuntimeError):
    """Raised when an account exceeds the card-redemption safety limit."""


class InsufficientCreditsError(ValueError):
    """The user's own workbench wallet cannot cover the model reservation."""


class PendingUsageError(ValueError):
    """An earlier upstream charge must be reconciled before another call."""


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
                CREATE TABLE IF NOT EXISTS user_balances (
                    user_id TEXT PRIMARY KEY,
                    credits INTEGER NOT NULL DEFAULT 0 CHECK (credits >= 0),
                    total_consumed INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS credit_transactions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    action TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_credit_tx_user ON credit_transactions(user_id, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_tx_order
                    ON credit_transactions(action) WHERE action LIKE 'order_payment:%';
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    amount_cny REAL NOT NULL,
                    credits_added INTEGER NOT NULL,
                    pay_type TEXT NOT NULL DEFAULT 'alipay',
                    status TEXT NOT NULL DEFAULT 'pending',
                    trade_no TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    paid_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_trade_no
                    ON orders(trade_no) WHERE trade_no <> '';
                CREATE TABLE IF NOT EXISTS recharge_codes (
                    code TEXT PRIMARY KEY,
                    credits INTEGER NOT NULL,
                    plan_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    used_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    used_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS workbench_credit_wallets (
                    user_id TEXT PRIMARY KEY,
                    balance_micro_cny INTEGER NOT NULL DEFAULT 0 CHECK (balance_micro_cny >= 0),
                    total_credited_micro_cny INTEGER NOT NULL DEFAULT 0 CHECK (total_credited_micro_cny >= 0),
                    total_spent_micro_cny INTEGER NOT NULL DEFAULT 0 CHECK (total_spent_micro_cny >= 0),
                    free_chat_count INTEGER NOT NULL DEFAULT 3 CHECK (free_chat_count >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workbench_credit_transactions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    delta_micro_cny INTEGER NOT NULL CHECK (delta_micro_cny <> 0),
                    balance_after_micro_cny INTEGER NOT NULL CHECK (balance_after_micro_cny >= 0),
                    kind TEXT NOT NULL,
                    reference_id TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    request_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, kind, reference_id)
                );
                CREATE INDEX IF NOT EXISTS idx_workbench_credit_tx_user
                    ON workbench_credit_transactions(user_id, created_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_workbench_payment_event
                    ON workbench_credit_transactions(reference_id)
                    WHERE kind = 'payment_credit';
                CREATE TABLE IF NOT EXISTS workbench_card_redemptions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    code_hash BLOB NOT NULL UNIQUE,
                    code_ciphertext BLOB,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','credited','rejected','needs_review')),
                    face_value_micro_cny INTEGER,
                    provider_user_id INTEGER,
                    transaction_id TEXT,
                    safe_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workbench_vouchers (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    code_hash BLOB NOT NULL UNIQUE CHECK (length(code_hash) = 32),
                    face_value_micro_cny INTEGER NOT NULL CHECK (face_value_micro_cny > 0),
                    provider_code_ciphertext BLOB,
                    status TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','active','redeemed','revoked')),
                    redeemed_by TEXT,
                    redeemed_at TEXT,
                    transaction_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workbench_vouchers_batch_status
                    ON workbench_vouchers(batch_id, status);
                CREATE TABLE IF NOT EXISTS workbench_usage_events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    request_id TEXT NOT NULL UNIQUE,
                    api_key_id INTEGER,
                    model TEXT NOT NULL,
                    reserved_micro_cny INTEGER NOT NULL CHECK (reserved_micro_cny > 0),
                    actual_micro_cny INTEGER,
                    provider_request_id TEXT,
                    status TEXT NOT NULL DEFAULT 'reserved'
                        CHECK (status IN ('reserved','settled','refunded','needs_review')),
                    created_at TEXT NOT NULL,
                    settled_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_workbench_usage_user_created
                    ON workbench_usage_events(user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS generation_jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    section_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    step TEXT NOT NULL DEFAULT 'queued',
                    attempt INTEGER NOT NULL DEFAULT 1,
                    idempotency_key TEXT NOT NULL DEFAULT '',
                    base_version TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_gen_jobs_project_section
                    ON generation_jobs(project_id, section_id, status);
                CREATE INDEX IF NOT EXISTS idx_gen_jobs_idempotency
                    ON generation_jobs(project_id, idempotency_key);
                CREATE TABLE IF NOT EXISTS section_versions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    section_id TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'user_edit',
                    content TEXT NOT NULL,
                    review_card_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_section_versions_proj_sec
                    ON section_versions(project_id, section_id, created_at DESC);
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(workbench_vouchers)")}
            if "provider_code_ciphertext" not in columns:
                db.execute("ALTER TABLE workbench_vouchers ADD COLUMN provider_code_ciphertext BLOB")
            wallet_cols = {row[1] for row in db.execute("PRAGMA table_info(workbench_credit_wallets)")}
            if "free_chat_count" not in wallet_cols:
                # Upgrading an old wallet is not a new registration.
                db.execute("ALTER TABLE workbench_credit_wallets ADD COLUMN free_chat_count INTEGER NOT NULL DEFAULT 0")
            # Apply to all credit-grant paths (payment, vouchers, paired codes),
            # not just one HTTP endpoint. A late free-request refund cannot
            # re-enable trials after payment.
            guard = f"""
                NEW.free_chat_count > 0 AND (
                    NEW.total_credited_micro_cny > 0 OR NEW.balance_micro_cny > 0
                    OR NEW.total_spent_micro_cny > 0
                    OR julianday(NEW.created_at) <= julianday('{TRIAL_REGISTRATION_CUTOFF}')
                )
            """
            for operation, name in (("INSERT", "insert"), ("UPDATE", "update")):
                db.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS workbench_trial_guard_{name}
                    AFTER {operation} ON workbench_credit_wallets
                    WHEN {guard}
                    BEGIN
                        UPDATE workbench_credit_wallets SET free_chat_count = 0
                        WHERE user_id = NEW.user_id;
                    END
                """)
            db.execute(
                """UPDATE workbench_credit_wallets SET free_chat_count = 0
                   WHERE free_chat_count > 0 AND (
                       total_credited_micro_cny > 0 OR balance_micro_cny > 0
                       OR total_spent_micro_cny > 0
                       OR julianday(created_at) <= julianday(?)
                   )""",
                (TRIAL_REGISTRATION_CUTOFF,),
            )

        with self.connect() as db:
            if "material_revision" not in {r["name"] for r in db.execute("PRAGMA table_info(projects)")}:
                db.execute("ALTER TABLE projects ADD COLUMN material_revision INTEGER NOT NULL DEFAULT 0")

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
        from .materials import attach_material
        return attach_material(result)

    def update_project(self, project_id: str, **fields: Any) -> dict[str, Any] | None:
        from .materials import MaterialConflict, enabled, prepare_update
        expected = fields.pop("expected_revision", None)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if not row:
                return None
            previous = self._project_row(row)
            if expected is not None and previous["material_revision"] != expected:
                raise MaterialConflict("项目已变化，请刷新后重试")
            if enabled(previous) or enabled({**previous, **fields}):
                fields = prepare_update(previous, fields)
            allowed = {"title", "level", "discipline", "school", "state", "outline", "sections",
                       "diagrams", "template_document_id"}
            fields = {k: v for k, v in fields.items() if k in allowed}
            if fields:
                updates, values = [], []
                for key, value in fields.items():
                    column = f"{key}_json" if key in {"state", "outline", "sections", "diagrams"} else key
                    updates.append(f"{column}=?")
                    values.append(json.dumps(value, ensure_ascii=False) if column.endswith("_json") else value)
                db.execute(
                    f"UPDATE projects SET {','.join(updates)}, material_revision=material_revision+1, updated_at=? WHERE id=?",
                    [*values, utc_now(), project_id],
                )
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
        from .materials import touch_document
        document = self.get_document(document_id)
        if document:
            touch_document(self, document)

    def set_template_document(self, project_id: str, document_id: str | None) -> None:
        self.update_project(project_id, template_document_id=document_id)

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
        from .materials import touch_document
        touch_document(self, doc, deleted=True)
        return doc

    def delete_project(self, project_id: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone()
            if not row:
                return False
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
            db.execute("DELETE FROM section_versions WHERE project_id=?", (project_id,))
            db.execute("DELETE FROM generation_jobs WHERE project_id=?", (project_id,))
        folder = self.files_dir / project_id
        if folder.exists():
            import shutil
            shutil.rmtree(folder)
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
                by_model = db.execute(
                    """
                    SELECT model, COUNT(*) as count, SUM(total_tokens) as tokens
                    FROM token_usages WHERE project_id = ?
                    GROUP BY model
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
                by_model = db.execute(
                    """
                    SELECT model, COUNT(*) as count, SUM(total_tokens) as tokens
                    FROM token_usages GROUP BY model
                    """
                ).fetchall()
            summary = dict(cursor.fetchone() or {})
            summary["by_task"] = [dict(row) for row in by_task]
            summary["by_model"] = [dict(row) for row in by_model]
            return summary

    def get_detailed_usage_logs(
        self, limit: int = 50, offset: int = 0, project_id: str | None = None
    ) -> list[dict[str, Any]]:
        limit = max(1, min(200, int(limit)))
        offset = max(0, int(offset))
        with self.connect() as db:
            if project_id:
                rows = db.execute(
                    """
                    SELECT u.*, p.title as project_title
                    FROM token_usages u
                    LEFT JOIN projects p ON u.project_id = p.id
                    WHERE u.project_id = ?
                    ORDER BY u.created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (project_id, limit, offset),
                ).fetchall()
            else:
                rows = db.execute(
                    """
                    SELECT u.*, p.title as project_title
                    FROM token_usages u
                    LEFT JOIN projects p ON u.project_id = p.id
                    ORDER BY u.created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_user_balance(self, user_id: str, default_credits: int = DEFAULT_INITIAL_CREDITS) -> dict[str, Any]:
        user_id = str(user_id or "default_user").strip()
        now = utc_now()
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO user_balances (user_id, credits, total_consumed, updated_at) VALUES (?, ?, 0, ?)",
                (user_id, default_credits, now),
            )
            row = db.execute("SELECT * FROM user_balances WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row)

    def deduct_credits(
        self, user_id: str, cost: int, model: str, action: str = "chat", project_id: str = ""
    ) -> dict[str, Any]:
        user_id = str(user_id or "default_user").strip()
        cost = max(0, int(cost))
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM user_balances WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                credits = DEFAULT_INITIAL_CREDITS
                consumed = 0
            else:
                credits = row["credits"]
                consumed = row["total_consumed"]

            if credits < cost:
                raise ValueError(f"积分余额不足（当前剩余 {credits} 点，本次需要 {cost} 点）。请充值积分或使用自带 API Key。")

            new_balance = credits - cost
            new_consumed = consumed + cost
            db.execute(
                """
                INSERT INTO user_balances (user_id, credits, total_consumed, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    credits = excluded.credits,
                    total_consumed = excluded.total_consumed,
                    updated_at = excluded.updated_at
                """,
                (user_id, new_balance, new_consumed, now),
            )
            tx_id = new_id()
            db.execute(
                """
                INSERT INTO credit_transactions (id, user_id, amount, balance_after, model, action, project_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tx_id, user_id, -cost, new_balance, model, action, project_id, now),
            )
            return {"user_id": user_id, "credits": new_balance, "total_consumed": new_consumed, "deducted": cost}

    def add_credits(
        self, user_id: str, amount: int, action: str = "recharge", model: str = "system", project_id: str = ""
    ) -> dict[str, Any]:
        user_id = str(user_id or "default_user").strip()
        amount = max(0, int(amount))
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM user_balances WHERE user_id = ?", (user_id,)).fetchone()
            credits = (row["credits"] if row else DEFAULT_INITIAL_CREDITS) + amount
            consumed = row["total_consumed"] if row else 0
            db.execute(
                """
                INSERT INTO user_balances (user_id, credits, total_consumed, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    credits = excluded.credits,
                    updated_at = excluded.updated_at
                """,
                (user_id, credits, consumed, now),
            )
            tx_id = new_id()
            db.execute(
                """
                INSERT INTO credit_transactions (id, user_id, amount, balance_after, model, action, project_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tx_id, user_id, amount, credits, model, action, project_id, now),
            )
            return {"user_id": user_id, "credits": credits, "added": amount}

    def get_credit_transactions(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        user_id = str(user_id or "default_user").strip()
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT * FROM credit_transactions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def create_order(
        self, user_id: str, plan_id: str, amount_cny: float, credits_added: int, pay_type: str = "alipay"
    ) -> dict[str, Any]:
        order_id = "ORD" + new_id()[:16].upper()
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO orders (order_id, user_id, plan_id, amount_cny, credits_added, pay_type, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (order_id, user_id, plan_id, float(amount_cny), int(credits_added), pay_type, now),
            )
            return {
                "order_id": order_id,
                "user_id": user_id,
                "plan_id": plan_id,
                "amount_cny": amount_cny,
                "credits_added": credits_added,
                "pay_type": pay_type,
                "status": "pending",
                "created_at": now,
            }

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            return dict(row) if row else None

    def complete_order(self, order_id: str, trade_no: str = "") -> dict[str, Any] | None:
        """Verified gateway callbacks only. Payment and credit grant commit together."""
        if not trade_no:
            raise ValueError("支付平台交易号不能为空")
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if not row:
                return None
            if row["status"] == "paid":
                if row["trade_no"] != trade_no:
                    raise ValueError("已支付订单的交易号不匹配")
                return dict(row)
            if row["status"] != "pending":
                raise ValueError("订单状态不允许入账")
            balance = db.execute(
                "SELECT credits, total_consumed FROM user_balances WHERE user_id = ?",
                (row["user_id"],),
            ).fetchone()
            credits = (balance["credits"] if balance else 0) + row["credits_added"]
            consumed = balance["total_consumed"] if balance else 0
            db.execute(
                "UPDATE orders SET status = 'paid', trade_no = ?, paid_at = ? WHERE order_id = ? AND status = 'pending'",
                (trade_no, now, order_id),
            )
            db.execute(
                """
                INSERT INTO user_balances(user_id, credits, total_consumed, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET credits = excluded.credits, updated_at = excluded.updated_at
                """,
                (row["user_id"], credits, consumed, now),
            )
            db.execute(
                """
                INSERT INTO credit_transactions(id, user_id, amount, balance_after, model, action, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(), row["user_id"], row["credits_added"], credits,
                    row["pay_type"], f"order_payment:{order_id}", now,
                ),
            )
            return dict(db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone())

    def create_recharge_code(self, credits: int, plan_id: str = "") -> str:
        from server.proposal.payment import generate_recharge_code
        code = generate_recharge_code()
        now = utc_now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO recharge_codes (code, credits, plan_id, status, created_at) VALUES (?, ?, ?, 'active', ?)",
                (code, int(credits), plan_id, now),
            )
        return code

    def redeem_recharge_code(self, user_id: str, code: str) -> dict[str, Any]:
        code = str(code).strip().upper()
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM recharge_codes WHERE code = ?", (code,)).fetchone()
            if not row:
                raise ValueError("卡密无效或不存在。")
            if row["status"] != "active":
                raise ValueError("该卡密已被使用或已失效。")
            db.execute(
                "UPDATE recharge_codes SET status = 'used', used_by = ?, used_at = ? WHERE code = ?",
                (user_id, now, code),
            )
            credits = row["credits"]
            balance = db.execute(
                "SELECT credits, total_consumed FROM user_balances WHERE user_id = ?", (user_id,)
            ).fetchone()
            new_balance = (balance["credits"] if balance else DEFAULT_INITIAL_CREDITS) + credits
            db.execute(
                """
                INSERT INTO user_balances(user_id, credits, total_consumed, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET credits = excluded.credits, updated_at = excluded.updated_at
                """,
                (user_id, new_balance, balance["total_consumed"] if balance else 0, now),
            )
            db.execute(
                """
                INSERT INTO credit_transactions(id, user_id, amount, balance_after, model, action, created_at)
                VALUES (?, ?, ?, ?, 'code', ?, ?)
                """,
                (new_id(), user_id, credits, new_balance, f"redeem_code:{code}", now),
            )
            return {"code": code, "credits_added": credits, "balance": new_balance}

    def get_profit_summary(self) -> dict[str, Any]:
        from server.proposal.payment import calculate_profit_share
        with self.connect() as db:
            row_rev = db.execute("SELECT COALESCE(SUM(amount_cny), 0) as total FROM orders WHERE status = 'paid'").fetchone()
            gross = float(row_rev["total"]) if row_rev else 0.0
            row_tok = db.execute(
                "SELECT COALESCE(SUM(prompt_tokens), 0) as p, COALESCE(SUM(completion_tokens), 0) as c FROM token_usages"
            ).fetchone()
            p = int(row_tok["p"]) if row_tok else 0
            c = int(row_tok["c"]) if row_tok else 0
            order_count = db.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'paid'").fetchone()["c"]
        summary = calculate_profit_share(gross_revenue=gross, total_prompt_tokens=p, total_completion_tokens=c)
        summary["paid_orders_count"] = order_count
        return summary

    def grant_workbench_payment_credits(
        self, user_id: str, event_id: str, amount_micro_cny: int
    ) -> dict[str, Any]:
        """Grant credits from one verified payment event exactly once."""
        user_id = str(user_id or "").strip()
        event_id = str(event_id or "").strip()
        amount_micro_cny = int(amount_micro_cny)
        if not user_id or not event_id or amount_micro_cny <= 0:
            raise ValueError("付款入账参数无效。")

        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                """
                SELECT balance_after_micro_cny FROM workbench_credit_transactions
                WHERE kind = 'payment_credit' AND reference_id = ?
                """,
                (event_id,),
            ).fetchone()
            if existing:
                existing_user = db.execute(
                    """
                    SELECT user_id FROM workbench_credit_transactions
                    WHERE kind = 'payment_credit' AND reference_id = ?
                    """,
                    (event_id,),
                ).fetchone()["user_id"]
                if str(existing_user) != user_id:
                    raise ValueError("付款事件已关联到其他工作台账户。")
                balance = db.execute(
                    "SELECT balance_micro_cny FROM workbench_credit_wallets WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                return {
                    "duplicate": True,
                    "balance_micro_cny": int(balance["balance_micro_cny"]) if balance else 0,
                    "credited_micro_cny": amount_micro_cny,
                }

            db.execute(
                """
                INSERT OR IGNORE INTO workbench_credit_wallets
                    (user_id, balance_micro_cny, total_credited_micro_cny,
                     total_spent_micro_cny, created_at, updated_at)
                VALUES (?, 0, 0, 0, ?, ?)
                """,
                (user_id, now, now),
            )
            db.execute(
                """
                UPDATE workbench_credit_wallets
                SET balance_micro_cny = balance_micro_cny + ?,
                    total_credited_micro_cny = total_credited_micro_cny + ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (amount_micro_cny, amount_micro_cny, now, user_id),
            )
            balance = db.execute(
                "SELECT balance_micro_cny FROM workbench_credit_wallets WHERE user_id = ?",
                (user_id,),
            ).fetchone()["balance_micro_cny"]
            db.execute(
                """
                INSERT INTO workbench_credit_transactions
                    (id, user_id, delta_micro_cny, balance_after_micro_cny,
                     kind, reference_id, created_at)
                VALUES (?, ?, ?, ?, 'payment_credit', ?, ?)
                """,
                (new_id(), user_id, amount_micro_cny, balance, event_id, now),
            )
            return {
                "duplicate": False,
                "balance_micro_cny": int(balance),
                "credited_micro_cny": amount_micro_cny,
            }

    def get_workbench_credit_balance(self, user_id: str) -> dict[str, Any]:
        user_id = str(user_id or "").strip()
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO workbench_credit_wallets
                    (user_id, balance_micro_cny, total_credited_micro_cny, total_spent_micro_cny, free_chat_count, created_at, updated_at)
                VALUES (?, 0, 0, 0, 3, ?, ?)
                """,
                (user_id, now, now),
            )
            row = db.execute(
                "SELECT * FROM workbench_credit_wallets WHERE user_id = ?", (user_id,)
            ).fetchone()
            return normalize_trial_wallet(dict(row))

    def consume_free_chat(self, user_id: str) -> int:
        user_id = str(user_id or "").strip()
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                INSERT OR IGNORE INTO workbench_credit_wallets
                    (user_id, balance_micro_cny, total_credited_micro_cny, total_spent_micro_cny, free_chat_count, created_at, updated_at)
                VALUES (?, 0, 0, 0, 3, ?, ?)
                """,
                (user_id, now, now),
            )
            row = db.execute(
                "SELECT * FROM workbench_credit_wallets WHERE user_id = ?", (user_id,)
            ).fetchone()
            current = normalize_trial_wallet(dict(row))["free_chat_count"] if row else 0
            if current <= 0:
                return -1
            remaining = current - 1
            db.execute(
                "UPDATE workbench_credit_wallets SET free_chat_count = ?, updated_at = ? WHERE user_id = ?",
                (remaining, now, user_id),
            )
            return remaining

    def refund_free_chat(self, user_id: str) -> int:
        user_id = str(user_id or "").strip()
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM workbench_credit_wallets WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not row or not normalize_trial_wallet(dict(row))["trial_eligible"]:
                return 0
            db.execute(
                "UPDATE workbench_credit_wallets SET free_chat_count = MIN(3, free_chat_count + 1), updated_at = ? WHERE user_id = ?",
                (now, user_id),
            )
            row = db.execute("SELECT free_chat_count FROM workbench_credit_wallets WHERE user_id = ?", (user_id,)).fetchone()
            return int(row["free_chat_count"]) if row else 0

    def get_workbench_credit_transactions(self, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT * FROM workbench_credit_transactions
                WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
                """,
                (str(user_id), max(1, min(100, int(limit)))),
            ).fetchall()
            return [dict(row) for row in rows]

    def import_workbench_voucher_drafts(
        self, batch_id: str, entries: list[tuple[bytes, int]]
    ) -> int:
        """Local admin/test import only; never expose this through a public route."""
        if not batch_id or not entries:
            raise ValueError("卡密批次不能为空。")
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for digest, face_value_micro_cny in entries:
                if len(digest) != 32 or face_value_micro_cny <= 0:
                    raise ValueError("卡密面值或摘要无效。")
                db.execute(
                    """
                    INSERT INTO workbench_vouchers
                        (id,batch_id,code_hash,face_value_micro_cny,status,created_at,updated_at)
                    VALUES (?,?,?,?,'draft',?,?)
                    """,
                    (new_id(), batch_id, digest, face_value_micro_cny, now, now),
                )
        return len(entries)

    def activate_workbench_voucher_batch(self, batch_id: str) -> int:
        """Explicit local admin/test activation; callers must verify shop funding."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                """
                UPDATE workbench_vouchers SET status='active', updated_at=?
                WHERE batch_id=? AND status='draft' AND provider_code_ciphertext IS NOT NULL
                """,
                (utc_now(), batch_id),
            )
            return result.rowcount

    def pair_workbench_voucher(self, code_hash: bytes, provider_code_ciphertext: bytes) -> None:
        if len(code_hash) != 32 or len(provider_code_ciphertext) < 29:
            raise ValueError("卡密配对数据无效。")
        with self.connect() as db:
            cur = db.execute(
                """UPDATE workbench_vouchers SET provider_code_ciphertext=?,updated_at=?
                   WHERE code_hash=? AND status='draft' AND provider_code_ciphertext IS NULL""",
                (provider_code_ciphertext, utc_now(), code_hash),
            )
            if cur.rowcount != 1:
                raise ValueError("卡密不存在、已配对或不再是草稿。")

    def lookup_paired_voucher(self, code_hash: bytes) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                """SELECT id,status,face_value_micro_cny,redeemed_by,provider_code_ciphertext
                   FROM workbench_vouchers WHERE code_hash=?""", (code_hash,),
            ).fetchone()
            if not row or row["status"] not in {"active", "redeemed"} or not row["provider_code_ciphertext"]:
                raise ValueError("工作台卡密无效或尚未启用。")
            return dict(row)

    def complete_paired_voucher(
        self, intent_id: str, face_value_micro_cny: int, provider_user_id: int
    ) -> dict[str, Any]:
        """Local equivalent of the atomic Supabase wrapper."""
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            intent = db.execute(
                "SELECT * FROM workbench_card_redemptions WHERE id=?", (intent_id,),
            ).fetchone()
            if not intent:
                raise ValueError("兑换请求不存在。")
            voucher = db.execute(
                "SELECT * FROM workbench_vouchers WHERE code_hash=?", (intent["code_hash"],),
            ).fetchone()
            if (
                not voucher or not voucher["provider_code_ciphertext"]
                or voucher["face_value_micro_cny"] != face_value_micro_cny
                or voucher["status"] not in {"active", "redeemed"}
                or (voucher["status"] == "redeemed" and voucher["redeemed_by"] != intent["user_id"])
                or not provider_user_id
            ):
                raise ValueError("卡密与上游面值或账户不匹配。")
            wallet = db.execute(
                "SELECT balance_micro_cny FROM workbench_credit_wallets WHERE user_id=?",
                (intent["user_id"],),
            ).fetchone()
            balance = wallet["balance_micro_cny"] if wallet else 0
            if intent["status"] == "credited":
                return {"duplicate": True, "balance_micro_cny": balance}
            if intent["status"] not in {"pending", "needs_review"}:
                raise ValueError("兑换请求已关闭。")
            balance += face_value_micro_cny
            db.execute(
                """INSERT INTO workbench_credit_wallets
                   (user_id,balance_micro_cny,total_credited_micro_cny,total_spent_micro_cny,created_at,updated_at)
                   VALUES (?,?,?,0,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                   balance_micro_cny=balance_micro_cny+excluded.balance_micro_cny,
                   total_credited_micro_cny=total_credited_micro_cny+excluded.total_credited_micro_cny,
                   updated_at=excluded.updated_at""",
                (intent["user_id"], face_value_micro_cny, face_value_micro_cny, now, now),
            )
            tx_id = new_id()
            db.execute(
                """INSERT INTO workbench_credit_transactions
                   (id,user_id,delta_micro_cny,balance_after_micro_cny,kind,reference_id,created_at)
                   VALUES (?,?,?,?,'card_redeem',?,?)""",
                (tx_id, intent["user_id"], face_value_micro_cny, balance, intent_id, now),
            )
            db.execute(
                """UPDATE workbench_card_redemptions
                   SET status='credited',face_value_micro_cny=?,provider_user_id=?,
                       transaction_id=?,code_ciphertext=NULL,updated_at=? WHERE id=?""",
                (face_value_micro_cny, provider_user_id, tx_id, now, intent_id),
            )
            db.execute(
                """UPDATE workbench_vouchers
                   SET status='redeemed',redeemed_by=?,redeemed_at=?,
                       transaction_id=?,updated_at=? WHERE id=?""",
                (intent["user_id"], now, tx_id, now, voucher["id"]),
            )
            return {"duplicate": False, "balance_micro_cny": balance}

    def redeem_workbench_voucher(self, user_id: str, code: str) -> dict[str, Any]:
        digest = workbench_voucher_digest(code)
        user_id = str(user_id or "").strip()
        if not user_id:
            raise ValueError("需要先登录才能兑换卡密。")
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            voucher = db.execute(
                "SELECT * FROM workbench_vouchers WHERE code_hash = ?", (digest,)
            ).fetchone()
            if not voucher:
                raise ValueError("卡密无效。")
            if voucher["status"] == "redeemed":
                if voucher["redeemed_by"] != user_id:
                    raise ValueError("卡密已被兑换。")
                wallet = db.execute(
                    "SELECT balance_micro_cny FROM workbench_credit_wallets WHERE user_id=?",
                    (user_id,),
                ).fetchone()
                return {
                    "duplicate": True,
                    "credited_micro_cny": voucher["face_value_micro_cny"],
                    "balance_micro_cny": wallet["balance_micro_cny"] if wallet else 0,
                }
            if voucher["status"] != "active":
                raise ValueError("卡密尚未启用。")
            db.execute(
                """
                INSERT OR IGNORE INTO workbench_credit_wallets
                    (user_id,balance_micro_cny,total_credited_micro_cny,
                     total_spent_micro_cny,created_at,updated_at)
                VALUES (?,0,0,0,?,?)
                """,
                (user_id, now, now),
            )
            db.execute(
                """
                UPDATE workbench_credit_wallets
                SET balance_micro_cny=balance_micro_cny+?,
                    total_credited_micro_cny=total_credited_micro_cny+?,
                    updated_at=?
                WHERE user_id=?
                """,
                (voucher["face_value_micro_cny"], voucher["face_value_micro_cny"], now, user_id),
            )
            balance = db.execute(
                "SELECT balance_micro_cny FROM workbench_credit_wallets WHERE user_id=?",
                (user_id,),
            ).fetchone()["balance_micro_cny"]
            transaction_id = new_id()
            db.execute(
                """
                INSERT INTO workbench_credit_transactions
                    (id,user_id,delta_micro_cny,balance_after_micro_cny,kind,reference_id,created_at)
                VALUES (?,?,?,?,'card_redeem',?,?)
                """,
                (
                    transaction_id, user_id, voucher["face_value_micro_cny"],
                    balance, voucher["id"], now,
                ),
            )
            db.execute(
                """
                UPDATE workbench_vouchers
                SET status='redeemed',redeemed_by=?,redeemed_at=?,transaction_id=?,updated_at=?
                WHERE id=? AND status='active'
                """,
                (user_id, now, transaction_id, now, voucher["id"]),
            )
            return {
                "duplicate": False,
                "credited_micro_cny": voucher["face_value_micro_cny"],
                "balance_micro_cny": balance,
            }

    def begin_workbench_card_redemption(
        self, user_id: str, code_hash: bytes, code_ciphertext: bytes
    ) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM workbench_card_redemptions WHERE code_hash = ?", (code_hash,)
            ).fetchone()
            if existing:
                if existing["user_id"] != user_id:
                    raise ValueError("此卡密已由其他工作台账户提交。")
                result = dict(existing)
                result["duplicate"] = True
                return result

            cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
            recent_count = db.execute(
                """
                SELECT COUNT(*) FROM workbench_card_redemptions
                WHERE user_id = ? AND created_at >= ?
                """,
                (user_id, cutoff),
            ).fetchone()[0]
            if recent_count >= 10:
                raise CreditRateLimitError("卡密兑换过于频繁，请一小时后再试。")

            inserted = db.execute(
                """
                INSERT OR IGNORE INTO workbench_card_redemptions
                    (id, user_id, code_hash, code_ciphertext, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (new_id(), user_id, code_hash, code_ciphertext, now, now),
            ).rowcount
            row = db.execute(
                "SELECT * FROM workbench_card_redemptions WHERE code_hash = ?", (code_hash,)
            ).fetchone()
            if row["user_id"] != user_id:
                raise ValueError("此卡密已由其他工作台账户提交。")
            result = dict(row)
            result["duplicate"] = inserted == 0
            return result

    def get_workbench_redemption_intent(self, intent_id: str, user_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM workbench_card_redemptions WHERE id = ? AND user_id = ?",
                (intent_id, user_id),
            ).fetchone()
            return dict(row) if row else None

    def complete_workbench_card_redemption(
        self, intent_id: str, face_value_micro_cny: int, provider_user_id: int | None = None
    ) -> dict[str, Any]:
        if face_value_micro_cny <= 0:
            raise ValueError("卡密面值无效。")
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            intent = db.execute(
                "SELECT * FROM workbench_card_redemptions WHERE id = ?", (intent_id,)
            ).fetchone()
            if not intent:
                raise ValueError("找不到卡密兑换请求。")
            wallet = db.execute(
                "SELECT * FROM workbench_credit_wallets WHERE user_id = ?", (intent["user_id"],)
            ).fetchone()
            balance = wallet["balance_micro_cny"] if wallet else 0
            if intent["status"] == "credited":
                return {"status": "credited", "duplicate": True, "balance_micro_cny": balance}
            if intent["status"] not in {"pending", "needs_review"}:
                raise ValueError("此卡密兑换请求已关闭。")
            balance += face_value_micro_cny
            db.execute(
                """
                INSERT INTO workbench_credit_wallets
                    (user_id, balance_micro_cny, total_credited_micro_cny, total_spent_micro_cny, created_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    balance_micro_cny = excluded.balance_micro_cny,
                    total_credited_micro_cny = workbench_credit_wallets.total_credited_micro_cny + excluded.total_credited_micro_cny,
                    updated_at = excluded.updated_at
                """,
                (intent["user_id"], balance, face_value_micro_cny, now, now),
            )
            tx_id = new_id()
            db.execute(
                """
                INSERT INTO workbench_credit_transactions
                    (id, user_id, delta_micro_cny, balance_after_micro_cny, kind, reference_id, created_at)
                VALUES (?, ?, ?, ?, 'card_redeem', ?, ?)
                """,
                (tx_id, intent["user_id"], face_value_micro_cny, balance, intent_id, now),
            )
            db.execute(
                """
                UPDATE workbench_card_redemptions
                SET status='credited', face_value_micro_cny=?, provider_user_id=?,
                    transaction_id=?, code_ciphertext=NULL, safe_message='', updated_at=?
                WHERE id=?
                """,
                (face_value_micro_cny, provider_user_id, tx_id, now, intent_id),
            )
            return {"status": "credited", "duplicate": False, "balance_micro_cny": balance}

    def set_workbench_card_redemption_status(
        self, intent_id: str, status: str, safe_message: str
    ) -> None:
        if status not in {"pending", "rejected", "needs_review"}:
            raise ValueError("invalid redemption state")
        with self.connect() as db:
            cur = db.execute(
                """
                UPDATE workbench_card_redemptions
                SET status=?, safe_message=?, code_ciphertext=CASE WHEN ?='rejected' THEN NULL ELSE code_ciphertext END,
                    updated_at=?
                WHERE id=? AND status <> 'credited'
                """,
                (status, safe_message[:240], status, utc_now(), intent_id),
            )
            if cur.rowcount != 1:
                raise ValueError("兑换请求不存在或已完成。")

    def reserve_workbench_usage(
        self, user_id: str, request_id: str, model: str, reserve_micro_cny: int, api_key_id: int | None = None
    ) -> dict[str, Any]:
        if reserve_micro_cny <= 0:
            raise ValueError("本次预留金额无效。")
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT * FROM workbench_usage_events WHERE request_id = ?", (request_id,)
            ).fetchone()
            if prior:
                if prior["user_id"] != user_id:
                    raise ValueError("请求标识已由其他用户使用。")
                return {"status": prior["status"], "duplicate": True}
            unresolved = db.execute(
                """
                SELECT 1 FROM workbench_usage_events
                WHERE user_id = ? AND status IN ('reserved', 'needs_review') LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if unresolved:
                raise PendingUsageError("有一笔模型用量正在核对，请稍后重试。")
            wallet = db.execute(
                "SELECT balance_micro_cny FROM workbench_credit_wallets WHERE user_id = ?", (user_id,)
            ).fetchone()
            balance = wallet["balance_micro_cny"] if wallet else 0
            if balance < reserve_micro_cny:
                raise InsufficientCreditsError("积分不足。请兑换卡密或切换自带 API Key。")
            balance -= reserve_micro_cny
            db.execute(
                "UPDATE workbench_credit_wallets SET balance_micro_cny=?, updated_at=? WHERE user_id=?",
                (balance, now, user_id),
            )
            db.execute(
                """
                INSERT INTO workbench_usage_events
                    (id,user_id,request_id,api_key_id,model,reserved_micro_cny,status,created_at)
                VALUES (?,?,?,?,?,?,'reserved',?)
                """,
                (new_id(), user_id, request_id, api_key_id, model, reserve_micro_cny, now),
            )
            db.execute(
                """
                INSERT INTO workbench_credit_transactions
                    (id,user_id,delta_micro_cny,balance_after_micro_cny,kind,reference_id,model,request_id,created_at)
                VALUES (?,?,?,?,'usage_reserve',?,?,?,?)
                """,
                (new_id(), user_id, -reserve_micro_cny, balance, request_id, model, request_id, now),
            )
            return {"status": "reserved", "duplicate": False, "balance_micro_cny": balance}

    def settle_workbench_usage(
        self, request_id: str, actual_micro_cny: int, provider_request_id: str = ""
    ) -> dict[str, Any]:
        if actual_micro_cny < 0:
            raise ValueError("模型实际费用无效。")
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            event = db.execute(
                "SELECT * FROM workbench_usage_events WHERE request_id = ?", (request_id,)
            ).fetchone()
            if not event:
                raise ValueError("找不到模型用量预留。")
            wallet = db.execute(
                "SELECT * FROM workbench_credit_wallets WHERE user_id = ?", (event["user_id"],)
            ).fetchone()
            balance = wallet["balance_micro_cny"] if wallet else 0
            if event["status"] == "settled":
                return {"status": "settled", "duplicate": True, "balance_micro_cny": balance}
            if event["status"] != "reserved":
                raise ValueError("模型用量状态需人工核对。")
            if actual_micro_cny > event["reserved_micro_cny"]:
                db.execute(
                    """
                    UPDATE workbench_usage_events SET status='needs_review',
                        actual_micro_cny=?, provider_request_id=? WHERE id=?
                    """,
                    (actual_micro_cny, provider_request_id, event["id"]),
                )
                return {"status": "needs_review", "balance_micro_cny": balance}
            refund = event["reserved_micro_cny"] - actual_micro_cny
            balance += refund
            db.execute(
                """
                UPDATE workbench_credit_wallets
                SET balance_micro_cny=?, total_spent_micro_cny=total_spent_micro_cny+?, updated_at=?
                WHERE user_id=?
                """,
                (balance, actual_micro_cny, now, event["user_id"]),
            )
            if refund:
                db.execute(
                    """
                    INSERT INTO workbench_credit_transactions
                        (id,user_id,delta_micro_cny,balance_after_micro_cny,kind,reference_id,model,request_id,created_at)
                    VALUES (?,?,?,?,'usage_settle',?,?,?,?)
                    """,
                    (new_id(), event["user_id"], refund, balance, request_id, event["model"], request_id, now),
                )
            db.execute(
                """
                UPDATE workbench_usage_events SET status='settled', actual_micro_cny=?,
                    provider_request_id=?, settled_at=? WHERE id=?
                """,
                (actual_micro_cny, provider_request_id, now, event["id"]),
            )
            return {"status": "settled", "duplicate": False, "balance_micro_cny": balance}

    def pending_workbench_usage(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT request_id,model,api_key_id FROM workbench_usage_events
                   WHERE user_id=? AND status='reserved' ORDER BY created_at LIMIT ?""",
                (user_id, max(1, min(limit, 20))),
            ).fetchall()
            return [dict(row) for row in rows]

    def refund_workbench_usage(self, request_id: str, reason: str = "provider_error") -> dict[str, Any]:
        now = utc_now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            event = db.execute(
                "SELECT * FROM workbench_usage_events WHERE request_id = ?", (request_id,)
            ).fetchone()
            if not event:
                raise ValueError("找不到模型用量预留。")
            wallet = db.execute(
                "SELECT * FROM workbench_credit_wallets WHERE user_id = ?", (event["user_id"],)
            ).fetchone()
            balance = wallet["balance_micro_cny"] if wallet else 0
            if event["status"] == "refunded":
                return {"status": "refunded", "duplicate": True, "balance_micro_cny": balance}
            if event["status"] != "reserved":
                raise ValueError("该模型用量不能退款，需人工核对。")
            balance += event["reserved_micro_cny"]
            db.execute(
                """
                UPDATE workbench_credit_wallets
                SET balance_micro_cny=?, updated_at=? WHERE user_id=?
                """,
                (balance, now, event["user_id"]),
            )
            db.execute(
                """
                INSERT INTO workbench_credit_transactions
                    (id,user_id,delta_micro_cny,balance_after_micro_cny,kind,reference_id,model,request_id,created_at)
                VALUES (?,?,?,?,'usage_refund',?,?,?,?)
                """,
                (
                    new_id(), event["user_id"], event["reserved_micro_cny"], balance,
                    event["model"], request_id, request_id, now,
                ),
            )
            db.execute(
                "UPDATE workbench_usage_events SET status='refunded', settled_at=? WHERE id=?",
                (now, event["id"]),
            )
            return {"status": "refunded", "duplicate": False, "balance_micro_cny": balance}

    # ------------------------------------------------------------------
    # 异步生成任务 (Generation Jobs) 与版本保护
    # ------------------------------------------------------------------

    def create_generation_job(
        self, project_id: str, section_id: str, idempotency_key: str = "", base_version: str = ""
    ) -> dict[str, Any]:
        with self.connect() as db:
            job_id = new_id()
            now = utc_now()
            db.execute(
                """INSERT INTO generation_jobs
                (id, project_id, section_id, status, step, attempt, idempotency_key, base_version, result_json, error_message, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', 'queued', 1, ?, ?, '{}', '', ?, ?)""",
                (job_id, project_id, section_id, idempotency_key or "", base_version or "", now, now),
            )
        return self.get_generation_job(job_id)  # type: ignore[return-value]

    def get_generation_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        res["result"] = self._decode_json(res.pop("result_json", "{}"), {})
        return res

    def find_job_by_idempotency_key(self, project_id: str, idempotency_key: str) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM generation_jobs WHERE project_id=? AND idempotency_key=? ORDER BY created_at DESC LIMIT 1",
                (project_id, idempotency_key),
            ).fetchone()
        if not row:
            return None
        res = dict(row)
        res["result"] = self._decode_json(res.pop("result_json", "{}"), {})
        return res

    def find_active_job(self, project_id: str, section_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                """SELECT * FROM generation_jobs
                WHERE project_id=? AND section_id=? AND status IN ('pending', 'running')
                ORDER BY created_at DESC LIMIT 1""",
                (project_id, section_id),
            ).fetchone()
        if not row:
            return None
        res = dict(row)
        res["result"] = self._decode_json(res.pop("result_json", "{}"), {})
        return res

    def update_generation_job(
        self,
        job_id: str,
        status: str,
        step: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT status FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            cur_status = row["status"]
            # 终态防重入保护：已取消或已终态的任务不能被非对应终态覆盖
            if cur_status == "cancelled" and status != "cancelled":
                return self.get_generation_job(job_id)
            if cur_status in {"completed", "failed"} and status in {"pending", "running"}:
                return self.get_generation_job(job_id)
            updates = ["status=?", "updated_at=?"]
            params: list[Any] = [status, utc_now()]
            if step is not None:
                updates.append("step=?")
                params.append(step)
            if result is not None:
                updates.append("result_json=?")
                params.append(json.dumps(result, ensure_ascii=False))
            if error is not None:
                updates.append("error_message=?")
                params.append(error)
            params.append(job_id)
            where_clauses = ["WHERE id=?"]
            if status != "cancelled":
                where_clauses.append("AND status != 'cancelled'")
            if status in {"pending", "running"}:
                where_clauses.append("AND status NOT IN ('completed', 'failed')")
            db.execute(f"UPDATE generation_jobs SET {', '.join(updates)} {' '.join(where_clauses)}", params)
        return self.get_generation_job(job_id)

    def cancel_generation_job(self, job_id: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT status FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] in {"completed", "failed", "cancelled"}:
                return False
            cursor = db.execute(
                "UPDATE generation_jobs SET status='cancelled', updated_at=? WHERE id=? AND status NOT IN ('completed', 'failed', 'cancelled')",
                (utc_now(), job_id),
            )
            if cursor.rowcount == 0:
                return False
        return True

    def save_section_version(
        self,
        project_id: str,
        section_id: str,
        content: str,
        source: str = "user_edit",
        review_card: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        version_id = new_id()
        now = utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO section_versions
                (id, project_id, section_id, source, content, review_card_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id,
                    project_id,
                    section_id,
                    source,
                    content,
                    json.dumps(review_card or {}, ensure_ascii=False),
                    now,
                ),
            )
        return {
            "id": version_id,
            "project_id": project_id,
            "section_id": section_id,
            "source": source,
            "content": content,
            "review_card": review_card or {},
            "created_at": now,
        }

    def list_section_versions(self, project_id: str, section_id: str, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT * FROM section_versions
                WHERE project_id=? AND section_id=?
                ORDER BY created_at DESC LIMIT ?""",
                (project_id, section_id, max(1, min(limit, 50))),
            ).fetchall()
        results = []
        for r in rows:
            item = dict(r)
            item["review_card"] = self._decode_json(item.pop("review_card_json", "{}"), {})
            results.append(item)
        return results

    def get_section_version(self, version_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM section_versions WHERE id=?", (version_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        res["review_card"] = self._decode_json(res.pop("review_card_json", "{}"), {})
        return res
