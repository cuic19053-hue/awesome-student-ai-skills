"""Experimental API stays local, opt-in and safe under repeated submission."""
from __future__ import annotations

import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture
def local_client(tmp_path, monkeypatch):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    calls = []
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    monkeypatch.setattr(agent, "_post", lambda *_: calls.append(1) or {"message": {"content": "本地结果"}})
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "OllamaAgent", lambda *_args, **_kwargs: agent)
    with TestClient(app.app) as client:
        yield client, store, calls


def test_experimental_local_worker_is_disabled_by_default(local_client, monkeypatch):
    client, store, _calls = local_client
    monkeypatch.delenv("LOCAL_CHAT_WORKER_ENABLED", raising=False)
    project = store.create_project()
    response = client.post(f"/api/experimental/local-chat/{project['id']}/turns", json={
        "message": "测试", "idempotency_key": "test-key",
    })
    assert response.status_code == 404
    assert not (store.data_dir / "local-chat-turns.sqlite3").exists()


def test_cloud_cannot_enable_local_worker_even_if_flag_is_set(monkeypatch):
    monkeypatch.setenv("LOCAL_CHAT_WORKER_ENABLED", "true")
    monkeypatch.setattr(app, "CLOUD_MODE", True)
    with pytest.raises(HTTPException) as error:
        app.local_chat_service.get_worker()
    assert error.value.status_code == 404


def test_local_turn_can_be_polled_and_same_request_is_not_replayed(local_client, monkeypatch):
    client, store, calls = local_client
    monkeypatch.setenv("LOCAL_CHAT_WORKER_ENABLED", "true")
    project = store.create_project()
    project_id = project["id"]
    url = f"/api/experimental/local-chat/{project_id}/turns"
    body = {"message": "测试对话", "idempotency_key": "same-key"}
    first = client.post(url, json=body)
    assert first.status_code == 200
    turn_id = first.json()["id"]
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = client.get(f"{url}/{turn_id}").json()
        if result["status"] == "completed":
            break
        time.sleep(.01)
    assert result["status"] == "completed"
    assert result["result"] == "本地结果"
    assert client.post(url, json=body).json()["id"] == turn_id
    assert calls == [1]
    conflict = client.post(url, json={**body, "message": "不一样的输入"})
    assert conflict.status_code == 409
    assert len(store.messages(project_id)) == 2
