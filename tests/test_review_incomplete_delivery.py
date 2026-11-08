"""Incomplete generated-section reviews must not overwrite student text."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.jobs import GenerationJobRunner
from proposal.material_jobs import MaterialJobs
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.workflow import AgenticWorkflowEngine


class IncompleteWorkflow:
    content = "候选正文，检查尚未完成。"

    def model_dump(self):
        return {"content": self.content, "status": "review_failed",
                "review_card": {"review_status": "failed"}}


def revision_interrupted_result():
    return {"content": "第一版仍可编辑的草稿。", "status": "needs_user_attention",
            "revision_incomplete": True, "review_card": {"review_status": "completed"}}


def test_interrupted_revision_is_an_alternative_in_legacy_async_job(tmp_path):
    store = Store(tmp_path)
    pid = store.create_project()["id"]
    store.update_project(pid, sections={"section": "学生原文"})
    runner = GenerationJobRunner(store, max_workers=1)
    try:
        job = runner.submit_job(pid, "section", revision_interrupted_result, current_section_content="学生原文")
        for _ in range(100):
            result = runner.get_job_status(job["id"])
            if result["status"] in {"completed", "failed"}:
                break
            time.sleep(.02)
        assert result["status"] == "completed"
        assert result["result"]["review_incomplete"]
        assert store.get_project(pid)["sections"]["section"] == "学生原文"
        assert any(v["content"] == "第一版仍可编辑的草稿。" for v in store.list_section_versions(pid, "section"))
    finally:
        runner.executor.shutdown(wait=True)


def test_interrupted_revision_material_task_requires_explicit_apply(tmp_path, monkeypatch):
    store = Store(tmp_path)
    pid = store.create_project()["id"]
    project = store.update_project(pid, state={"skill_id": "grant-application", "outline_confirmed": True},
                                   outline=[{"id": "family", "title": "家庭情况"}],
                                   sections={"family": "学生原文"})
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    queue = MaterialJobs(store)
    identifier = "b" * 32
    queue.submit(pid, "section", "family", {"job_id": identifier, "base_revision": project["material_revision"],
                                                "input_snapshot": "snapshot"}, "revision-one")
    job = queue.claim_local()
    queue.worker_local(job, "finish", status="completed", result=revision_interrupted_result())
    with TestClient(app.app) as client:
        url = f"/api/projects/{pid}/material/jobs/{identifier}"
        assert client.get(url).json()["result"]["content"] == "第一版仍可编辑的草稿。"
        assert client.post(url + "/apply").status_code == 409
        assert store.get_project(pid)["sections"]["family"] == "学生原文"
        assert client.post(url + "/apply", json={"use_unreviewed_draft": True}).json()["applied"]
    assert store.get_project(pid)["sections"]["family"] == "第一版仍可编辑的草稿。"


def test_sync_agent_preserves_original_and_retains_incomplete_draft(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "grant-application", "outline_confirmed": True,
                         "confirmed_facts": {"family_income": "2万元"}},
                         outline=[{"id": "family", "title": "家庭情况"}], sections={"family": "学生原文"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    calls = []
    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow",
                        lambda *_args, **_kwargs: calls.append(1) or IncompleteWorkflow())
    result = agent.generate_section(project_id, "family")
    assert calls == [1]
    assert result["review_incomplete"] and result["conflict_status"] == "user_edit_preserved"
    assert store.get_project(project_id)["sections"]["family"] == "学生原文"
    versions = store.list_section_versions(project_id, "family")
    assert any(v["content"] == IncompleteWorkflow.content and v["source"] == "ai_generated_alternative" for v in versions)


def test_deferred_result_does_not_claim_a_version_was_saved(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "grant-application", "outline_confirmed": True,
                         "confirmed_facts": {"family_income": "2万元"}},
                         outline=[{"id": "family", "title": "家庭情况"}], sections={"family": "学生原文"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow", lambda *_args, **_kwargs: IncompleteWorkflow())
    result = agent.generate_section(project_id, "family", persist=False)
    assert result["review_incomplete"] and "已保留" not in result["notice"]
    assert "conflict_status" not in result
    assert store.list_section_versions(project_id, "family") == []
    assert store.get_project(project_id)["sections"]["family"] == "学生原文"


def test_material_sync_endpoint_does_not_apply_incomplete_review(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "grant-application", "outline_confirmed": True},
                         outline=[{"id": "family", "title": "家庭情况"}], sections={"family": "学生原文"})
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    calls = []
    class FakeAgent:
        def generate_section(self, *_args, **_kwargs):
            calls.append(1)
            return IncompleteWorkflow().model_dump()
    monkeypatch.setattr(app, "_metered_invoke", lambda _config, _request, _action, _pid, fn: fn(FakeAgent()))
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{project_id}/sections/family/generate")
    assert response.status_code == 200
    assert response.json()["review_incomplete"]
    assert store.get_project(project_id)["sections"]["family"] == "学生原文"
    assert any(v["content"] == IncompleteWorkflow.content for v in store.list_section_versions(project_id, "family"))
    assert calls == [1]


def test_legacy_async_job_preserves_draft_once_without_applying(tmp_path):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, sections={"family": "学生原文"})
    runner = GenerationJobRunner(store, max_workers=1)
    calls = []
    def generate():
        calls.append(1)
        return IncompleteWorkflow().model_dump()
    job = runner.submit_job(project_id, "family", generate, idempotency_key="same", current_section_content="学生原文")
    for _ in range(100):
        result = runner.get_job_status(job["id"])
        if result["status"] in {"completed", "failed"}:
            break
        time.sleep(.02)
    assert result["status"] == "completed"
    assert result["result"]["review_incomplete"]
    assert store.get_project(project_id)["sections"]["family"] == "学生原文"
    assert any(v["content"] == IncompleteWorkflow.content for v in store.list_section_versions(project_id, "family"))
    assert runner.submit_job(project_id, "family", generate, idempotency_key="same")["id"] == job["id"]
    assert calls == [1]


def test_completed_material_draft_is_viewable_and_can_be_explicitly_applied(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    project = store.update_project(project_id, state={"skill_id": "grant-application", "outline_confirmed": True},
                                   outline=[{"id": "family", "title": "家庭情况"}], sections={"family": "学生原文"})
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    queue = MaterialJobs(store)
    identifier = "a" * 32
    queue.submit(project_id, "section", "family", {
        "job_id": identifier, "base_revision": project["material_revision"], "input_snapshot": "snapshot",
    }, "one")
    job = queue.claim_local()
    queue.worker_local(job, "finish", status="completed", result={
        **IncompleteWorkflow().model_dump(), "review_incomplete": True,
    })
    with TestClient(app.app) as client:
        url = f"/api/projects/{project_id}/material/jobs/{identifier}"
        visible = client.get(url)
        assert visible.status_code == 200
        assert visible.json()["result"]["content"] == IncompleteWorkflow.content
        assert store.get_project(project_id)["sections"]["family"] == "学生原文"
        assert client.post(url + "/apply").status_code == 409  # Old/automatic client.
        assert store.get_project(project_id)["sections"]["family"] == "学生原文"
        applied = client.post(url + "/apply", json={"use_unreviewed_draft": True})
        assert applied.status_code == 200 and applied.json()["applied"]
    assert store.get_project(project_id)["sections"]["family"] == IncompleteWorkflow.content


def test_sync_review_draft_remains_in_response_if_version_write_fails(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "grant-application", "outline_confirmed": True,
                         "confirmed_facts": {"family_income": "2万元"}},
                         outline=[{"id": "family", "title": "家庭情况"}], sections={"family": "学生原文"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    calls = []
    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow",
                        lambda *_args, **_kwargs: calls.append(1) or IncompleteWorkflow())
    monkeypatch.setattr(store, "save_section_version", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("storage")))
    result = agent.generate_section(project_id, "family")
    assert result["result_save_uncertain"] and result["content"] == IncompleteWorkflow.content
    assert "不明" in result["notice"] and calls == [1]
    assert store.get_project(project_id)["sections"]["family"] == "学生原文"


def test_material_sync_returns_draft_if_version_write_fails(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "grant-application", "outline_confirmed": True},
                         outline=[{"id": "family", "title": "家庭情况"}], sections={"family": "学生原文"})
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    calls = []
    class FakeAgent:
        def generate_section(self, *_args, **_kwargs):
            calls.append(1)
            return IncompleteWorkflow().model_dump()
    monkeypatch.setattr(app, "_metered_invoke", lambda _config, _request, _action, _pid, fn: fn(FakeAgent()))
    monkeypatch.setattr(store, "save_section_version", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("storage")))
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{project_id}/sections/family/generate")
    assert response.status_code == 200 and response.json()["result_save_uncertain"]
    assert response.json()["content"] == IncompleteWorkflow.content and calls == [1]
    assert store.get_project(project_id)["sections"]["family"] == "学生原文"


def test_async_review_draft_is_kept_in_job_if_version_write_fails(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, sections={"family": "学生原文"})
    monkeypatch.setattr(store, "save_section_version", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("storage")))
    runner = GenerationJobRunner(store, max_workers=1)
    calls = []
    def generate():
        calls.append(1)
        return IncompleteWorkflow().model_dump()
    try:
        job = runner.submit_job(project_id, "family", generate, idempotency_key="one", current_section_content="学生原文")
        for _ in range(100):
            result = runner.get_job_status(job["id"])
            if result["status"] in {"completed", "failed"}:
                break
            time.sleep(.02)
        assert result["status"] == "completed"
        assert result["result"]["result_save_uncertain"]
        assert result["result"]["content"] == IncompleteWorkflow.content
        assert store.get_project(project_id)["sections"]["family"] == "学生原文"
        assert runner.submit_job(project_id, "family", generate, idempotency_key="one")["id"] == job["id"]
        assert calls == [1]
    finally:
        runner.executor.shutdown(wait=True)
