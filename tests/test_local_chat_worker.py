"""At-most-once local worker: isolated database and fake provider only."""
from __future__ import annotations

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import server.app  # Makes the proposal package importable.
from proposal.agent import OllamaAgent
from proposal.chat_turns import ChatTurns, IdempotencyConflict
from proposal.local_chat_worker import LocalChatWorker, _fingerprint
from proposal.storage import Store
from proposal.tools import ProposalTools


def setup(tmp_path, post, *, lease_seconds=120):
    store = Store(tmp_path / "projects")
    project = store.create_project(title="隔离测试")
    turns = ChatTurns(tmp_path / "turns.sqlite3")

    def factory():
        agent = OllamaAgent(store, ProposalTools(store))
        agent._post = post
        agent._policy_evidence_reply = lambda *_: None
        return agent

    return store, project["id"], turns, LocalChatWorker(store, turns, factory, lease_seconds=lease_seconds)


def wait_for(worker, project_id, turn_id, statuses, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = worker.get(project_id, turn_id)
        if result and result["status"] in statuses:
            return result
        time.sleep(.01)
    pytest.fail("turn did not reach expected status")


def test_fast_completion_and_duplicate_never_run_twice(tmp_path):
    calls = []
    def post(*_args, **_kwargs):
        calls.append(1)
        return {"message": {"content": "已完成"}}
    store, project_id, turns, worker = setup(tmp_path, post)
    try:
        # Completing before add_done_callback is attached must not deadlock.
        with ThreadPoolExecutor(max_workers=1) as executor:
            turn = executor.submit(worker.submit, project_id, "retry-key", "测试问题").result(timeout=3)
        result = wait_for(worker, project_id, turn["id"], {"completed"})
        assert result["result"] == "已完成"
        duplicate = worker.submit(project_id, "retry-key", "测试问题")
        assert duplicate["id"] == turn["id"]
        assert calls == [1]
        assert [item["role"] for item in store.messages(project_id)] == ["user", "assistant"]
        with pytest.raises(IdempotencyConflict):
            worker.submit(project_id, "retry-key", "不同的问题")
    finally:
        worker.shutdown()


def test_busy_project_never_leaves_a_phantom_pending_job(tmp_path):
    started, release = threading.Event(), threading.Event()
    calls = []
    def post(*_args, **_kwargs):
        calls.append(1)
        started.set()
        assert release.wait(3)
        return {"message": {"content": "完成"}}
    store, project_id, turns, worker = setup(tmp_path, post)
    try:
        first = worker.submit(project_id, "first", "一")
        assert started.wait(3)
        second = worker.submit(project_id, "second", "二")
        assert second["status"] == "failed"
        assert worker.submit(project_id, "second", "二")["status"] == "failed"
        release.set()
        assert wait_for(worker, project_id, first["id"], {"completed"})["result"] == "完成"
        assert calls == [1]
    finally:
        release.set()
        worker.shutdown()


def test_explicit_identical_retry_can_start_a_known_unstarted_turn(tmp_path):
    calls = []
    def post(*_args, **_kwargs):
        calls.append(1)
        return {"message": {"content": "完成"}}
    store, project_id, turns, worker = setup(tmp_path, post)
    try:
        agent = worker.agent_factory()
        pending, created = turns.submit("local_user", project_id, "retry-pending",
                                        _fingerprint(project_id, "原始消息", agent))
        assert created and pending["status"] == "pending"
        with pytest.raises(IdempotencyConflict):
            worker.submit(project_id, "retry-pending", "其他消息")
        retried = worker.submit(project_id, "retry-pending", "原始消息")
        assert retried["id"] == pending["id"]
        assert wait_for(worker, project_id, retried["id"], {"completed"})["result"] == "完成"
        assert calls == [1]
    finally:
        worker.shutdown()


def test_uncertain_error_does_not_leak_or_retry(tmp_path):
    calls = []
    secret = "sensitive-provider-error-never-show"
    def post(*_args, **_kwargs):
        calls.append(1)
        raise RuntimeError(secret)
    store, project_id, turns, worker = setup(tmp_path, post)
    try:
        turn = worker.submit(project_id, "key", "问题")
        result = wait_for(worker, project_id, turn["id"], {"uncertain"})
        assert secret not in str(result)
        assert worker.submit(project_id, "key", "问题")["status"] == "uncertain"
        assert calls == [1]
        with sqlite3.connect(turns.db_path) as db:
            assert secret not in str(db.execute("SELECT * FROM chat_turns").fetchall())
    finally:
        worker.shutdown()


def test_expired_call_cannot_publish_reply_or_restart(tmp_path):
    started, release = threading.Event(), threading.Event()
    calls = []
    def post(*_args, **_kwargs):
        calls.append(1)
        started.set()
        assert release.wait(4)
        return {"message": {"content": "不应保存的过期答复"}}
    store, project_id, turns, worker = setup(tmp_path, post, lease_seconds=1)
    try:
        turn = worker.submit(project_id, "expired", "问题")
        assert started.wait(3)
        time.sleep(1.05)
        assert turns.expire() == 1
        release.set()
        worker.shutdown()
        assert worker.get(project_id, turn["id"])["status"] == "uncertain"
        assert not any(m["role"] == "assistant" for m in store.messages(project_id))
        assert calls == [1]
    finally:
        release.set()
        worker.shutdown()


def test_refuses_cloud_or_paid_agents(tmp_path):
    store, project_id, turns, worker = setup(tmp_path, lambda *_: {})
    worker.shutdown()
    def remote_factory():
        return OllamaAgent(store, ProposalTools(store), provider="openai_compatible",
                           base_url="https://example.test/v1", api_key="secret")
    remote_worker = LocalChatWorker(store, turns, remote_factory)
    try:
        with pytest.raises(ValueError, match="local Ollama"):
            remote_worker.submit(project_id, "remote", "问题")
    finally:
        remote_worker.shutdown()


def test_same_key_with_changed_model_config_conflicts(tmp_path):
    store = Store(tmp_path / "projects")
    project_id = store.create_project()["id"]
    turns = ChatTurns(tmp_path / "turns.sqlite3")
    model = ["first-model"]

    def factory():
        agent = OllamaAgent(store, ProposalTools(store), model=model[0])
        agent._post = lambda *_: {"message": {"content": "完成"}}
        agent._policy_evidence_reply = lambda *_: None
        return agent

    worker = LocalChatWorker(store, turns, factory)
    try:
        turn = worker.submit(project_id, "same-key", "相同输入")
        wait_for(worker, project_id, turn["id"], {"completed"})
        model[0] = "other-model"
        with pytest.raises(IdempotencyConflict):
            worker.submit(project_id, "same-key", "相同输入")
    finally:
        worker.shutdown()
