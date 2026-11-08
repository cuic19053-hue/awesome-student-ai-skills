"""Income preferences must also protect the need-based merit scholarship."""
import io

from docx import Document
from fastapi.testclient import TestClient
import pytest

import server.app as app
from proposal.agent import OllamaAgent
from proposal.material_export import export_material
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.workflow import AgenticWorkflowEngine


@pytest.fixture
def client_store(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    tools = ProposalTools(store, retriever)
    for name, value in {"store": store, "retriever": retriever, "tools": tools,
                        "agent": OllamaAgent(store, tools), "CLOUD_MODE": False}.items():
        monkeypatch.setattr(app, name, value)
    with TestClient(app.app) as client:
        pid = client.post("/api/projects", json={"skill_id": "motivation-scholarship"}).json()["id"]
        state = store.get_project(pid)["state"]
        state.update({"outline_confirmed": True, "confirmed_facts": {"family_income": "2万元", "name": "王明"}})
        store.update_project(pid, state=state, outline=[{"id": "family", "title": "家庭情况"}],
                             sections={"family": "我的家庭年收入为2万元。"})
        yield client, store, pid


def test_existing_and_downloaded_word_respect_new_optout(client_store, tmp_path, monkeypatch):
    client, store, pid = client_store
    exported = client.post(f"/api/projects/{pid}/export")
    assert exported.status_code == 200, exported.text
    old_url = exported.json()["download_url"]
    assert client.get(old_url).status_code == 200
    store.add_message(pid, "user", "不要把我家的收入放进申请书。")
    assert client.get(old_url).status_code == 409
    blocked = client.post(f"/api/projects/{pid}/export")
    assert blocked.status_code == 422 and "收入" in blocked.text
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    with pytest.raises(ValueError, match="收入"):
        export_material(store, pid, tmp_path / "worker")
    assert store.get_project(pid)["sections"]["family"] == "我的家庭年收入为2万元。"
    store.update_project(pid, sections={"family": "尊敬的老师：现申请国家励志奖学金。"})
    safe = client.post(f"/api/projects/{pid}/export")
    assert safe.status_code == 200
    word = Document(io.BytesIO(client.get(safe.json()["download_url"]).content))
    assert "2万元" not in "\n".join(paragraph.text for paragraph in word.paragraphs)
    store.add_message(pid, "user", "现在可以写家庭年收入。")
    store.update_project(pid, sections={"family": "我的家庭年收入为2万元。"})
    assert client.post(f"/api/projects/{pid}/export").status_code == 200


def test_income_optout_blocks_family_template(client_store):
    client, store, pid = client_store
    store.update_project(pid, sections={"family": "现申请国家励志奖学金。"})
    template = Document()
    table = template.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "家庭年收入", "【家庭年收入】"
    data = io.BytesIO()
    template.save(data)
    upload = client.post(f"/api/projects/{pid}/documents?kind=template", files={
        "files": ("学校模板.docx", data.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    })
    assert upload.status_code == 200
    store.add_message(pid, "user", "不要写家庭收入。")
    blocked = client.post(f"/api/projects/{pid}/export")
    assert blocked.status_code == 422 and "模板" in blocked.text
    assert store.get_project(pid)["state"]["confirmed_facts"]["family_income"] == "2万元"


def test_income_optout_prevents_model_sending_stored_fact(client_store, monkeypatch):
    _, store, pid = client_store
    store.add_message(pid, "user", "不要写家庭收入。")
    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow", lambda *_a, **_k: pytest.fail("must respect opt-out"))
    result = app.agent.generate_section(pid, "family")
    assert result["requires_student_input"] and "不写家庭收入" in result["notice"]
    assert result["content"] == "我的家庭年收入为2万元。"


def test_worker_job_started_before_optout_cannot_leak_old_word(client_store, monkeypatch):
    import material_worker
    client, store, pid = client_store
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("MATERIAL_WORKER_READY", "true")
    project = store.get_project(pid)
    url = f"/api/projects/{pid}/material/jobs"
    response = client.post(url, json={"revision": project["material_revision"], "kind": "export",
                                     "idempotency_key": "motivation-before-optout"})
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    store.add_message(pid, "user", "不要把我家的收入写进申请书。")
    assert material_worker.run_one(local_store=store)
    blocked = client.get(f"{url}/{job_id}/files/proposal.docx")
    assert blocked.status_code == 409 and "重新导出" in blocked.text
    store.add_message(pid, "user", "现在可以写家庭年收入。")
    assert client.get(f"{url}/{job_id}/files/proposal.docx").status_code == 200


def test_worker_rejects_old_income_after_optout_but_allows_safe_draft(client_store, monkeypatch):
    import material_worker
    client, store, pid = client_store
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("MATERIAL_WORKER_READY", "true")
    store.add_message(pid, "user", "不要写家庭收入。")
    url = f"/api/projects/{pid}/material/jobs"
    project = store.get_project(pid)
    response = client.post(url, json={"revision": project["material_revision"], "kind": "export",
                                     "idempotency_key": "motivation-unsafe"})
    assert response.status_code == 422 and "收入" in response.text
    project = store.update_project(pid, sections={"family": "尊敬的老师：现申请国家励志奖学金。"})
    accepted = client.post(url, json={"revision": project["material_revision"], "kind": "export",
                                     "idempotency_key": "motivation-safe"})
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["id"]
    assert material_worker.run_one(local_store=store)
    assert client.get(f"{url}/{job_id}/files/proposal.docx").status_code == 200
