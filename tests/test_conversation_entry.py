"""Exercise the chat-first entry and Skill selection through the API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from utils.dispatcher import Dispatcher


@pytest.fixture
def client_and_store(tmp_path, monkeypatch):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "dispatcher", Dispatcher(intent_decider=False, semantic_scorer=lambda _: {}))
    monkeypatch.setattr(agent, "_post", lambda *_: {"message": {"content": "收到，我们继续。"}})
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    with TestClient(app.app) as client:
        yield client, store


def test_start_chat_without_forcing_a_skill_and_route_later(client_and_store):
    client, store = client_and_store
    response = client.post("/api/projects/conversation")
    assert response.status_code == 200
    project = response.json()
    assert project["state"]["skill_id"] == ""
    assert "大创" not in project["messages"][0]["content"]
    first = client.post(f"/api/projects/{project['id']}/chat", json={"message": "你好，帮我整理一下想法"})
    assert first.status_code == 200
    assert store.get_project(project["id"])["state"]["skill_id"] == ""
    second = client.post(f"/api/projects/{project['id']}/chat", json={"message": "我要申请国家奖学金，请帮我列一个准备材料的步骤。"})
    assert second.status_code == 200
    assert "准备" in second.json()["message"] and "材料" in second.json()["message"]
    assert second.json()["setup_updated"] is True
    state = store.get_project(project["id"])["state"]
    assert state["skill_id"] == "national-scholarship"
    assert state["skill_name"] == "国家奖学金"
    # A later mention of a different Skill must not silently switch the project.
    client.post(f"/api/projects/{project['id']}/chat", json={"message": "也介绍一下国家助学金"})
    assert store.get_project(project["id"])["state"]["skill_id"] == "national-scholarship"


def test_ambiguous_skill_request_remains_a_conversation(client_and_store):
    client, store = client_and_store
    project = client.post("/api/projects/conversation").json()
    response = client.post(f"/api/projects/{project['id']}/chat", json={"message": "想申请国家奖学金或者国家励志奖学金"})
    assert response.status_code == 200
    assert store.get_project(project["id"])["state"]["skill_id"] == ""


def test_chat_routing_does_not_invoke_an_extra_model(client_and_store, monkeypatch):
    client, store = client_and_store
    class Decider:
        def decide(self, *_args):
            raise AssertionError("Conversation routing must not launch a second model")
    monkeypatch.setattr(app.dispatcher, "intent_decider", Decider())
    project = client.post("/api/projects/conversation").json()
    response = client.post(f"/api/projects/{project['id']}/chat", json={"message": "我想申请奖学金"})
    assert response.status_code == 200
    assert store.get_project(project["id"])["state"]["skill_id"] == ""


def test_user_can_choose_an_ambiguous_skill_without_losing_history(client_and_store):
    client, store = client_and_store
    project = client.post("/api/projects/conversation").json()
    project_id = project["id"]
    client.post(f"/api/projects/{project_id}/chat", json={"message": "我想申请奖学金"})
    previous = store.messages(project_id)
    invalid = client.post(f"/api/projects/{project_id}/skill", json={"skill_id": "../../unknown"})
    assert invalid.status_code == 422
    response = client.post(f"/api/projects/{project_id}/skill", json={"skill_id": "national-scholarship"})
    assert response.status_code == 200
    assert response.json()["state"]["skill_id"] == "national-scholarship"
    assert store.messages(project_id) == previous
    conflict = client.post(f"/api/projects/{project_id}/skill", json={"skill_id": "grant-application"})
    assert conflict.status_code == 409
    assert store.get_project(project_id)["state"]["skill_id"] == "national-scholarship"
