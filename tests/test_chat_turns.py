"""Local idempotency and lease behavior; no live model or production data."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import multiprocessing
import os
import sqlite3

import pytest

from server.proposal.chat_turns import ChatTurns, IdempotencyConflict


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def competing_worker(db_path: str) -> tuple[str, bool, str | None]:
    turns = ChatTurns(db_path)
    item, created = turns.submit("alice", "project-1", "same-key", fingerprint("same-request"))
    lease = turns.claim("alice", "project-1", item["id"])
    return item["id"], created, lease


def test_idempotent_submission_and_reject_mismatched_reuse(tmp_path):
    turns = ChatTurns(tmp_path / "turns.sqlite3")
    first, created = turns.submit("alice", "project", "key", fingerprint("request-one"))
    assert created is True and first["status"] == "pending"
    duplicate, created = turns.submit("alice", "project", "key", fingerprint("request-one"))
    assert not created and duplicate["id"] == first["id"]
    with pytest.raises(IdempotencyConflict):
        turns.submit("alice", "project", "key", fingerprint("different"))
    assert turns.get("bob", "project", first["id"]) is None
    assert turns.get("alice", "other", first["id"]) is None
    assert "request_fingerprint" not in first and "lease_hash" not in first


def test_separate_processes_claim_a_turn_once(tmp_path):
    path = str(tmp_path / "turns.sqlite3")
    ChatTurns(path)
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(competing_worker, [path] * 8))
    assert len({row[0] for row in results}) == 1
    assert sum(created for _id, created, _lease in results) == 1
    assert sum(lease is not None for _id, _created, lease in results) == 1


def test_project_turns_are_serialized_and_owner_scoped(tmp_path):
    turns = ChatTurns(tmp_path / "turns.sqlite3")
    a, _ = turns.submit("alice", "project", "key-a", fingerprint("one"))
    b, _ = turns.submit("alice", "project", "key-b", fingerprint("two"))
    token_a = turns.claim("alice", "project", a["id"])
    assert token_a
    assert turns.claim("alice", "project", b["id"]) is None
    assert turns.complete("bob", "project", a["id"], token_a, "not yours") is False
    assert turns.complete("alice", "project", a["id"], "wrong-token", "wrong") is False
    assert turns.complete("alice", "project", a["id"], token_a, "answer") is True
    assert turns.get("alice", "project", a["id"])["result"] == "answer"
    assert turns.complete("alice", "project", a["id"], token_a, "again") is False
    assert turns.claim("alice", "project", a["id"]) is None
    assert turns.claim("alice", "project", b["id"])


def test_expired_lease_is_uncertain_and_cannot_be_replayed(tmp_path, monkeypatch):
    import server.proposal.chat_turns as module
    now = [100.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])
    turns = ChatTurns(tmp_path / "turns.sqlite3")
    turn, _ = turns.submit("alice", "project", "key", fingerprint("request"))
    token = turns.claim("alice", "project", turn["id"], lease_seconds=5)
    assert turns.is_lease_valid("alice", "project", turn["id"], token)
    now[0] += 6
    assert not turns.is_lease_valid("alice", "project", turn["id"], token)
    assert turns.complete("alice", "project", turn["id"], token, "late") is False
    assert turns.get("alice", "project", turn["id"])["status"] == "uncertain"
    assert turns.claim("alice", "project", turn["id"]) is None
    duplicate, created = turns.submit("alice", "project", "key", fingerprint("request"))
    assert not created and duplicate["status"] == "uncertain"


def test_renew_and_abandon_never_replay_executed_turns(tmp_path, monkeypatch):
    import server.proposal.chat_turns as module
    now = [200.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])
    turns = ChatTurns(tmp_path / "turns.sqlite3")
    pending, _ = turns.submit("alice", "project", "pending", fingerprint("pending"))
    assert turns.abandon_pending("alice", "project", pending["id"])
    assert turns.get("alice", "project", pending["id"])["status"] == "failed"
    assert turns.claim("alice", "project", pending["id"]) is None
    running, _ = turns.submit("alice", "project", "running", fingerprint("running"))
    token = turns.claim("alice", "project", running["id"], lease_seconds=5)
    assert not turns.abandon_pending("alice", "project", running["id"])
    now[0] += 4
    assert turns.renew("alice", "project", running["id"], token, lease_seconds=5)
    now[0] += 2
    assert turns.is_lease_valid("alice", "project", running["id"], token)
    assert turns.fail("alice", "project", running["id"], token, uncertain=True)
    assert turns.get("alice", "project", running["id"])["status"] == "uncertain"


def test_ledger_does_not_persist_inputs_keys_or_lease_tokens(tmp_path):
    path = tmp_path / "turns.sqlite3"
    turns = ChatTurns(path)
    message = "unpersisted-student-message"
    key = "secret-idempotency-token"
    turn, _ = turns.submit("alice", "project", key, fingerprint(message))
    token = turns.claim("alice", "project", turn["id"])
    with sqlite3.connect(path) as db:
        serialized = repr(db.execute("SELECT * FROM chat_turns").fetchall())
    assert message not in serialized and key not in serialized and token not in serialized
    assert os.stat(path).st_mode & 0o077 == 0
