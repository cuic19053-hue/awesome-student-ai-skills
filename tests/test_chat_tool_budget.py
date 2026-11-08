"""Avoid repeated or unbounded tool work within one student conversation turn."""
import json

import server.app  # Add the server module path for proposal imports.
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


def _setup(tmp_path, monkeypatch, first_calls):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "innovation-research"})
    tools = ProposalTools(store, ProjectRetriever(store))
    invocations = []
    monkeypatch.setattr(tools, "invoke", lambda name, args: invocations.append((name, args)) or {"results": []})
    agent = OllamaAgent(store, tools)
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_a: None)
    payloads = []
    def reply(_path, payload):
        payloads.append(payload)
        if len(payloads) == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": first_calls}}
        return {"message": {"content": "已经整理现有资料。"}}
    monkeypatch.setattr(agent, "_post", reply)
    return store, project_id, agent, invocations, payloads


def _call(index, query):
    return {"id": f"call-{index}", "function": {"name": "search_project_materials", "arguments": {"query": query}}}


def test_duplicate_read_only_calls_are_reused_but_keep_each_tool_result(tmp_path, monkeypatch):
    store, pid, agent, invoked, payloads = _setup(tmp_path, monkeypatch, [_call(1, "校园调研"), _call(2, "校园调研")])
    result = agent.chat(pid, "查找现有项目资料。")
    assert result["message"] == "已经整理现有资料。" and len(invoked) == 1
    responses = [item for item in payloads[1]["messages"] if item["role"] == "tool"]
    assert len(responses) == 2 and {item["tool_call_id"] for item in responses} == {"call-1", "call-2"}


def test_one_response_cannot_trigger_unbounded_tool_calls(tmp_path, monkeypatch):
    calls = [_call(i, f"不同问题{i}") for i in range(12)]
    store, pid, agent, invoked, payloads = _setup(tmp_path, monkeypatch, calls)
    result = agent.chat(pid, "查找现有项目资料。")
    assert result["message"] == "已经整理现有资料。"
    assert len(invoked) == 8
    assert payloads[1]["tools"] == []
    responses = [item for item in payloads[1]["messages"] if item["role"] == "tool"]
    assert len(responses) == 12
    assert all("达到上限" in json.loads(item["content"])["error"] for item in responses[8:])
