import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.agent import OllamaAgent
from proposal.material_jobs import MaterialJobs


@pytest.fixture
def api(monkeypatch, tmp_path):
    import app
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("MATERIAL_WORKER_READY", "true")
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    store = Store(tmp_path)
    tools = ProposalTools(store)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", OllamaAgent(store,tools))
    p = store.create_project(title="大创试点")
    p = store.update_project(p["id"], state={"skill_id":"innovation-research","outline_confirmed":True},
        outline=[{"id":"method","title":"研究方法"}], sections={"method":"原文"})
    with TestClient(app.app) as client:
        yield client,store,p


def test_material_api_supports_catalogue_types_and_rejects_unknown(api):
    client,store,p = api
    assert client.get(f"/api/projects/{p['id']}/material").status_code == 200
    store.update_project(p["id"],state={"skill_id":"national-scholarship"})
    assert client.get(f"/api/projects/{p['id']}/material").status_code == 200
    store.update_project(p["id"],state={"skill_id":"not-a-catalogue-skill"})
    assert client.get(f"/api/projects/{p['id']}/material").status_code == 404


def test_non_innovation_export_job_runs_end_to_end(api, monkeypatch):
    import material_worker
    from docx import Document
    client, store, project = api
    project = store.update_project(project["id"], state={
        "skill_id": "national-scholarship", "outline_confirmed": True,
    })
    response = client.post(f"/api/projects/{project['id']}/material/jobs", json={
        "revision": project["material_revision"], "kind": "export",
        "idempotency_key": "national-export",
    })
    assert response.status_code == 202, response.text
    assert material_worker.run_one(local_store=store)
    job = MaterialJobs(store).call("get", project_id=project["id"], id=response.json()["id"])
    assert job["status"] == "completed", job
    path = store.files_dir / project["id"] / "_material" / job["id"] / "proposal.docx"
    assert "国家奖学金" in "\n".join(p.text for p in Document(path).paragraphs)


def test_cloud_job_snapshots_retrieval_only_with_matching_user_consent(api, monkeypatch):
    import app
    import proposal.material_api as material_api
    client, store, project = api
    saved, queries = [], []

    class FakeQueue:
        cloud = True
        def __init__(self, _store):
            pass
        def find(self, *_args):
            return None
        def submit(self, project_id, kind, target, payload, idempotency):
            saved.append(payload)
            return {"id": payload["job_id"]}

    class FakeRetriever:
        def search(self, project_id, query, top_k=5):
            queries.append((project_id, query, top_k))
            return {"retrieval_mode": "hybrid", "results": [{"text": "已确认资料"}]}

    async def bypass_auth(request, call_next):
        return await call_next(request)

    monkeypatch.setattr(app, "CLOUD_MODE", True)
    monkeypatch.setattr(app, "_require_supabase_session", bypass_auth)
    monkeypatch.setattr(app, "_agent_for_config", lambda *a, **kw: object())
    monkeypatch.setattr(app, "retriever", FakeRetriever())
    monkeypatch.setattr(material_api, "MaterialJobs", FakeQueue)
    monkeypatch.setattr(store, "_identity", lambda: {"user_id": "owner"}, raising=False)
    url = f"/api/projects/{project['id']}/material/jobs"
    body = {"revision": project["material_revision"], "kind": "outline", "idempotency_key": "one",
            "llm_config": {"provider": "ollama"}, "confirm_paid": True}
    assert client.post(url, json=body).status_code == 202
    assert not queries and "private_retrieval" not in saved[-1]
    wrong = {"X-Private-RAG-Consent": "cloudflare-bge-m3-v1", "X-Private-RAG-Project": "a" * 32}
    assert client.post(url, headers=wrong, json=body).status_code == 202
    assert not queries and "private_retrieval" not in saved[-1]
    correct = {**wrong, "X-Private-RAG-Project": project["id"]}
    assert client.post(url, headers=correct, json=body).status_code == 202
    assert queries == [(project["id"], "研究问题 研究内容 方法 创新点", 5)]
    assert saved[-1]["private_retrieval"]["result"]["retrieval_mode"] == "hybrid"


def test_requirements_and_revision_conflict(api):
    client,store,p = api
    body = {"revision":p["material_revision"],"items":[{
        "key":"font","value":"宋体","source_kind":"official","source":"学校通知",
        "scope":"2026 测试大学","confirmed":True,"applicable":True}]}
    url = f"/api/projects/{p['id']}/material/requirements"
    r = client.put(url,json=body)
    assert r.status_code == 200, r.text
    assert r.json()["requirements"]["effective"]["font"]["value"] == "宋体"
    assert client.put(url,json=body).status_code == 409


def test_figure_plan_and_explicit_confirmation(api):
    client,store,p = api
    root = f"/api/projects/{p['id']}/material"
    spec = {"id":"flow","section_id":"method","title":"技术路线","renderer":"svg","nodes":["建模","验证"],"confirmed":False}
    assert client.put(root+"/plans",json={"revision":p["material_revision"],"items":[spec]}).status_code == 200
    p = store.get_project(p["id"])
    request = {"revision":p["material_revision"],"kind":"figure","target":"flow","idempotency_key":"click"}
    assert client.post(root+"/jobs",json=request).status_code == 422
    spec["confirmed"] = True
    assert client.put(root+"/plans",json={"revision":p["material_revision"],"items":[spec]}).status_code == 200
    request["revision"] = store.get_project(p["id"])["material_revision"]
    first = client.post(root+"/jobs",json=request)
    assert first.status_code == 202, first.text
    second = client.post(root+"/jobs",json=request)
    assert first.json()["id"] == second.json()["id"]
    assert "payload" not in first.json()
    other = store.create_project()
    assert client.get(f"/api/projects/{other['id']}/material/jobs/{first.json()['id']}").status_code == 404


def test_text_calls_require_confirmation_and_credentials_not_echoed(api):
    client,store,p = api
    root = f"/api/projects/{p['id']}/material"
    result = client.post(root+"/jobs",json={
        "revision":p["material_revision"],"kind":"section","target":"method",
        "idempotency_key":"text","llm_config":{"provider":"ollama"}})
    assert result.status_code == 422
    assert not MaterialJobs(store).call("list",project_id=p["id"])
    # Invalid model secrets cannot appear in the validation response.
    result = client.post(root+"/jobs",json={
        "revision":p["material_revision"],"kind":"section","target":"method",
        "idempotency_key":"text","confirm_paid":True,
        "llm_config":{"provider":"openai_compatible","base_url":"http://localhost","api_key":"SECRET_MARKER"}})
    assert result.status_code == 422
    assert "SECRET_MARKER" not in result.text


def test_upload_not_silently_confirmed_in_pilot(api):
    client,store,p = api
    result = client.post(f"/api/projects/{p['id']}/documents",files=[
        ("files",("source.txt","预算 20000 元".encode(),"text/plain"))])
    assert result.status_code == 200, result.text
    docs = store.list_documents(p["id"])
    assert not docs[0]["confirmed"]
    client.get(f"/api/projects/{p['id']}")
    assert not store.list_documents(p["id"])[0]["confirmed"]


def test_manual_section_cas(api):
    client,store,p = api
    url = f"/api/projects/{p['id']}/sections/method"
    first = client.put(url,json={"content":"","expected_revision":p["material_revision"]})
    assert first.status_code == 200
    assert client.put(url,json={"content":"覆盖","expected_revision":p["material_revision"]}).status_code == 409
    assert store.get_project(p["id"])["sections"]["method"] == ""


def test_direct_section_generation_reports_atomic_persistence_when_worker_unready(api, monkeypatch):
    import app
    client, store, project = api
    monkeypatch.setenv("MATERIAL_WORKER_READY", "false")
    monkeypatch.setattr(app, "_metered_invoke",
                        lambda *args, **kwargs: {"content": "新的生成草稿"})
    response = client.post(f"/api/projects/{project['id']}/sections/method/generate")
    assert response.status_code == 200
    result = response.json()
    assert result["material_applied"] is True
    assert result["material_revision"] == store.get_project(project["id"])["material_revision"]
    assert store.get_project(project["id"])["sections"]["method"] == "新的生成草稿"
