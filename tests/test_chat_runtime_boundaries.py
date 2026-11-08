"""User-visible and side-effect boundaries across the refactored chat layers."""
import pytest

import server.app  # Register proposal module path.
from proposal.agent import ModelUnavailable, OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


def test_closing_chat_stream_closes_upstream_and_never_persists_partial_answer(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project = store.create_project(title="连接关闭测试")
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    lifecycle = []

    def upstream(_payload):
        try:
            lifecycle.append("opened")
            yield {"type": "delta", "text": "不完整"}
            yield {"type": "final", "message": {"content": "不完整"}, "usage": None}
        finally:
            lifecycle.append("closed")

    monkeypatch.setattr(agent, "_stream_post", upstream)
    events = agent.chat_stream(project["id"], "请帮我梳理想法")
    assert next(events) == {"type": "delta", "text": "不完整"}
    events.close()
    assert lifecycle == ["opened", "closed"]
    assert [item["role"] for item in store.messages(project["id"])] == ["user"]


def test_no_terminal_model_event_never_saves_partial_reply(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project = store.create_project(title="中断测试")
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    monkeypatch.setattr(agent, "_stream_post", lambda _payload: iter([{"type": "delta", "text": "未完成"}]))
    events = agent.chat_stream(project["id"], "请帮我梳理想法")
    assert next(events)["text"] == "未完成"
    with pytest.raises(ModelUnavailable, match="有效输出"):
        next(events)
    assert [item["role"] for item in store.messages(project["id"])] == ["user"]


def test_buffered_draft_reports_progress_without_leaking_unchecked_text(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project = store.create_project(title="进度测试")
    store.update_project(project["id"], state={"skill_id": "internet-plus", "skill_category": "competition"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    clock = iter([0.0, 1.0, 7.0, 8.0, 14.0])
    monkeypatch.setattr("proposal.chat_runtime.monotonic", lambda: next(clock))
    raw = '<WritingBlock>## 项目简介\n\n市场规模为5000亿元。</WritingBlock>'
    def upstream(_payload):
        for part in ("市场", "规模", "为5000", "亿元"):
            yield {"type": "delta", "text": part}
        yield {"type": "final", "message": {"content": raw}, "usage": None}
    monkeypatch.setattr(agent, "_stream_post", upstream)
    events = list(agent.chat_stream(project["id"], "请帮我写项目简介。"))
    progress = [event for event in events if event["type"] == "status"]
    assert len(progress) == 3  # initial notice, then two throttled updates
    deltas = [event["text"] for event in events if event["type"] == "delta"]
    assert len(deltas) == 1 and deltas[0].startswith("这版含需要核对的项目内容")
    assert events[-1]["type"] == "done" and events[-1]["message"] == deltas[0]
