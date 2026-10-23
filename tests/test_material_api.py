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


def test_pilot_gated_other_types_unchanged(api):
    client,store,p = api
    assert client.get(f"/api/projects/{p['id']}/material").status_code == 200
    store.update_project(p["id"],state={"skill_id":"national-scholarship"})
    assert client.get(f"/api/projects/{p['id']}/material").status_code == 404


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
