"""The local model timeout should be clear without retrying the request."""
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import LOCAL_MODEL_TIMEOUT_MESSAGE, ModelUnavailable, OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from utils.dispatcher import Dispatcher


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("wrapped", [False, True, "string"])
def test_local_timeout_uses_actionable_message_without_replaying(tmp_path, monkeypatch, stream, wrapped):
    store = Store(tmp_path)
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)), provider="ollama")
    calls = []
    def upstream(*_args, **_kwargs):
        calls.append(1)
        error = TimeoutError("timed out")
        if wrapped:
            raise urllib.error.URLError("timed out" if wrapped == "string" else error)
        raise error
    monkeypatch.setattr("proposal.agent.urllib.request.urlopen", upstream)
    with pytest.raises(ModelUnavailable) as result:
        if stream:
            list(agent._stream_post({"messages": []}))
        else:
            agent._post("/api/chat", {"messages": []})
    assert str(result.value) == LOCAL_MODEL_TIMEOUT_MESSAGE
    assert "超时" in str(result.value) and "自动重复发送" in str(result.value)
    assert "timed out" not in str(result.value) and "Ollama" not in str(result.value)
    assert calls == [1]


def test_connection_refusal_is_not_mislabeled_as_timeout(tmp_path, monkeypatch):
    store = Store(tmp_path)
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)), provider="ollama")
    monkeypatch.setattr("proposal.agent.urllib.request.urlopen", lambda *_a, **_kw: (_ for _ in ()).throw(
        urllib.error.URLError("connection refused")))
    with pytest.raises(ModelUnavailable, match="无法连接本机"):
        list(agent._stream_post({"messages": []}))


def test_real_chat_sse_for_timeout_returns_friendly_error_and_keeps_user_message(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools, provider="ollama")
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "dispatcher", Dispatcher(intent_decider=False, semantic_scorer=lambda _: {}))
    monkeypatch.setattr(app, "_agent_for_config", lambda *_a, **_kw: agent)
    calls = []
    def upstream(*_args, **_kwargs):
        calls.append(1)
        raise TimeoutError("timed out")
    monkeypatch.setattr("proposal.agent.urllib.request.urlopen", upstream)
    with TestClient(app.app) as client:
        pid = client.post("/api/projects/conversation").json()["id"]
        previous_assistant = [item for item in store.messages(pid) if item.get("role") == "assistant"]
        question = "中国大学生创新大赛高教主赛道，帮我写项目简介。"
        response = client.post(f"/api/projects/{pid}/chat?stream=true", json={
            "message": question, "llm_config": {"provider": "ollama"},
        })
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [event["type"] for event in events] == ["status", "error"]
    assert events[-1]["error"] == LOCAL_MODEL_TIMEOUT_MESSAGE
    assert calls == [1]
    history = store.messages(pid)
    assert sum(item.get("content") == question and item.get("role") == "user" for item in history) == 1
    assert [item for item in history if item.get("role") == "assistant"] == previous_assistant
