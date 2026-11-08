"""Ambiguous competition requests are clarified without guessing a track."""
import pytest
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.track_clarification import INTERNET_TRACK_QUESTION
from utils.dispatcher import Dispatcher


@pytest.fixture
def student(tmp_path, monkeypatch):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "dispatcher", Dispatcher(intent_decider=False, semantic_scorer=lambda _: {}))
    monkeypatch.setattr(agent, "_post", lambda *_a, **_k: {"message": {"content": "收到，我们继续整理。"}})
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_a: None)
    with TestClient(app.app) as client:
        yield client, store, client.post("/api/projects/conversation").json()["id"]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(("answer", "skill_id"), [("高教主赛道", "internet-plus"), ("红旅赛道", "internet-plus-red-tour")])
def test_track_question_and_followup_work_without_guessing(student, stream, answer, skill_id):
    client, store, pid = student
    url = f"/api/projects/{pid}/chat"
    first = client.post(url, json={"message": "我想报名中国国际大学生创新大赛，请帮我准备商业计划书。", "stream": stream})
    assert first.status_code == 200 and INTERNET_TRACK_QUESTION in first.text
    assert '"free_chat":false' in first.text.replace(" ", "")
    assert store.get_project(pid)["state"]["skill_id"] == ""
    assert store.get_workbench_credit_balance("local_user")["free_chat_count"] == 3
    response = client.post(url, json={"message": answer})
    assert response.status_code == 200
    state = store.get_project(pid)["state"]
    assert state["skill_id"] == skill_id
    assert "商业计划书" in state["initial_request"] and answer in state["initial_request"]


def test_track_question_does_not_attach_context_to_unrelated_request(student):
    client, store, pid = student
    url = f"/api/projects/{pid}/chat"
    client.post(url, json={"message": "我想参加互联网+，请帮我写商业计划书。"})
    response = client.post(url, json={"message": "我改成申请保研推免，请介绍一下。"})
    assert response.status_code == 200
    assert store.get_project(pid)["state"]["skill_id"] == "graduate-recommendation"


def test_asking_about_tracks_is_not_mistaken_for_a_choice(student):
    client, store, pid = student
    response = client.post(f"/api/projects/{pid}/chat", json={"message": "中国国际大学生创新大赛有哪些赛道？"})
    assert response.status_code == 200
    assert store.get_project(pid)["state"]["skill_id"] == ""
    assert response.json()["message"] != INTERNET_TRACK_QUESTION
