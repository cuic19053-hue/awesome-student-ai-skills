"""Student template exports report incomplete fields and preserve real facts."""
import io

from docx import Document
from docx.shared import Cm
from fastapi.testclient import TestClient
import pytest

import server.app as app
from proposal.material_export import export_material
from proposal.exporter import _fill_labeled_tables, _replace_tokens, _student_template_project
from proposal.retrieval import ProjectRetriever
from proposal.agent import OllamaAgent
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture
def client_store(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    tools = ProposalTools(store, retriever)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", OllamaAgent(store, tools))
    with TestClient(app.app) as client:
        yield client, store


def test_school_template_fills_confirmed_fields_and_reports_remaining(client_store):
    client, store = client_store
    project_id = client.post("/api/projects", json={"skill_id": "grant-application"}).json()["id"]
    template = Document()
    template.sections[0].page_width = Cm(19)
    template.sections[0].left_margin = Cm(3.2)
    template.add_heading("学校助学金申请表", 0)
    table = template.add_table(rows=4, cols=2)
    for row, label, token in [(0, "姓名", "【姓名】"), (1, "家庭年收入", "【年收入】"), (2, "学号", "【学号】")]:
        table.cell(row, 0).text, table.cell(row, 1).text = label, token
    table.cell(3, 0).text = "联系电话"
    original = io.BytesIO()
    template.save(original)
    uploaded = client.post(f"/api/projects/{project_id}/documents?kind=template", files={
        "files": ("school.docx", original.getvalue(),
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    })
    assert uploaded.status_code == 200
    document_id = uploaded.json()["documents"][0]["document"]["id"]
    state = store.get_project(project_id)["state"]
    state["confirmed_facts"] = {"applicant_name": "李明", "family_income": "年收入 5 万元"}
    store.update_project(project_id, state=state, outline=[{"id": "statement", "title": "申请陈述"}],
                         sections={"statement": "现申请国家助学金。"})
    response = client.post(f"/api/projects/{project_id}/export")
    assert response.status_code == 200
    result = response.json()
    assert result["template_status"] == "needs_review"
    assert result["validation"]["passed"] is False
    assert "联系电话（空白）" in result["template_unfilled_fields"]
    assert any("未填写" in text for text in result["warnings"])
    exported = Document(io.BytesIO(client.get(result["download_url"]).content))
    assert exported.tables[0].cell(0, 1).text == "李明"
    assert exported.tables[0].cell(1, 1).text == "年收入 5 万元"
    assert exported.tables[0].cell(2, 1).text == "【学号】"
    assert exported.sections[0].page_width == template.sections[0].page_width
    assert exported.sections[0].left_margin == template.sections[0].left_margin
    # Work on a copy: the uploaded original is unchanged.
    assert open(store.get_document(document_id)["stored_path"], "rb").read() == original.getvalue()


def test_grant_template_respects_income_omission_until_reenabled(client_store, tmp_path, monkeypatch):
    client, store = client_store
    project_id = client.post("/api/projects", json={"skill_id": "grant-application"}).json()["id"]
    template = Document()
    table = template.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "家庭年收入", "【家庭年收入】"
    original = io.BytesIO()
    template.save(original)
    client.post(f"/api/projects/{project_id}/documents?kind=template", files={
        "files": ("school.docx", original.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    }).raise_for_status()
    state = store.get_project(project_id)["state"]
    state["confirmed_facts"] = {"applicant_name": "王明", "family_income": "2万元"}
    store.update_project(project_id, state=state, outline=[{"id": "letter", "title": "申请书"}],
                         sections={"letter": "尊敬的老师：现申请国家助学金。"})
    store.add_message(project_id, "user", "不要把我家的收入放进申请书。")

    result = client.post(f"/api/projects/{project_id}/export")
    assert result.status_code == 422 and "模板" in result.json()["detail"]
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    folder = tmp_path / "omitted-worker"
    with pytest.raises(ValueError, match="模板"):
        export_material(store, project_id, folder)
    assert store.get_project(project_id)["state"]["confirmed_facts"]["family_income"] == "2万元"

    store.add_message(project_id, "user", "现在可以写家庭年收入。")
    result = client.post(f"/api/projects/{project_id}/export")
    document = Document(io.BytesIO(client.get(result.json()["download_url"]).content))
    assert document.tables[0].cell(0, 1).text == "2万元"
    folder = tmp_path / "allowed-worker"
    export_material(store, project_id, folder)
    assert Document(folder / "proposal.docx").tables[0].cell(0, 1).text == "2万元"


@pytest.mark.parametrize("old_body", ["家庭年收入为2万元。", "家里每年约有20000元。", "【家庭年收入待补充】"])
def test_income_optout_blocks_old_saved_body_without_altering_it(client_store, tmp_path, monkeypatch, old_body):
    client, store = client_store
    project_id = client.post("/api/projects", json={"skill_id": "grant-application"}).json()["id"]
    state = store.get_project(project_id)["state"]
    state["confirmed_facts"] = {"family_income": "2万元"}
    store.update_project(project_id, state=state, outline=[{"id": "letter", "title": "申请书"}],
                         sections={"letter": old_body})
    store.add_message(project_id, "user", "不要把我家的收入放进申请书。")
    result = client.post(f"/api/projects/{project_id}/export")
    assert result.status_code == 422 and "正文" in result.json()["detail"]
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    with pytest.raises(ValueError, match="正文"):
        export_material(store, project_id, tmp_path / "worker")
    assert store.get_project(project_id)["sections"]["letter"] == old_body


def test_income_optout_allows_export_when_saved_text_and_template_are_safe(client_store):
    client, store = client_store
    project_id = client.post("/api/projects", json={"skill_id": "grant-application"}).json()["id"]
    state = store.get_project(project_id)["state"]
    state["confirmed_facts"] = {"family_income": "2万元"}
    store.update_project(project_id, state=state, outline=[{"id": "letter", "title": "申请书"}],
                         sections={"letter": "尊敬的老师，现申请国家助学金。"})
    store.add_message(project_id, "user", "不要把我家的收入放进申请书。")
    template = Document()
    template.add_paragraph("学校助学金申请表")
    source = io.BytesIO()
    template.save(source)
    client.post(f"/api/projects/{project_id}/documents?kind=template", files={
        "files": ("school.docx", source.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    }).raise_for_status()
    assert client.post(f"/api/projects/{project_id}/export").status_code == 200


def test_prior_word_download_obeys_current_income_choice(client_store):
    client, store = client_store
    project_id = client.post("/api/projects", json={"skill_id": "grant-application"}).json()["id"]
    state = store.get_project(project_id)["state"]
    state["confirmed_facts"] = {"family_income": "2万元"}
    store.update_project(project_id, state=state, outline=[{"id": "letter", "title": "申请书"}],
                         sections={"letter": "我的家庭年收入为2万元。"})
    exported = client.post(f"/api/projects/{project_id}/export")
    assert exported.status_code == 200
    download = exported.json()["download_url"]
    assert client.get(download).status_code == 200
    store.add_message(project_id, "user", "不要把我家的收入放进申请书。")
    blocked = client.get(download)
    assert blocked.status_code == 409 and "重新导出" in blocked.json()["detail"]
    # Choosing the new draft changes the saved body, not the earlier file in place.
    store.update_project(project_id, sections={"letter": "尊敬的老师：申请国家助学金。"})
    assert client.get(download).status_code == 409
    fresh = client.post(f"/api/projects/{project_id}/export")
    assert fresh.status_code == 200
    assert client.get(fresh.json()["download_url"]).status_code == 200
    store.add_message(project_id, "user", "现在可以写家庭年收入。")
    store.update_project(project_id, sections={"letter": "我的家庭年收入为2万元。"})
    allowed = client.post(f"/api/projects/{project_id}/export")
    assert allowed.status_code == 200 and client.get(allowed.json()["download_url"]).status_code == 200


def test_worker_export_warns_when_template_is_not_fully_mapped(client_store, tmp_path, monkeypatch):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    client, store = client_store
    project_id = client.post("/api/projects", json={"skill_id": "grant-application"}).json()["id"]
    template = Document()
    template.add_heading("学校表格", 0)
    table = template.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "姓名", "【姓名】"
    data = io.BytesIO()
    template.save(data)
    client.post(f"/api/projects/{project_id}/documents?kind=template", files={
        "files": ("school.docx", data.getvalue(),
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    }).raise_for_status()
    store.update_project(project_id, outline=[{"id": "statement", "title": "申请陈述"}],
                         sections={"statement": "申请助学金。"})
    folder = tmp_path / "render"
    result = export_material(store, project_id, folder)
    assert result["template_status"] == "needs_review"
    assert result["validation"]["passed"] is False
    assert any("未填写" in warning for warning in result["warnings"])
    assert Document(folder / "proposal.docx").tables[0].cell(0, 1).text == "【姓名】"


def test_scholarship_letter_has_no_default_project_cover_or_internal_notice(client_store):
    client, store = client_store
    project_id = client.post("/api/projects/conversation").json()["id"]
    client.post(f"/api/projects/{project_id}/skill", json={"skill_id": "national-scholarship"}).raise_for_status()
    store.update_project(project_id, outline=[{"id": "letter", "title": "国家奖学金申请书"}],
                         sections={"letter": "尊敬的老师：\n我申请国家奖学金。\n【个人经历待补充】"})
    response = client.post(f"/api/projects/{project_id}/export")
    assert response.status_code == 200
    result = response.json()
    assert result["validation"]["passed"] is False
    exported = Document(io.BytesIO(client.get(result["download_url"]).content))
    content = "\n".join(p.text for p in exported.paragraphs)
    assert "国家奖学金申请书" in content
    assert "新对话" not in content
    assert "草稿：提交前" not in content
    assert "我申请国家奖学金" in content


def test_national_scholarship_does_not_insert_family_income_even_when_confirmed():
    template = Document()
    table = template.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "家庭年收入", "【家庭年收入】"
    project = {"state": {"skill_id": "national-scholarship", "confirmed_facts": {"family_income": "5万元"}},
               "sections": {}, "outline": [], "_documents": []}
    _replace_tokens(template, project)
    _fill_labeled_tables(template, project)
    assert table.cell(0, 1).text == "【家庭年收入】"


def test_ambiguous_repeated_name_and_existing_template_values_are_not_overwritten():
    template = Document()
    table = template.add_table(rows=3, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "姓名", "【姓名】"
    table.cell(1, 0).text, table.cell(1, 1).text = "姓名", "【姓名】"
    table.cell(2, 0).text, table.cell(2, 1).text = "家庭年收入", "【不适用】"
    project = {"state": {"skill_id": "grant-application", "confirmed_facts": {
        "applicant_name": "李明", "family_income": "5万元"}},
        "sections": {}, "outline": [], "_documents": []}
    _replace_tokens(template, project)
    _fill_labeled_tables(template, project)
    assert table.cell(0, 1).text == table.cell(1, 1).text == "【姓名】"
    assert table.cell(2, 1).text == "【不适用】"


def test_personal_placeholder_split_across_word_runs_is_filled_once():
    template = Document()
    table = template.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "姓名"
    paragraph = table.cell(0, 1).paragraphs[0]
    paragraph.add_run("【姓")
    paragraph.add_run("名】")
    project = {"state": {"skill_id": "grant-application", "confirmed_facts": {"applicant_name": "李明"}},
               "sections": {}, "outline": [], "_documents": []}
    assert _replace_tokens(template, project) == 1
    _fill_labeled_tables(template, project)
    assert table.cell(0, 1).text == "李明"


def test_unrelated_project_does_not_map_generic_person_name_to_template():
    template = Document()
    table = template.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "姓名", "【姓名】"
    project = {"state": {"skill_id": "innovation-research", "confirmed_facts": {"applicant_name": "李明"}},
               "sections": {}, "outline": [], "_documents": []}
    _replace_tokens(template, project)
    _fill_labeled_tables(template, project)
    assert table.cell(0, 1).text == "【姓名】"


def test_national_chat_and_confirmed_document_fill_template_without_persisting_facts(client_store, monkeypatch, tmp_path):
    client, store = client_store
    project_id = client.post("/api/projects/conversation").json()["id"]
    client.post(f"/api/projects/{project_id}/skill", json={"skill_id": "national-scholarship"}).raise_for_status()
    material = client.post(f"/api/projects/{project_id}/documents?kind=source", files={
        "files": ("个人资料.txt", "姓名：李明\n学院：信息学院\n绩点：3.8".encode(), "text/plain"),
    }).json()["documents"][0]["document"]
    client.patch(f"/api/documents/{material['id']}/confirm", json={"confirmed": True}).raise_for_status()
    reply = client.post(f"/api/projects/{project_id}/chat", json={
        "message": "我叫李明，请帮我写国家奖学金申请书。",
    })
    assert reply.status_code == 200 and "信息学院" in reply.json()["message"]
    preview = client.get(f"/api/projects/{project_id}/chat-drafts").json()
    client.post(f"/api/projects/{project_id}/chat-drafts/confirm", json={
        "snapshot": preview["snapshot"], "items": [{"id": preview["items"][0]["id"]}],
    }).raise_for_status()
    template = Document()
    table = template.add_table(rows=3, cols=2)
    for index, label in enumerate(("姓名", "学院", "绩点")):
        table.cell(index, 0).text, table.cell(index, 1).text = label, f"【{label}】"
    source = io.BytesIO()
    template.save(source)
    client.post(f"/api/projects/{project_id}/documents?kind=template", files={
        "files": ("school.docx", source.getvalue(),
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    }).raise_for_status()
    assert not store.get_project(project_id)["state"].get("confirmed_facts")
    result = client.post(f"/api/projects/{project_id}/export")
    assert result.status_code == 200
    output = Document(io.BytesIO(client.get(result.json()["download_url"]).content))
    assert [output.tables[0].cell(i, 1).text for i in range(3)] == ["李明", "信息学院", "3.8"]
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    worker_folder = tmp_path / "worker-export"
    export_material(store, project_id, worker_folder)
    worker_output = Document(worker_folder / "proposal.docx")
    assert [worker_output.tables[0].cell(i, 1).text for i in range(3)] == ["李明", "信息学院", "3.8"]
    assert not store.get_project(project_id)["state"].get("confirmed_facts")


def test_chat_and_confirmed_field_disagreement_leaves_template_field_untouched(client_store):
    client, store = client_store
    project_id = client.post("/api/projects", json={"skill_id": "national-scholarship"}).json()["id"]
    store.add_message(project_id, "user", "我叫李明，绩点3.8。")
    state = store.get_project(project_id)["state"]
    state["confirmed_facts"] = {"applicant_name": "李明", "gpa": "4.0"}
    store.update_project(project_id, state=state, outline=[{"id": "letter", "title": "申请书"}],
                         sections={"letter": "尊敬的老师：我申请国家奖学金。"})
    template = Document()
    table = template.add_table(rows=2, cols=2)
    for index, label in enumerate(("姓名", "绩点")):
        table.cell(index, 0).text, table.cell(index, 1).text = label, f"【{label}】"
    source = io.BytesIO()
    template.save(source)
    client.post(f"/api/projects/{project_id}/documents?kind=template", files={
        "files": ("school.docx", source.getvalue(),
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    }).raise_for_status()
    result = client.post(f"/api/projects/{project_id}/export")
    assert result.status_code == 200
    output = Document(io.BytesIO(client.get(result.json()["download_url"]).content))
    assert output.tables[0].cell(0, 1).text == "李明"
    assert output.tables[0].cell(1, 1).text == "【绩点】"
    assert result.json()["template_status"] == "needs_review"
    assert any("不同说法" in warning for warning in result.json()["warnings"])
    assert store.get_project(project_id)["state"]["confirmed_facts"]["gpa"] == "4.0"


def test_student_request_not_to_use_information_leaves_personal_template_fields_blank(client_store):
    client, store = client_store
    project_id = client.post("/api/projects", json={"skill_id": "national-scholarship"}).json()["id"]
    store.add_message(project_id, "user", "我叫李明，绩点3.8。")
    store.add_message(project_id, "user", "请不要使用我的资料。")
    state = store.get_project(project_id)["state"]
    state["confirmed_facts"] = {"applicant_name": "李明", "gpa": "3.8"}
    store.update_project(project_id, state=state, outline=[{"id": "letter", "title": "申请书"}],
                         sections={"letter": "尊敬的老师：我申请国家奖学金。"})
    template = Document()
    table = template.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "姓名", "【姓名】"
    data = io.BytesIO()
    template.save(data)
    client.post(f"/api/projects/{project_id}/documents?kind=template", files={
        "files": ("school.docx", data.getvalue(),
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    }).raise_for_status()
    result = client.post(f"/api/projects/{project_id}/export")
    output = Document(io.BytesIO(client.get(result.json()["download_url"]).content))
    assert output.tables[0].cell(0, 1).text == "【姓名】"


def test_name_conflict_never_combines_different_students_profile_fields(client_store):
    _, store = client_store
    project = store.create_project()
    store.add_message(project["id"], "user", "我叫李明，绩点3.8。")
    project = store.update_project(project["id"], state={"skill_id": "national-scholarship",
        "confirmed_facts": {"applicant_name": "王同学", "gpa": "4.0"}})
    export_copy = _student_template_project(store, project, [])
    assert "applicant_name" not in export_copy["state"]["confirmed_facts"]
    assert "gpa" not in export_copy["state"]["confirmed_facts"]
    assert store.get_project(project["id"])["state"]["confirmed_facts"]["applicant_name"] == "王同学"
