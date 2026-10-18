import io
import json

import pytest

import server.app  # Registers the server module path.
from proposal.agent import ModelUnavailable, OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.workbench_metering import WorkbenchMeter


def make_agent(tmp_path, *, paid=True):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    meter = None
    if paid:
        store.grant_workbench_payment_credits("alice", "test-payment", 1_000_000)
        meter = WorkbenchMeter(store, "alice", 684)
    return store, meter, OllamaAgent(
        store, tools, provider="openai_compatible", model="deepseek-v4-flash",
        base_url="https://api.wopally.cn/v1", api_key="fake-key",
        meter=meter, platform_transport=True,
    )


@pytest.mark.parametrize("content", [None, "", " \n\t"])
def test_reasoning_only_or_blank_reply_refunds_before_settlement(tmp_path, monkeypatch, content):
    store, meter, agent = make_agent(tmp_path)
    calls = []

    def upstream(request, timeout=0):
        calls.append(json.loads(request.data))
        return io.BytesIO(json.dumps({
            "choices": [{"finish_reason": "length", "message": {
                "content": content, "reasoning_content": "private reasoning must never be exposed",
            }}],
            "usage": {"prompt_tokens": 10000, "completion_tokens": 2048},
        }).encode())

    monkeypatch.setattr("proposal.agent.wopally_urlopen", upstream)
    monkeypatch.setattr(meter, "settle", lambda *_: pytest.fail("Blank answers must not be settled"))
    with pytest.raises(ModelUnavailable, match="预留积分") as error:
        agent._post("/api/chat", {"messages": [{"role": "user", "content": "test"}]})
    assert "private reasoning" not in str(error.value)
    assert len(calls) == 1
    assert calls[0]["thinking"] == {"type": "disabled"}
    assert calls[0]["max_tokens"] == 2048
    wallet = store.get_workbench_credit_balance("alice")
    assert wallet["balance_micro_cny"] == 1_000_000
    assert wallet["total_spent_micro_cny"] == 0
    assert store.pending_workbench_usage("alice") == []
    transactions = store.get_workbench_credit_transactions("alice")
    assert any(tx["kind"] == "usage_refund" for tx in transactions)
    assert not any(tx["kind"] == "usage_settle" for tx in transactions)


@pytest.mark.parametrize("tool_call", [False, True])
def test_visible_answers_and_legitimate_tool_only_responses_still_settle(tmp_path, monkeypatch, tool_call):
    store, meter, agent = make_agent(tmp_path)
    message = {"content": "有意义的回答"}
    if tool_call:
        message = {"content": None, "tool_calls": [{
            "id": "call-one", "type": "function", "function": {
                "name": "search_project_materials", "arguments": '{"query":"背景"}',
            },
        }]}
    monkeypatch.setattr(
        "proposal.agent.wopally_urlopen",
        lambda *_args, **_kwargs: io.BytesIO(json.dumps({"choices": [{"message": message}]}).encode()),
    )
    meter.usage.find = lambda *_: (10_000, "provider-test-record")
    result = agent._post("/api/chat", {"messages": [{"role": "user", "content": "test"}]})
    assert bool(result["message"]["tool_calls"]) is tool_call
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 990_000


def test_free_platform_also_disables_thinking_and_rejects_blank_content(tmp_path, monkeypatch):
    _store, _meter, agent = make_agent(tmp_path, paid=False)
    bodies = []

    def upstream(request, **_kwargs):
        bodies.append(json.loads(request.data))
        return io.BytesIO(b'{"choices":[{"message":{"content":null}}]}')

    monkeypatch.setattr("proposal.agent.wopally_urlopen", upstream)
    with pytest.raises(ModelUnavailable, match="未返回可用正文"):
        agent._post("/api/chat", {"messages": []})
    assert bodies[0]["thinking"] == {"type": "disabled"}
    assert bodies[0]["max_tokens"] == 2048


def test_byok_does_not_force_provider_specific_thinking_configuration(tmp_path, monkeypatch):
    _store, _meter, agent = make_agent(tmp_path, paid=False)
    agent.platform_transport = False
    bodies = []

    def upstream(request, **_kwargs):
        bodies.append(json.loads(request.data))
        return io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')

    monkeypatch.setattr("proposal.agent.urllib.request.urlopen", upstream)
    assert agent._post("/api/chat", {"messages": []})["message"]["content"] == "ok"
    assert "thinking" not in bodies[0]


def test_chat_never_saves_blank_assistant_messages_even_for_other_adapters(tmp_path, monkeypatch):
    store, _meter, agent = make_agent(tmp_path, paid=False)
    project = store.create_project(title="空答复防护回归")
    monkeypatch.setattr(agent, "_post", lambda *_: {"message": {"content": None}})
    with pytest.raises(ModelUnavailable, match="未返回可用正文"):
        agent.chat(project["id"], "请帮我核对材料")
    assert not any(item["role"] == "assistant" for item in store.messages(project["id"]))
