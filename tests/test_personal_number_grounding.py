"""Do not silently save a personal numerical claim the student never gave."""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from proposal.agent import OllamaAgent
from proposal.personal_claims import unsupported_personal_numbers
from proposal.retrieval import ProjectRetriever
from proposal.skills import registry
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.workflow import AgenticWorkflowEngine


@pytest.mark.parametrize(("content", "issues"), [
    ("我的绩点为3.8，满分为4.0。", ["绩点满分制"]),
    ("我的绩点3.8，采用4.0分制。", ["绩点满分制"]),
    ("我的绩点3.8（满分制为4.0）。", ["绩点满分制"]),
    ("我累计参加志愿服务100小时。", ["志愿服务时长"]),
    ("我的绩点为3.9。", ["绩点"]),
    ("我的绩点4.5，但没有志愿经历。", ["绩点"]),
    ("我没有志愿经历但绩点4.5。", ["绩点"]),
    ("我的绩点3.8，满分4.0，但没有志愿经历。", ["绩点满分制"]),
    ("我的绩点4.5，曾帮助同学。", ["绩点"]),
    ("申请人绩点4.5。", ["绩点"]),
    ("本人绩点4.5，专业【待补充】。", ["绩点"]),
    ("本人绩点4.5，专业【待补充：例如计算机】。", ["绩点"]),
    ("我累计参加志愿服务100小时，专业【待补充】。", ["志愿服务时长"]),
    ("我的绩点【待补充：例如4.5】，专业计算机。", []),
    ("该生累计志愿服务100小时。", ["志愿服务时长"]),
    ("我的绩点是3.8。", []),
    ("【待补充：我的绩点和志愿服务小时数】", []),
    ("评审通知提到志愿服务时长100小时。", []),
])
def test_unprovided_numbers_are_not_supported_by_other_values(content, issues):
    project = {"id": "p", "state": {"confirmed_facts": {}}}
    history = [{"role": "user", "content": "我叫李明，绩点是3.8。"}]
    assert unsupported_personal_numbers(registry.get("national-scholarship"), project, history, [], content) == issues


def test_self_supplied_scale_and_hours_are_accepted():
    project = {"id": "p", "state": {"confirmed_facts": {}}}
    history = [{"role": "user", "content": "我叫李明，绩点3.8/4.0。我志愿服务100小时。"}]
    result = unsupported_personal_numbers(registry.get("major-transfer"), project, history, [],
                                           "我的绩点为3.8，满分4.0。我累计志愿服务100小时。")
    assert result == []


def test_examples_model_messages_and_conflicting_claims_do_not_count_as_student_evidence():
    project = {"id": "p", "state": {"confirmed_facts": {}}}
    history = [{"role": "user", "content": "我叫李明，绩点3.8。"},
               {"role": "user", "content": "例如我志愿服务100小时。"},
               {"role": "assistant", "content": "我的绩点3.8，满分4.0。我志愿服务100小时。"}]
    result = unsupported_personal_numbers(registry.get("grant-application"), project, history, [],
                                           "我的绩点3.8，满分4.0。我志愿服务100小时。")
    assert result == ["绩点满分制", "志愿服务时长"]


@pytest.mark.parametrize("persist", [True, False])
def test_passed_model_review_cannot_overwrite_student_text_with_unprovided_numbers(tmp_path, monkeypatch, persist):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "national-scholarship", "outline_confirmed": True,
                         "confirmed_facts": {"gpa": "3.8"}},
                         outline=[{"id": "study", "title": "学习成绩"}], sections={"study": "学生自己的正文"})
    store.add_message(project_id, "user", "我叫李明，绩点3.8。")
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))

    class ModelSaysPassed:
        content = "我的绩点为3.8，满分4.0；我参加志愿服务100小时。"
        def model_dump(self):
            return {"content": self.content, "status": "passed", "review_card": {"review_status": "completed"}}

    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow", lambda *_a, **_kw: ModelSaysPassed())
    result = agent.generate_section(project_id, "study", persist=persist)
    assert result["review_incomplete"]
    assert result["grounding_issues"] == ["绩点满分制", "志愿服务时长"]
    assert "核对" in result["notice"]
    assert store.get_project(project_id)["sections"]["study"] == "学生自己的正文"
    versions = store.list_section_versions(project_id, "study")
    assert bool(versions) is persist
    if persist:
        assert versions[0]["source"] == "ai_generated_alternative"
        assert "志愿服务100小时" in versions[0]["content"]


def test_async_job_retains_unverified_number_as_alternative(tmp_path):
    import time
    from proposal.jobs import GenerationJobRunner
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, sections={"study": "学生自己的正文"})
    runner = GenerationJobRunner(store, max_workers=1)
    try:
        job = runner.submit_job(project_id, "study", lambda: {
            "content": "我的绩点3.8，满分4.0。", "status": "passed",
            "review_card": {"review_status": "completed"}, "grounding_issues": ["绩点满分制"],
        }, idempotency_key="one", current_section_content="学生自己的正文")
        for _ in range(100):
            result = runner.get_job_status(job["id"])
            if result["status"] in {"completed", "failed"}:
                break
            time.sleep(.02)
        assert result["status"] == "completed"
        assert result["result"]["review_incomplete"]
        assert "个人数字需要你核对" in result["result"]["notice"]
        assert store.get_project(project_id)["sections"]["study"] == "学生自己的正文"
        assert any(v["content"].startswith("我的绩点") for v in store.list_section_versions(project_id, "study"))
    finally:
        runner.executor.shutdown(wait=True)
