"""Student and Youth League drafts use only bounded, grounded user information."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.chat_context import is_outstanding_draft_request, scholarship_student_facts
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from utils.dispatcher import Dispatcher


@pytest.fixture
def conversation(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_args, **_kwargs: (None, ""))
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools)
    project = store.create_project()
    store.update_project(project["id"], state={"skill_id": "outstanding-student"})
    for name, value in {"store": store, "retriever": retriever, "tools": tools, "agent": agent, "CLOUD_MODE": False}.items():
        monkeypatch.setattr(app, name, value)
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    monkeypatch.setattr(agent, "_post", lambda *_: pytest.fail("grounded student draft must not call a model"))
    monkeypatch.setattr(agent, "_stream_post", lambda *_: pytest.fail("grounded student draft must not call a model"))
    with TestClient(app.app) as client:
        yield client, store, project["id"]


@pytest.mark.parametrize("stream", [False, True])
def test_student_draft_is_saveable_and_does_not_invent_history(conversation, stream):
    client, store, pid = conversation
    response = client.post(f"/api/projects/{pid}/chat", json={"stream": stream,
        "llm_config": {"provider": "preset"}, "message":
        "我叫李明，学计算机专业，绩点3.8，专业排名3/80，请帮我写优秀学生申请书。没有科研经历。"})
    assert response.status_code == 200
    assert all(value in response.text for value in ("李明", "计算机", "3.8", "3/80", "优秀学生申请书", "<WritingBlock"))
    assert "目前我暂无科研经历" in response.text
    assert "优秀团员申请书" not in response.text
    assert all(invented not in response.text for invented in ("预备党员", "组织团日", "优秀干部", "志愿100小时", "4.0制"))
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
    assert "李明" in body and "3.8" in body


@pytest.mark.parametrize(("prompt", "title", "work"), [
    ("请帮我写三好学生申请书", "三好学生申请书", "学生工作"),
    ("请帮我写优秀团员申请书", "优秀团员申请书", "团务工作"),
])
def test_selected_type_is_preserved(conversation, prompt, title, work):
    client, _, pid = conversation
    result = client.post(f"/api/projects/{pid}/chat", json={"message": prompt})
    assert result.status_code == 200 and title in result.text and work in result.text
    assert "我的政治面貌是团员" not in result.text


def test_ambiguous_type_asks_once_and_followup_is_saveable(conversation):
    client, store, pid = conversation
    url = f"/api/projects/{pid}/chat"
    ask = client.post(url, json={"message": "请帮我写申请书。"})
    assert ask.status_code == 200 and "优秀团员" in ask.text and "<WritingBlock" not in ask.text
    answer = client.post(url, json={"message": "优秀团员"})
    assert answer.status_code == 200 and "优秀团员申请书" in answer.text
    assert len(client.get(f"/api/projects/{pid}/chat-drafts").json()["items"]) == 1
    assert store.get_workbench_credit_balance("local_user")["free_chat_count"] == 3


@pytest.mark.parametrize("prompt", ["不要写优秀学生申请书", "先别写申请书，请谈思路", "请润色优秀团员申请书", "优秀学生申请书怎么写", "写优秀学生申请书提纲"])
def test_edit_and_negative_requests_do_not_trigger_new_draft(prompt):
    assert not is_outstanding_draft_request(prompt, {"state": {"skill_id": "outstanding-student"}})


def test_correction_and_uploaded_material_remain_project_scoped(conversation):
    client, store, pid = conversation
    url = f"/api/projects/{pid}/chat"
    store.add_message(pid, "user", "我叫李明，学计算机专业，绩点3.8。我要申请优秀学生。")
    uploaded = client.post(f"/api/projects/{pid}/documents?kind=source", files={
        "files": ("资料.txt", "姓名：李明\n学院：信息学院\n获奖：数学建模二等奖".encode("gbk"), "text/plain"),
    }).json()["documents"][0]["document"]
    # Unconfirmed source material must not appear.
    unconfirmed = client.post(url, json={"message": "请帮我写优秀学生申请书。"}).json()["message"]
    assert "数学建模二等奖" not in unconfirmed
    assert client.patch(f"/api/documents/{uploaded['id']}/confirm", json={"confirmed": True}).status_code == 200
    result = client.post(url, json={"message": "更正，我的绩点改为3.7。请重新写申请书。"}).json()["message"]
    assert "3.7" in result and "3.8" not in result
    assert "信息学院" in result and "数学建模二等奖" in result
    other = store.create_project()
    store.update_project(other["id"], state={"skill_id": "outstanding-student"})
    foreign = client.post(f"/api/projects/{other['id']}/chat", json={"message": "请帮我写优秀学生申请书。"}).json()["message"]
    assert "李明" not in foreign and "数学建模二等奖" not in foreign


def test_mixed_policy_uses_evidence_and_safe_draft(conversation, monkeypatch):
    client, _, pid = conversation
    monkeypatch.setattr(app.agent, "_policy_evidence_reply", lambda *_: "学校当年通知暂未找到。")
    response = client.post(f"/api/projects/{pid}/chat", json={"message": "优秀团员的申报条件是什么？帮我写优秀团员申请书。"})
    assert response.status_code == 200
    assert "学校当年通知暂未找到" in response.text and "优秀团员申请书" in response.text


def test_chat_first_routes_to_outstanding_student_without_extra_model(conversation, monkeypatch):
    client, store, _ = conversation
    monkeypatch.setattr(app, "dispatcher", Dispatcher(intent_decider=False, semantic_scorer=lambda _: {}))
    project = client.post("/api/projects/conversation").json()
    response = client.post(f"/api/projects/{project['id']}/chat", json={
        "message": "我叫李明，学计算机专业，绩点3.8，请帮我写三好学生申请书。",
    })
    assert response.status_code == 200 and "三好学生申请书" in response.text and "李明" in response.text
    assert store.get_project(project["id"])["state"]["skill_id"] == "outstanding-student"


def test_field_omissions_are_not_mistaken_for_a_refusal_to_draft(conversation):
    client, store, pid = conversation
    url = f"/api/projects/{pid}/chat"
    store.add_message(pid, "user", "我叫李明，学计算机专业，绩点3.8。我要申请优秀学生。")
    result = client.post(url, json={"message": "不要写科研经历和绩点，请重新写优秀学生申请书。"})
    assert result.status_code == 200 and "<WritingBlock" in result.text
    assert "李明" in result.text and "计算机" in result.text
    assert "科研" not in result.text and "绩点" not in result.text and "3.8" not in result.text
    later = client.post(url, json={"message": "可以写绩点，请重新写。"})
    assert later.status_code == 200 and "3.8" in later.text and "科研" not in later.text


def test_omitting_political_identity_does_not_imply_league_membership(conversation):
    client, _, pid = conversation
    result = client.post(f"/api/projects/{pid}/chat", json={"message": "不要写政治面貌，请帮我写优秀团员申请书。"})
    assert result.status_code == 200 and "优秀团员申请书" in result.text
    assert "思想表现" not in result.text and "政治面貌" not in result.text
    assert "我是一名团员" not in result.text


def test_grades_can_be_omitted_and_selectively_restored_through_api(conversation):
    client, store, pid = conversation
    url = f"/api/projects/{pid}/chat"
    store.add_message(pid, "user", "我叫李明，学计算机专业，绩点3.8，专业排名3/80。我要申请优秀学生。")
    omitted = client.post(url, json={"message": "不要写成绩，请重新写优秀学生申请书。"})
    assert omitted.status_code == 200 and "<WritingBlock" in omitted.text
    assert all(value not in omitted.text for value in ("绩点", "排名", "3.8", "3/80"))
    gpa = client.post(url, json={"message": "可以写绩点，请重新写。"})
    assert gpa.status_code == 200 and "3.8" in gpa.text
    assert "排名" not in gpa.text and "3/80" not in gpa.text
    restored = client.post(url, json={"message": "现在可以写成绩，请重新写。"})
    assert restored.status_code == 200 and "3.8" in restored.text and "3/80" in restored.text
    assert store.get_workbench_credit_balance("local_user")["free_chat_count"] == 3


@pytest.mark.parametrize("message", [
    "帮我写优秀学生申请书但不要写成绩。",
    "不要写学习成绩但是帮我写优秀学生申请书。",
    "帮我写优秀学生申请书，不写学业成绩。",
])
def test_positive_draft_and_grade_omission_in_same_request(conversation, message):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫李明，绩点3.8，专业排名3/80。")
    result = client.post(f"/api/projects/{pid}/chat", json={"message": message})
    assert result.status_code == 200 and "<WritingBlock" in result.text and "李明" in result.text
    assert all(value not in result.text for value in ("绩点", "排名", "3.8", "3/80"))


@pytest.mark.parametrize("message", [
    "请写优秀学生申请书，不要编造成绩。",
    "不要写虚假成绩，请写优秀学生申请书。",
])
def test_prohibiting_fabrication_does_not_omit_real_grades(conversation, message):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫李明，绩点3.8，专业排名3/80。")
    result = client.post(f"/api/projects/{pid}/chat", json={"message": message})
    assert result.status_code == 200 and "<WritingBlock" in result.text
    assert "3.8" in result.text and "3/80" in result.text


@pytest.mark.parametrize(("instructions", "include_gpa"), [
    ("不要写成绩但是可以写绩点", True),
    ("可以写绩点但不要写成绩", False),
])
def test_later_instruction_takes_precedence_in_same_message(conversation, instructions, include_gpa):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫李明，绩点3.8，专业排名3/80。")
    result = client.post(f"/api/projects/{pid}/chat", json={
        "message": f"{instructions}，请写优秀学生申请书。",
    })
    assert result.status_code == 200 and "<WritingBlock" in result.text
    assert ("3.8" in result.text) is include_gpa
    assert "3/80" not in result.text


def test_refusing_the_whole_application_never_triggers_the_local_draft(conversation, monkeypatch):
    client, _, pid = conversation
    calls = []
    def respond(*_args):
        calls.append(True)
        return {"message": {"content": "好的，我们先不写申请书。"}}
    monkeypatch.setattr(app.agent, "_post", respond)
    result = client.post(f"/api/projects/{pid}/chat", json={"message": "不要写优秀学生申请书。"})
    assert result.status_code == 200 and "<WritingBlock" not in result.text
    assert "先不写" in result.text and calls == [True]


def test_award_description_cannot_leak_omitted_grades(conversation, monkeypatch):
    from proposal import personal_materials
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫李明，绩点3.8，专业排名3/80。")
    uploaded = client.post(f"/api/projects/{pid}/documents?kind=source", files={
        "files": ("资料.txt", "姓名：李明\n获奖：数学建模二等奖，绩点3.8，排名3/80".encode(), "text/plain"),
    }).json()["documents"][0]["document"]
    assert client.patch(f"/api/documents/{uploaded['id']}/confirm", json={"confirmed": True}).status_code == 200
    # Simulate a confirmed parser result whose free-text award includes grades.
    monkeypatch.setattr(personal_materials, "confirmed_personal_material_fields", lambda *_args, **_kwargs: {
        "获奖": "数学建模二等奖，绩点3.8，排名3/80",
    })
    baseline = client.post(f"/api/projects/{pid}/chat", json={"message": "请写优秀学生申请书。"})
    assert baseline.status_code == 200 and "数学建模二等奖" in baseline.text
    assert "绩点3.8" in baseline.text and "排名3/80" in baseline.text
    result = client.post(f"/api/projects/{pid}/chat", json={"message": "不要写成绩，请写优秀学生申请书。"})
    assert result.status_code == 200 and "<WritingBlock" in result.text
    assert all(value not in result.text for value in ("绩点", "排名", "3.8", "3/80"))


def test_do_not_write_grades_keeps_other_facts_and_allows_restoration(conversation):
    client, store, pid = conversation
    url = f"/api/projects/{pid}/chat"
    store.add_message(pid, "user", "我叫李明，学计算机专业，绩点3.8，专业排名3/80。我要申请优秀学生。")
    uploaded = client.post(f"/api/projects/{pid}/documents?kind=source", files={
        "files": ("资料.txt", "姓名：李明\n学院：信息学院\n获奖：数学建模二等奖".encode(), "text/plain"),
    }).json()["documents"][0]["document"]
    assert client.patch(f"/api/documents/{uploaded['id']}/confirm", json={"confirmed": True}).status_code == 200
    result = client.post(url, json={"message": "不要写入成绩，请重新写优秀学生申请书。"})
    assert result.status_code == 200 and "<WritingBlock" in result.text
    assert all(value in result.text for value in ("李明", "计算机", "信息学院", "数学建模二等奖"))
    assert all(value not in result.text for value in ("绩点", "排名", "3.8", "3/80"))
    restored = client.post(url, json={"message": "现在可以写成绩，请重新写。"})
    assert restored.status_code == 200 and "3.8" in restored.text and "3/80" in restored.text
    assert store.get_workbench_credit_balance("local_user")["free_chat_count"] == 3


def test_grade_omission_does_not_override_broader_privacy_request(conversation):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫李明，学计算机专业，绩点3.8。我要申请优秀学生。")
    result = client.post(f"/api/projects/{pid}/chat", json={
        "message": "不要写入成绩和我的资料，请写优秀学生申请书。",
    })
    assert result.status_code == 200 and "<WritingBlock" in result.text
    assert all(value not in result.text for value in ("李明", "计算机", "3.8"))


@pytest.mark.parametrize("message", [
    "我叫李明，学计算机专业，绩点3.8，不要写入成绩，请写优秀学生申请书。",
    "我叫李明，学计算机专业但不要写入成绩，请写优秀学生申请书。",
    "我叫李明，学计算机专业不要写入成绩，请写优秀学生申请书。",
])
def test_same_message_grade_omission_keeps_unrelated_student_facts(conversation, message):
    client, _, pid = conversation
    result = client.post(f"/api/projects/{pid}/chat", json={"message": message})
    assert result.status_code == 200 and "<WritingBlock" in result.text
    assert "李明" in result.text and "计算机" in result.text
    assert all(value not in result.text for value in ("绩点", "排名", "3.8"))


def test_same_message_all_personal_data_denial_takes_precedence(conversation):
    client, _, pid = conversation
    result = client.post(f"/api/projects/{pid}/chat", json={"message":
        "我叫李明，学计算机专业，绩点3.8，不要写入成绩和我的资料，请写优秀学生申请书。"})
    assert result.status_code == 200 and "<WritingBlock" in result.text
    assert all(value not in result.text for value in ("李明", "计算机", "3.8"))


def test_same_message_grade_can_be_restored_later(conversation):
    client, _, pid = conversation
    url = f"/api/projects/{pid}/chat"
    first = client.post(url, json={"message":
        "我叫李明，学计算机专业，绩点3.8，不要写入成绩，请写优秀学生申请书。"})
    assert first.status_code == 200 and "3.8" not in first.text
    restored = client.post(url, json={"message": "可以写成绩，请重新写。"})
    assert restored.status_code == 200 and "李明" in restored.text and "3.8" in restored.text


@pytest.mark.parametrize("include_family_income", [False, True])
def test_scholarship_default_grade_privacy_behavior_is_unchanged(include_family_income):
    history = [{"role": "user", "content": "我叫李明，学计算机专业，绩点3.8。"}]
    facts, _ = scholarship_student_facts(history, "不要写入成绩", [], include_family_income=include_family_income)
    assert not any(key in facts for key in ("姓名", "专业", "绩点"))
