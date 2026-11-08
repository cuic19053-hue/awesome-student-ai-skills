"""Natural self-reports must be distinguished from rules and other people."""
import pytest
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.chat_context import current_turn_student_facts, scholarship_placeholder_draft
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.mark.parametrize(("message", "expected"), [
    ("我叫李明，学计算机专业，绩点3.8，专业排名3/80", {
        "姓名": "李明", "专业": "计算机", "绩点": "3.8", "排名": "3/80",
    }),
    ("我的专业是软件工程，我的绩点是3.8/4.0，排名第3名", {
        "专业": "软件工程", "绩点": "3.8/4.0", "排名": "第3名",
    }),
    ("我在信息学院，我学人工智能专业，GPA3.7", {
        "学院": "信息学院", "专业": "人工智能", "绩点": "3.7",
    }),
    ("申报条件是什么？帮我写申请书，我叫李明，绩点3.8", {
        "姓名": "李明", "绩点": "3.8",
    }),
    ("我叫张学友，绩点3.8", {"姓名": "张学友", "绩点": "3.8"}),
])
def test_natural_first_person_self_reports_are_read(message, expected):
    assert current_turn_student_facts(message) == expected


@pytest.mark.parametrize("message", [
    "学校要求绩点3.8，排名3/80。请帮我写申请书。",
    "学校通知：姓名李明，绩点3.8，排名3/80。",
    "我的同学叫李明，绩点3.8，排名3/80。",
    "我叫李明，我朋友叫王五，绩点3.8。",
    "例如我叫李明，学计算机专业，绩点3.8。",
    "他说我叫李明，绩点3.8。",
    "我叫李明，学校规定绩点3.8，排名3/80。",
    "我叫李明，绩点3.8。请不要使用我的资料。",
    "我叫李明我的专业是计算机",
    "我叫李明学计算机专业",
    "我的专业是计算机我的排名是前十",
])
def test_ambiguous_or_nonpersonal_text_is_not_used(message):
    assert current_turn_student_facts(message) == {}


def test_unanchored_or_conflicting_following_fields_stay_empty():
    assert current_turn_student_facts("绩点3.8，排名3/80") == {}
    assert current_turn_student_facts("我叫李明，绩点3.8，GPA4.0") == {"姓名": "李明"}
    assert current_turn_student_facts("我叫李明，我之前在外实习，排名3/80") == {"姓名": "李明"}
    assert current_turn_student_facts("我叫李明。排名3/80") == {"姓名": "李明"}


def test_unsafe_natural_field_cannot_change_markup_or_become_a_fact():
    text = scholarship_placeholder_draft("我叫李明<script>，绩点3.8，排名3/80")
    assert "<script>" not in text
    assert "【姓名待补充】" in text
    assert text.count("<WritingBlock") == text.count("</WritingBlock>") == 1


def test_draft_uses_natural_sentences_and_only_supplied_fields():
    text = scholarship_placeholder_draft("我叫李明，学计算机专业，绩点3.8，专业排名3/80")
    assert "我叫李明，现就读于【学院待补充】，所学专业为计算机。" in text
    assert "我的绩点为3.8，排名为3/80。" in text
    assert "【科研、竞赛或实践经历待补充】" in text


@pytest.mark.parametrize("stream", [False, True])
def test_mixed_chat_uses_natural_self_report(tmp_path, monkeypatch, stream):
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
    monkeypatch.setattr(agent, "_post", lambda *_: pytest.fail("must not call model"))
    monkeypatch.setattr(agent, "_stream_post", lambda *_: pytest.fail("must not call model"))
    response = TestClient(app.app).post(f"/api/projects/{project['id']}/chat", json={
        "message": "申报条件是什么？帮我写申请书，我叫李明，学计算机专业，绩点3.8，专业排名3/80",
        "stream": stream,
    })
    assert response.status_code == 200
    assert "我叫李明" in response.text
    assert "所学专业为计算机" in response.text
    assert "绩点为3.8，排名为3/80" in response.text
    assert "【学院待补充】" in response.text
