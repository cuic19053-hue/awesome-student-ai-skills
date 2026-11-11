"""External tool work shares the model turn's remaining time budget."""
from __future__ import annotations

import io
import json

import pytest

import server.app
from proposal.agent import ModelUnavailable
from proposal.chat_tools import ChatToolRouter
from proposal import execution_budget as budget
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


def setup_tools(tmp_path):
    store = Store(tmp_path)
    project = store.create_project()
    tools = ProposalTools(store, ProjectRetriever(store))
    return project, tools


def test_budget_is_request_scoped_and_restored_after_failure(monkeypatch):
    monkeypatch.setattr(budget.time, "monotonic", lambda: 100)
    assert budget.remaining_timeout(12) == 12
    with budget.execution_budget(102):
        assert budget.remaining_timeout(12) == 2
        with pytest.raises(budget.ExecutionBudgetExceeded):
            with budget.execution_budget(99):
                pytest.fail("Expired work must not start")
        assert budget.remaining_timeout(12) == 2
    assert budget.remaining_timeout(12) == 12


def test_expired_router_does_not_execute_even_one_tool(tmp_path, monkeypatch):
    project, tools = setup_tools(tmp_path)
    invoked = []
    monkeypatch.setattr(budget.time, "monotonic", lambda: 100)
    monkeypatch.setattr(tools, "invoke", lambda *_: invoked.append(True))
    router = ChatToolRouter(tools, project["id"], project, deadline=99)
    with pytest.raises(budget.ExecutionBudgetExceeded):
        router.invoke({"function": {"name": "get_project_state", "arguments": {}}})
    assert invoked == []


def test_paper_http_timeout_uses_remaining_budget(tmp_path, monkeypatch):
    _, tools = setup_tools(tmp_path)
    timeouts = []
    monkeypatch.setattr(budget.time, "monotonic", lambda: 100)

    class Response(io.BytesIO):
        pass

    def open_request(_request, timeout):
        timeouts.append(timeout)
        return Response(json.dumps({"message": {"items": []}}).encode())

    monkeypatch.setattr("proposal.tools.urllib.request.urlopen", open_request)
    with budget.execution_budget(101.5):
        assert tools.search_papers("测试论文")["results"] == []
    assert timeouts == [1.5]


def test_response_completed_after_deadline_is_not_accepted(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(budget.time, "monotonic", lambda: clock[0])

    class Response:
        def read(self):
            clock[0] = 103
            return b"not a timely result"

    with budget.execution_budget(102):
        with pytest.raises(budget.ExecutionBudgetExceeded):
            budget.read_response(Response())


def test_exhausted_searxng_budget_cannot_start_a_fresh_fallback(tmp_path, monkeypatch):
    _, tools = setup_tools(tmp_path)
    clock = [100.0]
    calls = []
    monkeypatch.setattr(budget.time, "monotonic", lambda: clock[0])
    monkeypatch.setenv("SEARXNG_URL", "https://search.example/")

    def fail_request(_request, timeout):
        calls.append(timeout)
        clock[0] = 103
        raise TimeoutError("not available")

    monkeypatch.setattr("proposal.tools.urllib.request.urlopen", fail_request)
    # remaining_timeout is checked before DDGS is constructed, so its own
    # timeout cannot restart a consumed deadline.
    with budget.execution_budget(102):
        result = tools.search_official_notices("大创")
    assert calls == [2]
    assert "error" in result


def test_chat_stops_before_next_tool_and_does_not_call_model_again(tmp_path, monkeypatch):
    from proposal.agent import OllamaAgent

    project, tools = setup_tools(tmp_path)
    agent = OllamaAgent(tools.store, tools)
    agent._execution_deadline = 102
    clock = [100.0]
    monkeypatch.setattr(budget.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    model_calls = []
    invoked = []

    def model(_path, _payload):
        model_calls.append(True)
        return {"message": {"tool_calls": [
            {"id": str(i), "function": {"name": "search_papers", "arguments": {"query": str(i)}}}
            for i in range(2)
        ]}}

    def invoke(_name, _arguments):
        invoked.append(True)
        clock[0] = 103
        return {"results": []}

    monkeypatch.setattr(agent, "_post", model)
    monkeypatch.setattr(tools, "invoke", invoke)
    with pytest.raises(ModelUnavailable, match="没有自动重试"):
        agent.chat(project["id"], "请查一下真实论文")
    assert len(invoked) == 1
    assert len(model_calls) == 1
