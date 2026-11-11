"""A personalized scholarship request gets one real, bounded model draft."""
import io
import json

import pytest
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import ModelUnavailable, OllamaAgent
from proposal.chat_context import (is_scholarship_placeholder_request, scholarship_student_facts,
                                   scholarship_placeholder_draft)
from proposal.chat_drafts import candidates
from proposal.chat_safety import INCOMPLETE_DRAFT_PREFIX, PERSONAL_NUMBER_REVIEW_PREFIX
from proposal.scholarship_writing import scholarship_writing_context
from proposal.storage import Store
from proposal.tools import ProposalTools


REQUEST = ("我的资料：姓名：陈林；学院：计算机学院；专业：软件工程；绩点：3.9；排名：2/100。"
           "申请学年2026-2027。我担任班长两年，组织了8次学习互助活动。"
           "请帮我写一份2000字的国家奖学金申请书，语言朴实，重点写班长经历。")
PROJECT = {"state": {"skill_id": "national-scholarship"}}
DRAFT = ('<WritingBlock variant="document">\n## 国家奖学金申请书\n\n尊敬的评审老师：\n\n'
         '我申请2026-2027学年国家奖学金。我叫陈林，我的绩点为3.9，排名为2/100。'
         '我担任班长两年，组织了8次学习互助活动。\n\n此致\n敬礼！\n\n申请人：陈林\n</WritingBlock>')


@pytest.mark.parametrize("prompt", [
    "请写一份国家奖学金申请书", "我叫陈林，绩点3.9，请写申请书，不要编造经历。",
])
def test_basic_starter_remains_model_free(prompt):
    assert is_scholarship_placeholder_request(prompt, PROJECT)


@pytest.mark.parametrize("prompt", [
    REQUEST, "请写2000字国家奖学金申请书", "请写两千字申请书", "请写申请书，语言朴实",
    "请写申请书，重点写班长经历", "我担任班长两年，请写申请书", "请重新写一份，避免套话",
])
def test_personal_writing_requirements_are_not_replaced_with_a_fixed_starter(prompt):
    assert not is_scholarship_placeholder_request(prompt, PROJECT)


def test_explicit_application_year_is_preserved_and_conflicts_are_not_chosen():
    facts, conflict = scholarship_student_facts([], "申请学年2026-2027。请写申请书", [])
    assert facts == {"申请学年": "2026-2027"} and not conflict
    assert "我申请2026-2027学年国家奖学金" in scholarship_placeholder_draft(facts=facts)
    history = [{"role": "user", "content": "申请学年2025-2026。"}]
    facts, conflict = scholarship_student_facts(history, "申请学年2026-2027。", [])
    assert "申请学年" not in facts and conflict
    facts, conflict = scholarship_student_facts(history, "更正，申请学年改为2026-2027。", [])
    assert facts == {"申请学年": "2026-2027"} and not conflict


def setup_agent(tmp_path, monkeypatch):
    store = Store(tmp_path)
    pid = store.create_project()["id"]
    store.update_project(pid, state={"skill_id": "national-scholarship"})
    agent = OllamaAgent(store, ProposalTools(store), model="chosen-model")
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    return store, pid, agent


@pytest.mark.parametrize("stream", [False, True])
def test_custom_draft_uses_selected_model_once_and_preserves_request(tmp_path, monkeypatch, stream):
    store, pid, agent = setup_agent(tmp_path, monkeypatch)
    requests = []
    def respond(_path, payload):
        requests.append(payload)
        return {"message": {"content": DRAFT}}
    def stream_response(payload):
        requests.append(payload)
        yield {"type": "delta", "text": DRAFT}
        yield {"type": "final", "message": {"content": DRAFT}, "usage": None}
    monkeypatch.setattr(agent, "_post", respond)
    monkeypatch.setattr(agent, "_stream_post", stream_response)
    result = list(agent.chat_stream(pid, REQUEST))[-1] if stream else agent.chat(pid, REQUEST)
    assert result["model"] == "chosen-model" and result["message"] == DRAFT
    assert len(requests) == 1 and requests[0]["tools"] == []
    assert requests[0]["options"]["num_predict"] == 4096
    assert requests[0]["response_profile"] == "scholarship_draft"
    assert requests[0]["messages"][-1]["content"] == REQUEST
    prompt = requests[0]["messages"][0]["content"]
    assert '"申请学年": "2026-2027"' in prompt and "班长两年" in prompt and "8次学习互助活动" in prompt
    assert len(store.messages(pid)) == 2 and not store.get_project(pid)["sections"]


def test_earlier_user_experience_is_bounded_and_never_inferred_from_assistant_or_example():
    history = [{"role": "user", "content": "我担任班长两年，组织了8次学习互助活动。"},
               {"role": "assistant", "content": "我获评优秀学生干部，并发表论文。"},
               {"role": "user", "content": "例如：我获得全国一等奖。"}]
    history += [{"role": "user", "content": f"讨论标题{n}"} for n in range(15)]
    context = scholarship_writing_context(history, "请写2000字申请书", {"姓名": "陈林"}, conflicted=False)
    assert "8次学习互助活动" in context and "用户消息1" in context
    assert "优秀学生干部" not in context and "全国一等奖" not in context
    hidden = scholarship_writing_context(history, "不要写我的班长经历，请写2000字申请书", {}, conflicted=False)
    assert "8次学习互助活动" not in hidden
    many = [{"role": "user", "content": f"我组织了第{n}场学习活动。"} for n in range(30)]
    bounded = scholarship_writing_context(many, "请写2000字申请书", {}, conflicted=False)
    assert bounded.count('"quote":') == 8


@pytest.mark.parametrize("stream", [False, True])
def test_provider_length_stop_is_visible_but_not_a_complete_saveable_letter(tmp_path, monkeypatch, stream):
    store, pid, _ = setup_agent(tmp_path, monkeypatch)
    agent = OllamaAgent(store, ProposalTools(store), provider="openai_compatible", model="chosen-model",
                        base_url="https://provider.invalid/v1")
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    calls = []
    def upstream(request, **_kwargs):
        calls.append(json.loads(request.data))
        if stream:
            body = {"choices": [{"delta": {"content": DRAFT}, "finish_reason": "length"}]}
            return io.BytesIO(("data: " + json.dumps(body) + "\n\ndata: [DONE]\n\n").encode())
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": DRAFT}, "finish_reason": "length"}]}).encode())
    monkeypatch.setattr("proposal.agent.urllib.request.urlopen", upstream)
    store.add_message(pid, "user", "请写申请书")
    store.add_message(pid, "assistant", DRAFT)
    assert candidates(store.get_project(pid), store.messages(pid))
    result = list(agent.chat_stream(pid, REQUEST))[-1] if stream else agent.chat(pid, REQUEST)
    assert len(calls) == 1 and result["incomplete"] is True
    assert result["message"].startswith(INCOMPLETE_DRAFT_PREFIX)
    assert "8次学习互助活动" in result["message"] and "<WritingBlock" not in result["message"]
    assert candidates(store.get_project(pid), store.messages(pid)) == []
    assert not store.get_project(pid)["sections"]


def test_custom_model_draft_still_blocks_unsupported_personal_figures(tmp_path, monkeypatch):
    store, pid, agent = setup_agent(tmp_path, monkeypatch)
    monkeypatch.setattr(agent, "_post", lambda *_: {"message": {"content": DRAFT.replace("3.9", "4.9")}})
    result = agent.chat(pid, REQUEST)
    assert result["message"].startswith(PERSONAL_NUMBER_REVIEW_PREFIX)
    assert "<WritingBlock" not in result["message"]
    assert candidates(store.get_project(pid), store.messages(pid)) == []


def test_custom_failure_does_not_automatically_retry_or_replace_with_a_starter(tmp_path, monkeypatch):
    store, pid, agent = setup_agent(tmp_path, monkeypatch)
    calls = []
    def fail(*_):
        calls.append(1)
        raise ModelUnavailable("测试模型失败")
    monkeypatch.setattr(agent, "_post", fail)
    with pytest.raises(ModelUnavailable):
        agent.chat(pid, REQUEST)
    assert calls == [1] and [item["role"] for item in store.messages(pid)] == ["user"]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("prompt", [REQUEST, "我应该怎么准备？请直接写一份2000字国家奖学金申请书，语言朴实。"])
def test_endpoint_authorizes_custom_draft_through_model_configuration(tmp_path, monkeypatch, stream, prompt):
    store, pid, agent = setup_agent(tmp_path, monkeypatch)
    if prompt != REQUEST:
        store.add_message(pid, "user", REQUEST)
    selected = []
    calls = []
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", agent.tools)
    monkeypatch.setattr(app, "agent", agent)
    def configured(config, *_args, **_kwargs):
        selected.append(config.model)
        return agent
    monkeypatch.setattr(app, "_agent_for_config", configured)
    def ordinary_response(_path, payload):
        calls.append(payload)
        return {"message": {"content": DRAFT}}
    monkeypatch.setattr(agent, "_post", ordinary_response)
    def response(payload):
        calls.append(payload)
        yield {"type": "final", "message": {"content": DRAFT}, "usage": None}
    monkeypatch.setattr(agent, "_stream_post", response)
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{pid}/chat", json={"message": prompt, "stream": stream,
            "llm_config": {"provider": "ollama", "model": "chosen-model"}})
    assert response.status_code == 200, response.text
    assert selected == ["chosen-model"] and "班长两年" in response.text
    assert len(calls) == 1 and calls[0]["messages"][-1]["content"] == prompt


@pytest.mark.parametrize("stream", [False, True])
def test_basic_starter_can_still_include_preparation_steps_without_a_model(tmp_path, monkeypatch, stream):
    store, pid, agent = setup_agent(tmp_path, monkeypatch)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", agent.tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "_agent_for_config", lambda *_a, **_k: pytest.fail("starter must remain model-free"))
    monkeypatch.setattr(agent, "_post", lambda *_: pytest.fail("starter must not invoke a model"))
    monkeypatch.setattr(agent, "_stream_post", lambda *_: pytest.fail("starter must not invoke a model"))
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{pid}/chat", json={
            "message": "我应该怎么准备？请先帮我写国家奖学金申请书。", "stream": stream,
            "llm_config": {"provider": "ollama", "model": "chosen-model"},
        })
    assert response.status_code == 200, response.text
    assert "<WritingBlock" in response.text and "找到学校和学院当年的通知" in response.text
