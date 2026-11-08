"""Tool-call IDs stay consistent through the full model/tool/model loop."""
from __future__ import annotations

import io
import json

import pytest

import server.app  # Registers the proposal package path.
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


def sse(data):
    return ("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("upstream_ids", [False, True])
def test_gateway_tool_ids_match_results_across_model_turns(tmp_path, monkeypatch, stream, upstream_ids):
    store = Store(tmp_path)
    project = store.create_project(title="工具调用测试")
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools, provider="openai_compatible",
                        base_url="https://model.example.test/v1", model="test-model", api_key="test-key")
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    requests = []

    def upstream(request, **_kwargs):
        body = json.loads(request.data)
        requests.append(body)
        if len(requests) == 1:
            calls = [{
                **({"id": f"gateway-{index}"} if upstream_ids else {}),
                "type": "function", "function": {"name": "get_project_state", "arguments": "{}"},
            } for index in range(2)]
            if stream:
                delta = [{**call, "index": index} for index, call in enumerate(calls)]
                return io.BytesIO(sse({"choices": [{"delta": {"tool_calls": delta}}]})
                                  + sse({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]})
                                  + b"data: [DONE]\n\n")
            return io.BytesIO(json.dumps({"choices": [{"message": {"tool_calls": calls}}]}).encode())

        messages = body["messages"]
        assistant = next(item for item in messages if item.get("tool_calls"))
        tool_ids = [call["id"] for call in assistant["tool_calls"]]
        result_ids = [item["tool_call_id"] for item in messages if item["role"] == "tool"]
        assert len(tool_ids) == 2 and len(set(tool_ids)) == 2
        assert tool_ids == result_ids
        if upstream_ids:
            assert tool_ids == ["gateway-0", "gateway-1"]
        if stream:
            return io.BytesIO(sse({"choices": [{"delta": {"content": "读取成功"}, "finish_reason": "stop"}]})
                              + b"data: [DONE]\n\n")
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": "读取成功"}}]},
                                     ensure_ascii=False).encode())

    monkeypatch.setattr("proposal.agent.urllib.request.urlopen", upstream)
    if stream:
        events = list(agent.chat_stream(project["id"], "请查看当前项目"))
        assert events[-1]["type"] == "done" and events[-1]["message"] == "读取成功"
    else:
        assert agent.chat(project["id"], "请查看当前项目")["message"] == "读取成功"
    assert len(requests) == 2
