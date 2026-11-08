"""Personal rewrites must flag model-added figures before streaming a reply."""
from __future__ import annotations

import pytest

import server.app  # Register the server module path.
from proposal.agent import OllamaAgent
from proposal.chat_drafts import candidates
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture
def conversation(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "national-scholarship"},
                         sections={"study": "学生自己的正文"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    return store, project_id, agent


@pytest.mark.parametrize("stream", [False, True])
def test_rewrite_with_invented_scale_and_hours_is_flagged_and_not_importable(conversation, monkeypatch, stream):
    store, project_id, agent = conversation
    model_reply = ('<WritingBlock variant="document">\n## 学习情况\n'
                   '我的绩点3.8，满分4.0；我累计志愿服务100小时。\n</WritingBlock>')
    store.add_message(project_id, "user", "我叫李明，我的绩点是3.8。")
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: {"message": {"content": model_reply}})
    def reply(_payload):
        yield {"type": "delta", "text": "我的绩点3.8，满分4.0；"}
        yield {"type": "delta", "text": "我累计志愿服务100小时。"}
        yield {"type": "final", "message": {"content": model_reply}, "usage": None}
    monkeypatch.setattr(agent, "_stream_post", reply)
    if stream:
        events = list(agent.chat_stream(project_id, "请润色我的学习经历。"))
        result = events[-1]
        chunks = [event["text"] for event in events if event["type"] == "delta"]
        assert chunks == [result["message"]]
    else:
        result = agent.chat(project_id, "请润色我的学习经历。")
    answer = result["message"]
    assert answer.startswith("这版含需要核对的个人数字")
    assert "绩点满分制" in answer and "志愿服务时长" in answer
    assert "满分4.0" in answer and "100小时" in answer  # Available to edit, not lost.
    assert "WritingBlock" not in answer
    assert candidates(store.get_project(project_id), store.messages(project_id)) == []
    assert store.get_project(project_id)["sections"]["study"] == "学生自己的正文"


def test_model_second_person_claim_about_student_is_checked(conversation, monkeypatch):
    store, project_id, agent = conversation
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: {
        "message": {"content": "你的绩点3.8，满分4.0。"}})
    result = agent.chat(project_id, "我的绩点是3.8，请解释一下我的成绩。")
    assert "绩点满分制" in result["message"]


def test_student_supplied_figures_remain_available_as_a_draft(conversation, monkeypatch):
    store, project_id, agent = conversation
    answer = '<WritingBlock variant="document">\n## 学习情况\n我的绩点3.8，满分4.0。\n</WritingBlock>'
    store.add_message(project_id, "user", "我的绩点是3.8/4.0。")
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: {"message": {"content": answer}})
    result = agent.chat(project_id, "请润色我的学习情况。")
    assert result["message"] == answer
    assert candidates(store.get_project(project_id), store.messages(project_id))[0]["title"] == "学习情况"


def test_general_explanation_continues_to_stream_without_buffering(conversation, monkeypatch):
    _, project_id, agent = conversation
    def reply(_payload):
        yield {"type": "delta", "text": "绩点是"}
        yield {"type": "delta", "text": "一种成绩指标。"}
        yield {"type": "final", "message": {"content": "绩点是一种成绩指标。"}, "usage": None}
    monkeypatch.setattr(agent, "_stream_post", reply)
    events = list(agent.chat_stream(project_id, "什么是绩点？"))
    assert [event["text"] for event in events if event["type"] == "delta"] == ["绩点是", "一种成绩指标。"]


@pytest.mark.parametrize("mixed", [False, True])
def test_other_personal_draft_requests_are_checked_including_mixed_policy(conversation, monkeypatch, mixed):
    store, project_id, agent = conversation
    store.update_project(project_id, state={"skill_id": "university-scholarship"})
    policy = "请以本校通知为准。" if mixed else None
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: policy)
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: {"message": {"content":
        '<WritingBlock variant="document">\n## 校级奖学金申请书\n本人累计志愿服务100小时。\n</WritingBlock>'}})
    request = "请帮我写一份校级奖学金申请书。"
    if mixed:
        request = "这个奖学金申请条件是什么？请帮我写一份校级奖学金申请书。"
    result = agent.chat(project_id, request)
    assert result["message"].startswith("这版含需要核对的个人数字")
    assert "志愿服务时长" in result["message"] and "WritingBlock" not in result["message"]
