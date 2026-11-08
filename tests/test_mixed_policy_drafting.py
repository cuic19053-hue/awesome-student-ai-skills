"""Mixed questions retain verified evidence and run writing through billing."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.chat_context import fallback_scholarship_draft, without_policy_claims
from proposal.knowledge import mixed_drafting_request, is_policy_question
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.mark.parametrize("query", [
    "学校的申报条件是什么？帮我写申请书",
    "请先告诉我申报条件有哪些，再帮我写申请书",
    "帮我写申请书，同时确认截止时间是几号？",
    "我能申请国家奖学金吗？帮我起草材料",
    "请帮我写申请书并告诉我条件",
    "绩点多少可以申请国家奖学金？请重新写国家奖学金申请书。",
])
def test_policy_clause_is_separated_from_writing(query):
    assert is_policy_question(query)
    draft = mixed_drafting_request(query)
    assert draft and not is_policy_question(draft)
    assert not any(word in draft for word in ("申报条件", "截止时间", "能申请", "告诉我条件"))


def test_cannot_isolate_combined_clause_keeps_evidence_only():
    query = "申报条件是多少帮我写申请书"
    assert is_policy_question(query)
    assert mixed_drafting_request(query) is None


@pytest.mark.parametrize("claim", [
    "你可以申请国家奖学金。", "申请人必须为二年级以上。", "奖学金金额10000元。", "截止时间是本周。",
])
def test_generated_policy_claims_are_not_in_draft(claim):
    text = claim + "尊敬的老师：我申请【项目名称待补充】。"
    output = without_policy_claims(text)
    assert claim not in output
    assert "尊敬的老师" in output


LIST_ONLY = "请提供以下信息：\n1. 姓名\n2. 学院\n3. 排名\n4. 经历"


def test_mixed_scholarship_draft_request_gets_a_placeholder_draft_when_model_only_asks_for_information():
    text = fallback_scholarship_draft(LIST_ONLY, "请帮我写申请书", {"state": {"skill_id": "national-scholarship"}})
    assert '<WritingBlock variant="document">' in text
    assert "国家奖学金申请书" in text and "【姓名待补充】" in text
    assert "申请学年待补充" in text
    assert "已保存" not in text
    assert "10000" not in text and "专业第一" not in text
    assert without_policy_claims(text) == text


@pytest.mark.parametrize(("draft_text", "skill", "answer"), [
    ("请润色申请书", "national-scholarship", LIST_ONLY),
    ("请写申请书", "grant-application", LIST_ONLY),
    ("写一份调研报告", "national-scholarship", LIST_ONLY),
    ("请写申请书", "national-scholarship", "尊敬的老师：\n本人申请【待补充】。\n\n1. 学习情况\n2. 科研情况\n3. 实践情况。"),
    ("请写申请书", "national-scholarship", '<WritingBlock variant="document">\n## 申请书\n正文\n</WritingBlock>'),
])
def test_placeholder_fallback_does_not_replace_other_requests_or_real_drafts(draft_text, skill, answer):
    assert fallback_scholarship_draft(answer, draft_text, {"state": {"skill_id": skill}}) == answer


@pytest.mark.parametrize("stream", [False, True])
def test_mixed_question_uses_configured_model_and_only_evidence_can_answer_policy(tmp_path, monkeypatch, stream):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    project = store.create_project(title="混合意图")
    store.update_project(project["id"], state={
        "skill_id": "outstanding-cadre",
        "initial_request": "学校的申报条件是什么？帮我写申请书",
    })
    requests = []
    selected = []
    trusted = "已检索官方通知：请核对学校和年度。"
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: trusted)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)

    def configured(config, *_args, **_kwargs):
        selected.append(config.provider)
        return agent

    monkeypatch.setattr(app, "_agent_for_config", configured)
    content = "申请者必须为二年级以上。尊敬的老师：我申请【项目名称待补充】。"
    if stream:
        def fake_stream(payload):
            requests.append(payload)
            yield {"type": "delta", "text": content}
            yield {"type": "final", "message": {"content": content}, "usage": None}
        monkeypatch.setattr(agent, "_stream_post", fake_stream)
    else:
        def fake_post(_endpoint, payload):
            requests.append(payload)
            return {"message": {"content": content}}
        monkeypatch.setattr(agent, "_post", fake_post)
    client = TestClient(app.app)
    response = client.post(f"/api/projects/{project['id']}/chat", json={
        "message": "学校的申报条件是什么？帮我写申请书", "stream": stream,
        "llm_config": {"provider": "ollama", "model": "mock"},
    })
    assert response.status_code == 200
    assert selected == ["ollama"]
    assert len(requests) == 1
    assert requests[0]["messages"][-1]["content"].startswith("帮我写申请书\n请先直接给出可编辑草稿")
    assert "已检索官方通知" not in str(requests[0]["messages"])
    assert "学校的申报条件是什么？帮我写申请书" not in str(requests[0]["messages"])
    assert "信息不足时用【待补充】占位" in requests[0]["messages"][0]["content"]
    assert "不要只列资料清单" in requests[0]["messages"][0]["content"]
    offered = {schema["function"]["name"] for schema in requests[0]["tools"]}
    assert "search_public_knowledge" not in offered
    assert "save_project_fact" not in offered
    assert trusted in response.text
    assert "申请者必须为二年级以上" not in response.text
    assert "尊敬的老师" in response.text
    assert store.messages(project["id"])[-1]["content"].startswith("【政策资料核查】")


def test_pure_policy_question_still_never_invokes_model(tmp_path, monkeypatch):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    project = store.create_project()
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: "官方资料暂缺")
    monkeypatch.setattr(agent, "_post", lambda *_: pytest.fail("policy-only must not call model"))
    response = TestClient(app.app).post(f"/api/projects/{project['id']}/chat", json={"message": "申报条件是什么？"})
    assert response.status_code == 200
    assert response.json()["message"] == "官方资料暂缺"
    assert response.json()["free_chat"] is False


def test_inseparable_mixed_intent_does_not_pretend_writing_was_done(tmp_path, monkeypatch):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    project = store.create_project()
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: "官方资料暂缺")
    monkeypatch.setattr(agent, "_post", lambda *_: pytest.fail("inseparable request must not call model"))
    response = TestClient(app.app).post(f"/api/projects/{project['id']}/chat", json={"message": "申报条件是多少帮我写申请书"})
    assert response.status_code == 200
    assert "官方资料暂缺" in response.json()["message"]
    assert "写作请求还没有执行" in response.json()["message"]


@pytest.mark.parametrize("stream", [False, True])
def test_mixed_scholarship_uses_placeholder_draft_without_model_in_api(tmp_path, monkeypatch, stream):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    project = store.create_project()
    store.update_project(project["id"], state={"skill_id": "national-scholarship"})
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: "官方资料暂缺")
    monkeypatch.setattr(agent, "_stream_post", lambda *_: pytest.fail("placeholder must not call model"))
    monkeypatch.setattr(agent, "_post", lambda *_: pytest.fail("placeholder must not call model"))
    response = TestClient(app.app).post(f"/api/projects/{project['id']}/chat", json={
        "message": "申报条件是什么？请帮我写申请书", "stream": stream,
    })
    assert response.status_code == 200
    assert "官方资料暂缺" in response.text
    assert "【姓名待补充】" in response.text
    assert "写作内容" in response.text
    assert "请补充【待补充】的内容" in response.text


def test_placeholder_path_does_not_claim_to_use_existing_facts_or_charge_trial(tmp_path, monkeypatch):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    project = store.create_project()
    store.update_project(project["id"], state={
        "skill_id": "national-scholarship", "confirmed_facts": {"gpa": "3.9", "budget": "1200"},
    })
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: "官方资料暂缺")
    monkeypatch.setattr(agent, "_post", lambda *_: pytest.fail("placeholder must not call model"))
    response = TestClient(app.app).post(f"/api/projects/{project['id']}/chat", json={
        "message": "我叫张三，申报条件是什么？请帮我写申请书", "llm_config": {"provider": "preset"},
    })
    assert response.status_code == 200
    assert response.json()["free_chat"] is False
    assert store.get_workbench_credit_balance("local_user")["free_chat_count"] == 3
    assert "请补充【待补充】的内容" in response.json()["message"]
    assert "张三" in response.json()["message"]
    assert "3.9" not in response.json()["message"]


def test_mixed_preset_uses_trial_accounting_once(tmp_path, monkeypatch):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    project = store.create_project()
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "OllamaAgent", lambda *_args, **_kwargs: agent)
    monkeypatch.setattr(app, "_platform_bundle_ready", lambda: True)
    monkeypatch.setenv("WOPALLY_MODEL_BASE_URL", "https://test.example/v1")
    monkeypatch.setenv("WOPALLY_WORKBENCH_API_KEY", "test-only")
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: "官方资料暂缺")
    monkeypatch.setattr(agent, "_post", lambda *_: {"message": {"content": "申请书草稿：待补充。"}})
    response = TestClient(app.app).post(f"/api/projects/{project['id']}/chat", json={
        "message": "申报条件是什么？帮我写申请书", "llm_config": {"provider": "preset"},
    })
    assert response.status_code == 200
    assert response.json()["free_chat"] is True
    assert response.json()["free_chats_remaining"] == 2
    assert store.get_workbench_credit_balance("local_user")["free_chat_count"] == 2
