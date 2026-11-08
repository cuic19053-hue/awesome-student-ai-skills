"""A later revision failure must not lose the earlier paid-for draft."""
import json

import pytest

from server.proposal.agent import ModelUnavailable, OllamaAgent
from server.proposal.storage import Store
from server.proposal.tools import ProposalTools
from server.proposal.workflow import AgenticWorkflowEngine, REVIEW_WEIGHTS


def failed_review(*, actions=None):
    return json.dumps({"overall_score": 70.0, "passed": False,
        "dimensions": [{"name": name, "score": 70.0, "weight": weight, "comment": "可改进"}
                       for name, weight in REVIEW_WEIGHTS.items()],
        "strengths": [], "weaknesses": ["表达需要改进"],
        "actionable_revisions": ["优化文字结构"], "user_action_required": actions or [], "blocking_issues": []})


def test_student_inputs_stop_rewriting_and_preserve_draft():
    calls = []
    def draft(_messages, _options):
        calls.append("draft")
        return "初稿：拟进行调研。【待补充：调研地点】"
    def review(_messages, _options):
        calls.append("review")
        return failed_review(actions=["提供调研地点"])
    result = AgenticWorkflowEngine(draft, review, max_retries=2).run_workflow(
        project_context={}, section_id="plan", section_title="调研计划", skill_guidance="", evidence_results=[])
    assert calls == ["draft", "review"]
    assert result.iterations == 1 and "初稿" in result.content
    assert not result.passed and "调研地点" in result.missing_facts[0]


@pytest.mark.parametrize("persist", [True, False])
def test_revision_timeout_retains_draft_and_preserves_existing_section(tmp_path, monkeypatch, persist):
    store = Store(tmp_path)
    pid = store.create_project("学生项目")["id"]
    store.update_project(pid, state={"skill_id": "internet-plus", "outline_confirmed": True},
                         outline=[{"id": "market", "title": "市场分析"}],
                         sections={"market": "学生之前写的正文"})
    tools = ProposalTools(store)
    monkeypatch.setattr(tools, "search_project_materials", lambda *_a, **_k: {"results": []})
    monkeypatch.setattr(tools, "search_public_knowledge", lambda *_a, **_k: {"results": []})
    agent = OllamaAgent(store, tools)
    calls = []
    def post(_path, _payload, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            return {"message": {"content": "已完成的第一版草稿。"}}
        if len(calls) == 2:
            return {"message": {"content": failed_review()}}
        raise ModelUnavailable("secret upstream detail")
    monkeypatch.setattr(agent, "_post", post)
    result = agent.generate_section(pid, "market", persist=persist)
    assert len(calls) == 3
    assert result["content"] == "已完成的第一版草稿。"
    assert result["revision_incomplete"] and result["review_incomplete"] and not result["passed"]
    assert "修改未完成" in result["notice"] and "secret" not in str(result)
    assert store.get_project(pid)["sections"]["market"] == "学生之前写的正文"
    versions = store.list_section_versions(pid, "market")
    assert bool(versions) is persist
    if persist:
        assert versions[0]["content"] == "已完成的第一版草稿。"


def test_initial_draft_failure_does_not_claim_result():
    def fail(_messages, _options):
        raise ModelUnavailable("模型不可用")
    with pytest.raises(ModelUnavailable):
        AgenticWorkflowEngine(fail).run_workflow(
            project_context={}, section_id="plan", section_title="计划", skill_guidance="", evidence_results=[])
