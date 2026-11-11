"""A downloaded Word file must still represent the current saved inputs."""
import io

from docx import Document
from fastapi.testclient import TestClient
import pytest

import server.app as app
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    tools = ProposalTools(store, retriever)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", OllamaAgent(store, tools))
    project = store.create_project(title="版本核查")
    project_id = project["id"]
    store.update_project(project_id, state={"skill_id": "national-scholarship", "skill_name": "国家奖学金"},
                         outline=[{"id": "letter", "title": "申请书"}],
                         sections={"letter": "我的专业排名为第三名。"})
    with TestClient(app.app) as client:
        yield client, store, project_id


def test_saved_body_change_expires_old_word_and_reexport_contains_new_body(isolated):
    client, store, project_id = isolated
    url = f"/api/projects/{project_id}"
    assert client.post(url + "/export").status_code == 200
    assert client.get(url + "/download").status_code == 200
    client.put(url + "/sections/letter", json={"content": "我的专业排名已更正为第五名。"}).raise_for_status()
    old = client.get(url + "/download")
    assert old.status_code == 409 and "重新导出" in old.json()["detail"]
    client.post(url + "/export").raise_for_status()
    word = Document(io.BytesIO(client.get(url + "/download").content))
    text = "\n".join(p.text for p in word.paragraphs)
    assert "第五名" in text and "第三名" not in text


def test_concurrent_edit_during_export_is_not_published_as_current(isolated, monkeypatch):
    client, store, project_id = isolated
    export = app.export_project

    def edit_during_export(*args):
        result = export(*args)
        store.update_project(project_id, sections={"letter": "生成文件期间保存的新正文。"})
        return result

    monkeypatch.setattr(app, "export_project", edit_during_export)
    result = client.post(f"/api/projects/{project_id}/export")
    assert result.status_code == 409
    assert "导出期间" in result.json()["detail"]
    assert not store.get_project(project_id)["state"].get("exported_docx_fingerprint")


@pytest.mark.parametrize("legacy_revision", [False, True])
def test_edit_then_undo_during_render_cannot_publish_the_intermediate_body(isolated, monkeypatch, legacy_revision):
    client, store, project_id = isolated
    export = app.export_project
    if legacy_revision:
        # Older cloud writes may not advance material_revision; the actual
        # renderer snapshot must still detect an A -> B -> A change.
        get_project = store.get_project
        monkeypatch.setattr(store, "get_project", lambda pid: {**get_project(pid), "material_revision": 0})

    def edit_and_undo(st, pid, path):
        st.update_project(pid, sections={"letter": "这份中间版本不应该作为当前文件：排名第一名。"})
        result = export(st, pid, path)
        st.update_project(pid, sections={"letter": "我的专业排名为第三名。"})
        return result

    monkeypatch.setattr(app, "export_project", edit_and_undo)
    response = client.post(f"/api/projects/{project_id}/export")
    assert response.status_code == 409
    assert "导出期间" in response.json()["detail"]
    assert not store.get_project(project_id)["state"].get("exported_docx_fingerprint")


def test_edit_at_publication_keeps_student_text_and_rejects_export(isolated, monkeypatch):
    client, store, project_id = isolated
    update = store.update_project

    def edit_before_publish(pid, **fields):
        if "exported_docx_fingerprint" in fields.get("state", {}):
            update(pid, sections={"letter": "保存版本元数据前刚提交的新正文。"})
        return update(pid, **fields)

    monkeypatch.setattr(store, "update_project", edit_before_publish)
    response = client.post(f"/api/projects/{project_id}/export")
    assert response.status_code == 409
    current = store.get_project(project_id)
    assert "刚提交" in current["sections"]["letter"]
    assert not current["state"].get("exported_docx_fingerprint")


def test_export_metadata_is_not_bound_only_to_project_revision(isolated):
    client, store, project_id = isolated
    url = f"/api/projects/{project_id}"
    client.post(url + "/export").raise_for_status()
    state = dict(store.get_project(project_id)["state"])
    state["last_model_config"] = {"model": "another-model"}
    store.update_project(project_id, state=state)
    assert client.get(url + "/download").status_code == 200
    # Student instructions affect facts/template filling without a project patch.
    store.add_message(project_id, "user", "请将申请学校更正为另一所学校。")
    assert client.get(url + "/download").status_code == 409


def test_file_replacement_cannot_serve_bytes_from_another_export(isolated):
    client, store, project_id = isolated
    url = f"/api/projects/{project_id}"
    client.post(url + "/export").raise_for_status()
    name = store.get_project(project_id)["state"]["exported_docx_local_name"]
    replacement = Document()
    replacement.add_paragraph("另一次请求产生的旧稿。")
    replacement.save(store.files_dir / project_id / name)
    assert client.get(url + "/download").status_code == 409


def test_reexport_removes_only_the_replaced_generated_local_file(isolated):
    client, store, project_id = isolated
    url = f"/api/projects/{project_id}"
    client.post(url + "/export").raise_for_status()
    old_name = store.get_project(project_id)["state"]["exported_docx_local_name"]
    original = store.files_dir / project_id / "学生原稿.docx"
    original.write_bytes(b"original attachment")
    client.post(url + "/export").raise_for_status()
    assert not (store.files_dir / project_id / old_name).exists()
    assert original.read_bytes() == b"original attachment"
    assert client.get(url + "/download").status_code == 200


def test_cloud_read_rechecks_edits_that_arrive_during_storage_fetch(isolated, monkeypatch):
    client, store, project_id = isolated
    url = f"/api/projects/{project_id}"
    saved = {}
    monkeypatch.setattr(store, "persist_generated_file", lambda project_id, name, path, kind:
                        saved.setdefault("path", path) and "owner/project/generated.docx", raising=False)
    client.post(url + "/export").raise_for_status()

    def read_file(_):
        content = saved["path"].read_bytes()
        store.update_project(project_id, sections={"letter": "存储读取期间已经更正的正文。"})
        return content

    monkeypatch.setattr(store, "read_generated_file", read_file, raising=False)
    assert client.get(url + "/download").status_code == 409


def test_document_confirmation_change_expires_generated_word(isolated):
    client, store, project_id = isolated
    upload = client.post(f"/api/projects/{project_id}/documents", files={
        "files": ("个人资料.txt", "我叫李明，专业为计算机科学。".encode(), "text/plain"),
    }).json()["documents"][0]["document"]
    client.post(f"/api/projects/{project_id}/export").raise_for_status()
    client.patch(f"/api/documents/{upload['id']}/confirm", json={"confirmed": True}).raise_for_status()
    assert client.get(f"/api/projects/{project_id}/download").status_code == 409
