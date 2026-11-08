"""Local, opt-in turn ledger with fenced claims and conservative recovery.

This ledger is not an executor. The caller must authorize each owner/project,
store the user's input separately, and never pass credentials to this module.
Its database must be separate from the existing project SQLite database.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class IdempotencyConflict(ValueError):
    """One idempotency key was reused for a different request."""


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 160 or "\x00" in value:
        raise ValueError(f"无效的{label}。")
    return value


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ChatTurns:
    """Persist local turn status; neither input text nor credentials are stored.

    A worker receives a one-time lease token from claim(). Once the lease
    expires the outcome becomes uncertain, never pending. Even a known
    failure is terminal: the application decides whether to issue a new turn.

    Pending records contain no executable input. Following a process restart,
    the application must provide the original input after matching its digest,
    or explicitly abandon the record; the ledger cannot resume it itself.
    Different keys may remain pending for a project, but only one can run at a
    time. This ledger does not choose which pending turn to claim or promise
    FIFO order. Authorization belongs to the caller; an uncertain earlier turn
    does not itself prohibit a different explicitly submitted turn.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS chat_turns (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','running','completed','failed','uncertain')),
                    lease_hash TEXT,
                    lease_until REAL,
                    result TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(owner_id, project_id, key_hash)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS chat_turns_one_running_per_project
                    ON chat_turns(owner_id, project_id) WHERE status = 'running';
                CREATE INDEX IF NOT EXISTS chat_turns_expiry
                    ON chat_turns(lease_until) WHERE status = 'running';
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 30000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _public(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = {key: row[key] for key in ("id", "project_id", "status", "created_at", "updated_at")}
        if row["status"] == "completed":
            result["result"] = row["result"]
        return result

    def submit(self, owner_id: str, project_id: str, idempotency_key: str,
               request_fingerprint: str) -> tuple[dict[str, Any], bool]:
        owner = _identifier(owner_id, "用户")
        project = _identifier(project_id, "项目")
        key = _identifier(idempotency_key, "幂等键")
        if not isinstance(request_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", request_fingerprint):
            raise ValueError("请求指纹必须是小写 SHA-256 摘要。")
        key_hash = _digest(key)
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM chat_turns WHERE owner_id=? AND project_id=? AND key_hash=?",
                             (owner, project, key_hash)).fetchone()
            if row:
                if not hmac.compare_digest(row["request_fingerprint"], request_fingerprint):
                    raise IdempotencyConflict("幂等键已用于不同请求。")
                return self._public(row), False  # type: ignore[return-value]
            turn_id = uuid.uuid4().hex
            db.execute("""INSERT INTO chat_turns
                (id,owner_id,project_id,key_hash,request_fingerprint,status,created_at,updated_at)
                VALUES(?,?,?,?,?,'pending',?,?)""",
                (turn_id, owner, project, key_hash, request_fingerprint, now, now))
            row = db.execute("SELECT * FROM chat_turns WHERE id=?", (turn_id,)).fetchone()
            return self._public(row), True  # type: ignore[return-value]

    def claim(self, owner_id: str, project_id: str, turn_id: str,
              lease_seconds: float = 120) -> str | None:
        owner = _identifier(owner_id, "用户")
        project = _identifier(project_id, "项目")
        turn = _identifier(turn_id, "任务")
        if not isinstance(lease_seconds, (int, float)) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 3600:
            raise ValueError("租约时长无效。")
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Expired executions are not proof the model did not run.
            self._expire_in_transaction(db, now)
            active = db.execute("SELECT 1 FROM chat_turns WHERE owner_id=? AND project_id=? AND status='running'",
                                (owner, project)).fetchone()
            if active:
                return None
            changed = db.execute("""UPDATE chat_turns SET status='running',lease_hash=?,lease_until=?,updated_at=?
                WHERE id=? AND owner_id=? AND project_id=? AND status='pending'""",
                (_digest(token), now + lease_seconds, now, turn, owner, project)).rowcount
            return token if changed else None

    def renew(self, owner_id: str, project_id: str, turn_id: str, lease_token: str,
              lease_seconds: float = 120) -> bool:
        owner = _identifier(owner_id, "用户")
        project = _identifier(project_id, "项目")
        turn = _identifier(turn_id, "任务")
        token = _identifier(lease_token, "租约")
        if not isinstance(lease_seconds, (int, float)) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 3600:
            raise ValueError("租约时长无效。")
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._expire_in_transaction(db, now)
            return bool(db.execute("""UPDATE chat_turns SET lease_until=?,updated_at=?
                WHERE id=? AND owner_id=? AND project_id=? AND status='running' AND lease_hash=? AND lease_until>?""",
                (now + lease_seconds, now, turn, owner, project, _digest(token), now)).rowcount)

    def is_lease_valid(self, owner_id: str, project_id: str, turn_id: str,
                       lease_token: str) -> bool:
        """Check lease ownership; not an atomic fence for external services."""
        owner = _identifier(owner_id, "用户")
        project = _identifier(project_id, "项目")
        turn = _identifier(turn_id, "任务")
        token = _identifier(lease_token, "租约")
        with self._connect() as db:
            return db.execute("""SELECT 1 FROM chat_turns WHERE id=? AND owner_id=? AND project_id=?
                AND status='running' AND lease_hash=? AND lease_until>?""",
                (turn, owner, project, _digest(token), time.time())).fetchone() is not None

    def abandon_pending(self, owner_id: str, project_id: str, turn_id: str) -> bool:
        """Terminate a known-unstarted record without claiming or executing it."""
        owner = _identifier(owner_id, "用户")
        project = _identifier(project_id, "项目")
        turn = _identifier(turn_id, "任务")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return bool(db.execute("""UPDATE chat_turns SET status='failed',updated_at=?
                WHERE id=? AND owner_id=? AND project_id=? AND status='pending'""",
                (time.time(), turn, owner, project)).rowcount)

    def complete(self, owner_id: str, project_id: str, turn_id: str,
                 lease_token: str, result: str) -> bool:
        if not isinstance(result, str) or not result.strip() or len(result) > 200_000:
            raise ValueError("对话结果为空或过长。")
        return self._finish(owner_id, project_id, turn_id, lease_token, "completed", result)

    def fail(self, owner_id: str, project_id: str, turn_id: str,
             lease_token: str, *, uncertain: bool) -> bool:
        if not isinstance(uncertain, bool):
            raise ValueError("需要明确请求结果是否不确定。")
        return self._finish(owner_id, project_id, turn_id, lease_token,
                            "uncertain" if uncertain else "failed", None)

    def _finish(self, owner_id: str, project_id: str, turn_id: str,
                lease_token: str, status: str, result: str | None) -> bool:
        owner = _identifier(owner_id, "用户")
        project = _identifier(project_id, "项目")
        turn = _identifier(turn_id, "任务")
        token = _identifier(lease_token, "租约")
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._expire_in_transaction(db, now)
            return bool(db.execute("""UPDATE chat_turns SET status=?,result=?,lease_hash=NULL,lease_until=NULL,updated_at=?
                WHERE id=? AND owner_id=? AND project_id=? AND status='running' AND lease_hash=? AND lease_until>?""",
                (status, result, now, turn, owner, project, _digest(token), now)).rowcount)

    def get(self, owner_id: str, project_id: str, turn_id: str) -> dict[str, Any] | None:
        owner = _identifier(owner_id, "用户")
        project = _identifier(project_id, "项目")
        turn = _identifier(turn_id, "任务")
        with self._connect() as db:
            row = db.execute("SELECT * FROM chat_turns WHERE id=? AND owner_id=? AND project_id=?",
                             (turn, owner, project)).fetchone()
            return self._public(row)

    @staticmethod
    def _expire_in_transaction(db: sqlite3.Connection, now: float) -> int:
        return db.execute("""UPDATE chat_turns SET status='uncertain',lease_hash=NULL,lease_until=NULL,updated_at=?
            WHERE status='running' AND lease_until<=?""", (now, now)).rowcount

    def expire(self) -> int:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._expire_in_transaction(db, time.time())
