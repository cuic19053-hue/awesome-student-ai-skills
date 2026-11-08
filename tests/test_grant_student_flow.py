"""Grounded student-grant drafts avoid inventing family and study history."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.chat_context import current_turn_student_facts, grant_placeholder_draft, is_grant_draft_request, scholarship_student_facts
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture
def conversation(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_args, **_kwargs: (None, ""))
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools)
    project = store.create_project()
    store.update_project(project["id"], state={"skill_id": "grant-application"})
    for key, value in {"store": store, "retriever": retriever, "tools": tools, "agent": agent, "CLOUD_MODE": False}.items():
        monkeypatch.setattr(app, key, value)
    monkeypatch.setattr(agent, "_post", lambda *_: pytest.fail("grounded grant draft must not call a model"))
    monkeypatch.setattr(agent, "_stream_post", lambda *_: pytest.fail("grounded grant draft must not call a model"))
    with TestClient(app.app) as client:
        yield client, store, project["id"]


@pytest.mark.parametrize("stream", [False, True])
def test_original_student_request_is_saveable_without_inventing_experiences(conversation, stream):
    client, store, pid = conversation
    response = client.post(f"/api/projects/{pid}/chat", json={"stream": stream,
        "llm_config": {"provider": "preset"}, "message":
        "我叫王明，计算机专业，家庭年收入2万元，帮我写国家助学金申请书。没提供的经历不要编造。"})
    assert response.status_code == 200
    assert all(value in response.text for value in ("王明", "计算机", "2万元", "<WritingBlock"))
    for invented in ("父母务农", "认定已通过", "通过学校审核", "勤工助学", "志愿服务", "全部及格", "家庭债务"):
        assert invented not in response.text
    assert "尚未核验" not in response.text and "本人提供" not in response.text
    assert store.get_workbench_credit_balance("local_user")["free_chat_count"] == 3
    preview = client.get(f"/api/projects/{pid}/chat-drafts").json()
    assert len(preview["items"]) == 1
    assert client.post(f"/api/projects/{pid}/chat-drafts/confirm", json={
        "snapshot": preview["snapshot"], "items": [{"id": preview["items"][0]["id"]}],
    }).status_code == 200
    exported = client.post(f"/api/projects/{pid}/export")
    assert exported.status_code == 200
    word = client.get(exported.json()["download_url"])
    body = "\n".join(p.text for p in Document(io.BytesIO(word.content)).paragraphs)
    assert all(value in body for value in ("王明", "计算机", "2万元"))
    assert "父母务农" not in body and "通过学校审核" not in body


def test_income_conflicts_corrections_and_opt_out():
    initial = [{"role": "user", "content": "我叫王明，计算机专业，家庭年收入2万元。"}]
    facts, conflict = scholarship_student_facts(initial, "请写申请书", [], include_family_income=True)
    assert facts == {"姓名": "王明", "专业": "计算机", "家庭年收入": "2万元"} and not conflict
    contradictory = initial + [{"role": "user", "content": "我的家庭年收入是3万元。"}]
    facts, conflict = scholarship_student_facts(contradictory, "请写申请书", [], include_family_income=True)
    assert "家庭年收入" not in facts and conflict
    facts, conflict = scholarship_student_facts(contradictory, "更正，我的家庭年收入改为4万元。", [], include_family_income=True)
    assert facts["家庭年收入"] == "4万元" and not conflict
    for opt_out in ("请不要使用家庭年收入。", "不要写家庭收入。", "不要把家庭年收入写进去。"):
        facts, _ = scholarship_student_facts(initial + [{"role": "user", "content": opt_out}], "请写申请书", [], include_family_income=True)
        assert "家庭年收入" not in facts
    # Other skill types must not incidentally consume family information.
    assert "家庭年收入" not in current_turn_student_facts(initial[0]["content"])


@pytest.mark.parametrize("instruction", [
    "不要把我家的收入放进申请书。",
    "这次不要提我家的收入。",
    "不写我的家庭年收入。",
    "我的收入不要写进正文。",
    "请不要使用家庭年收入。",
])
def test_natural_omission_request_removes_income_sentence_completely(conversation, instruction):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫王明，计算机专业，家庭年收入2万元。")
    response = client.post(f"/api/projects/{pid}/chat", json={
        "message": instruction + "请重新写国家助学金申请书。",
    })
    assert response.status_code == 200
    assert "王明" in response.text and "计算机" in response.text
    assert "2万元" not in response.text and "收入" not in response.text
    preview = client.get(f"/api/projects/{pid}/chat-drafts").json()
    assert len(preview["items"]) == 1 and "收入" not in preview["items"][0]["content"]


def test_concise_income_correction_replaces_earlier_value_without_extra_identity():
    initial = [{"role": "user", "content": "我叫王明，计算机专业，家庭年收入2万元。"}]
    facts, conflict = scholarship_student_facts(initial, "更正，家庭年收入改为4万元。", [], include_family_income=True)
    assert facts["家庭年收入"] == "4万元" and not conflict
    assert "2万元" not in grant_placeholder_draft(facts=facts, conflicted=conflict)


def test_omitted_income_remains_hidden_until_student_explicitly_allows_it():
    history = [
        {"role": "user", "content": "我叫王明，计算机专业，家庭年收入2万元。"},
        {"role": "user", "content": "不要把我家的收入放进申请书。"},
    ]
    facts, conflict = scholarship_student_facts(history, "请写助学金申请书。", [], include_family_income=True)
    assert "收入" not in grant_placeholder_draft(facts=facts, conflicted=conflict)
    facts, conflict = scholarship_student_facts(history, "现在可以写家庭年收入。", [], include_family_income=True)
    assert facts["家庭年收入"] == "2万元" and not conflict
    assert "2万元" in grant_placeholder_draft(facts=facts, conflicted=conflict)


def test_omission_and_reauthorization_with_bare_rewrite_run_without_model(conversation):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫王明，计算机专业，家庭年收入2万元。")
    url = f"/api/projects/{pid}/chat"
    omitted = client.post(url, json={"message": "不要把我家的收入放进申请书，请重新写。"})
    assert omitted.status_code == 200
    assert "<WritingBlock" in omitted.text and "收入" not in omitted.text
    assert "王明" in omitted.text and "计算机" in omitted.text
    allowed = client.post(url, json={"message": "现在可以写家庭年收入，请重新写。"})
    assert allowed.status_code == 200
    assert "<WritingBlock" in allowed.text and "2万元" in allowed.text


@pytest.mark.parametrize("message", ["不要写申请书。", "先别写申请书，请说说思路。", "请润色申请书。"])
def test_declining_draft_or_requesting_edits_does_not_force_new_letter(conversation, monkeypatch, message):
    client, _, pid = conversation
    calls = []
    monkeypatch.setattr(app.agent, "_post", lambda *_: calls.append(1) or {"message": {"content": "好的，我先回应你的要求。"}})
    response = client.post(f"/api/projects/{pid}/chat", json={"message": message})
    assert response.status_code == 200 and calls == [1]
    assert "<WritingBlock" not in response.text


def test_policy_and_writing_share_the_response_without_asking_model(conversation, monkeypatch):
    client, _, pid = conversation
    monkeypatch.setattr(app.agent, "_policy_evidence_reply", lambda *_: "学校当年通知暂未找到。")
    response = client.post(f"/api/projects/{pid}/chat", json={"message":
        "国家助学金申请条件是什么？我叫王明，计算机专业，家庭年收入2万元，帮我写申请书。"})
    assert response.status_code == 200
    text = response.json()["message"]
    assert "学校当年通知暂未找到" in text and "国家助学金申请书" in text
    assert all(value in text for value in ("王明", "计算机", "2万元"))


@pytest.mark.parametrize("prompt", ["不要写申请书", "先别写申请书，谈谈思路", "请润色申请书", "申请书怎么写", "写助学金申请书提纲"])
def test_non_draft_requests_do_not_force_a_new_grant_letter(prompt):
    assert not is_grant_draft_request(prompt, {"state": {"skill_id": "grant-application"}})


@pytest.mark.parametrize(("name", "confirm", "expected"), [("王明", True, True), ("王明", False, False), ("李华", True, False)])
def test_real_confirmed_source_requires_matching_name(conversation, name, confirm, expected):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫王明，计算机专业。")
    source = f"姓名：{name}\n家庭年收入：2万元".encode("gbk")
    upload = client.post(f"/api/projects/{pid}/documents?kind=source", files={"files": ("资料.txt", source, "text/plain")})
    assert upload.status_code == 200
    document_id = upload.json()["documents"][0]["document"]["id"]
    if confirm:
        assert client.patch(f"/api/documents/{document_id}/confirm", json={"confirmed": True}).status_code == 200
    response = client.post(f"/api/projects/{pid}/chat", json={"message": "请帮我写国家助学金申请书。"})
    assert response.status_code == 200
    assert ("2万元" in response.text) is expected
