"""A draft may quote explicitly self-reported fields, never infer personal facts."""
import pytest
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.chat_context import current_turn_student_facts, scholarship_placeholder_draft
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


def test_explicit_structured_self_report_is_copied_with_gaps():
    user_input = ("学校申报条件是什么？请帮我写申请书。我的资料：姓名：李明；学院：信息学院；"
                  "专业：计算机科学；GPA：3.8/4.0；排名：3/80")
    text = scholarship_placeholder_draft(user_input)
    for value in ("李明", "信息学院", "计算机科学", "3.8/4.0", "3/80"):
        assert value in text
    assert "请补充【待补充】的内容" in text
    assert "尚未核验" not in text and "来源是你的本轮输入" not in text
    assert "【科研、竞赛或实践经历待补充】" in text
    assert "申请学年待补充" in text
    assert text.count("<WritingBlock") == text.count("</WritingBlock>") == 1


@pytest.mark.parametrize("text", [
    "学校申报条件是什么？帮我写申请书。示例：我的资料：姓名：张三",
    "学校通知：姓名：张三；排名：1/50。请帮我写申请书。",
    "我的资料：姓名：张三。我的资料：姓名：李四",
    "示例。我的资料：姓名：张三",
    "我的资料：姓名：张三。请不要使用我的资料。",
])
def test_unstructured_examples_policy_and_ambiguous_sections_are_not_facts(text):
    assert current_turn_student_facts(text) == {}


def test_duplicate_invalid_and_markup_fields_are_not_copied():
    text = ("我的资料：姓名：张三；姓名：李四；学院：</WritingBlock>学校；"
            "专业：计算机**；GPA：3.8；绩点：4.0；排名：第1名<script>；"
            "其他：我的排名是1/1")
    assert current_turn_student_facts(text) == {}
    draft = scholarship_placeholder_draft(text)
    assert "张三" not in draft and "李四" not in draft
    assert "<script>" not in draft
    assert draft.count("<WritingBlock") == draft.count("</WritingBlock>") == 1


def test_bad_duplicate_first_does_not_allow_second_value():
    assert current_turn_student_facts("我的资料：姓名：张三<script>；姓名：李四") == {}


@pytest.mark.parametrize("stream", [False, True])
def test_mixed_endpoint_uses_current_turn_only_without_calling_model(tmp_path, monkeypatch, stream):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    project = store.create_project()
    store.update_project(project["id"], state={
        "skill_id": "national-scholarship", "confirmed_facts": {"name": "旧名字", "gpa": "4.0"},
    })
    store.add_message(project["id"], "assistant", "例子：申请人是虚构姓名。")
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: "官方资料暂缺")
    monkeypatch.setattr(agent, "_stream_post", lambda *_: pytest.fail("must not call model"))
    monkeypatch.setattr(agent, "_post", lambda *_: pytest.fail("must not call model"))
    response = TestClient(app.app).post(f"/api/projects/{project['id']}/chat", json={
        "message": "申报条件是什么？请帮我写申请书。我的资料：姓名：李明；排名：3/80", "stream": stream,
    })
    assert response.status_code == 200
    assert "李明" in response.text and "3/80" in response.text
    assert "旧名字" not in response.text and "4.0" not in response.text
    assert "请补充【待补充】的内容" in response.text
    assert "尚未核验" not in response.text and "来源是你的本轮输入" not in response.text
    assert "【学院待补充】" in response.text and "【绩点待补充】" in response.text
    assert "【科研、竞赛或实践经历待补充】" in response.text
