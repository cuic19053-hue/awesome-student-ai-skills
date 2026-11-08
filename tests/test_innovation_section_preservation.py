"""A missing-info checklist must not erase a student's project chapter."""
import time

import pytest
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.jobs import GenerationJobRunner
from proposal.material_jobs import MaterialJobs
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture
def project_env(tmp_path, monkeypatch):
    store = Store(tmp_path)
    pid = store.create_project(title="校园垃圾分类助手")["id"]
    project = store.update_project(pid,
        state={"skill_id": "innovation-research", "outline_confirmed": True},
        outline=[{"id": "background", "title": "项目背景与研究问题"}],
        sections={"background": "学生已写：校园分类指引需要进一步调研。"})
    tools = ProposalTools(store, ProjectRetriever(store))
    monkeypatch.setattr(tools, "search_project_materials", lambda *_a, **_kw: {"results": [], "retrieval_mode": "empty"})
    agent = OllamaAgent(store, tools)
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: pytest.fail("缺少事实时不得调用模型"))
    return store, pid, project, agent


@pytest.mark.parametrize("material_mode", [False, True])
def test_sync_generation_keeps_existing_chapter(project_env, monkeypatch, material_mode):
    store, pid, _, agent = project_env
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", str(material_mode).lower())
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "_metered_invoke", lambda _cfg, _req, _act, _pid, fn: fn(agent))
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{pid}/sections/background/generate")
    assert response.status_code == 200
    result = response.json()
    assert result["requires_student_input"] is True
    assert result["missing_fields"] == ["problem"]
    assert result["content"] == "学生已写：校园分类指引需要进一步调研。"
    assert store.get_project(pid)["sections"]["background"] == result["content"]


def test_empty_chapter_offers_a_missing_information_checklist(project_env):
    store, pid, _, agent = project_env
    store.update_project(pid, sections={"background": ""})
    result = agent.generate_section(pid, "background")
    assert result["requires_student_input"]
    assert "具体问题和发生场景" in result["content"]
    assert store.get_project(pid)["sections"]["background"] == result["content"]


def test_background_job_preserves_existing_chapter(project_env):
    store, pid, _, agent = project_env
    before = store.get_project(pid)["sections"]["background"]
    runner = GenerationJobRunner(store, max_workers=1)
    job = runner.submit_job(pid, "background", lambda: agent.generate_section(pid, "background", persist=False),
                            current_section_content=before)
    try:
        for _ in range(100):
            current = runner.get_job_status(job["id"])
            if current["status"] in {"completed", "failed"}:
                break
            time.sleep(.02)
        assert current["status"] == "completed", current
        assert current["result"]["requires_student_input"]
        assert store.get_project(pid)["sections"]["background"] == before
    finally:
        runner.executor.shutdown(wait=True)


def test_material_worker_cannot_replace_with_checklist(project_env, monkeypatch):
    store, pid, project, agent = project_env
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    queue = MaterialJobs(store)
    identifier = "c" * 32
    queue.submit(pid, "section", "background", {"job_id": identifier,
        "base_revision": project["material_revision"], "input_snapshot": "snapshot"}, "innovation-one")
    job = queue.claim_local()
    result = agent.generate_section(pid, "background", persist=False)
    queue.worker_local(job, "finish", status="completed", result=result)
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{pid}/material/jobs/{identifier}/apply")
    assert response.status_code == 200
    assert response.json()["requires_student_input"]
    assert store.get_project(pid)["sections"]["background"] == "学生已写：校园分类指引需要进一步调研。"
