"""Broken optional assets must not silently discard a student's Word draft."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.material_export import export_material
from proposal.storage import Store
from proposal.tools import ProposalTools


def document_text(document):
    return "\n".join(p.text for p in document.paragraphs)


@pytest.mark.parametrize("condition", ["missing", "corrupt"])
def test_unavailable_template_preserves_sections_in_both_export_paths(tmp_path, monkeypatch, condition):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    store = Store(tmp_path / "data")
    pid = store.create_project("垃圾分类研究")["id"]
    path = tmp_path / "school.docx"
    if condition == "corrupt":
        path.write_bytes(b"not a docx archive")
    uploaded = store.add_document(pid, "school.docx", str(path), "template", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    state = {"skill_id": "social-survey", "outline_confirmed": True}
    store.update_project(pid, state=state, template_document_id=uploaded["id"],
                         outline=[{"id": "background", "title": "调研背景"}],
                         sections={"background": "这是学生已保存的社区垃圾分类调研正文。"})
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", ProposalTools(store))
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{pid}/export")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["template_status"] == "needs_review"
        assert not result["used_original_template"] and not result["validation"]["passed"]
        assert any("模板" in warning and "通用" in warning for warning in result["warnings"])
        assert "学生已保存的社区垃圾分类调研正文" in document_text(Document(io.BytesIO(client.get(result["download_url"]).content)))
    output = tmp_path / "worker"
    report = export_material(store, pid, output)
    assert report["template_status"] == "needs_review" and not report["validation"]["passed"]
    assert any("模板" in warning and "通用" in warning for warning in report["warnings"])
    assert "学生已保存的社区垃圾分类调研正文" in document_text(Document(output / "proposal.docx"))
    assert store.get_project(pid)["sections"]["background"] == "这是学生已保存的社区垃圾分类调研正文。"


def test_unreadable_optional_figure_cannot_block_worker_word_export(tmp_path, monkeypatch):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    store = Store(tmp_path / "data")
    pid = store.create_project("研究项目")["id"]
    figure = tmp_path / "broken.png"
    figure.write_bytes(b"not an image")
    store.update_project(pid, state={"skill_id": "innovation-research", "outline_confirmed": True},
                         outline=[{"id": "intro", "title": "研究背景"}],
                         sections={"intro": "这里是已保存的学生正文。"},
                         diagrams=[{"id": "fig1", "title": "路线图", "section_id": "intro",
                                    "preview": str(figure), "anchor": -1}])
    output = tmp_path / "output"
    report = export_material(store, pid, output)
    text = document_text(Document(output / "proposal.docx"))
    assert "已保存的学生正文" in text and "图 1 暂无法嵌入" in text
    assert any("图 1" in warning and "无法读取" in warning for warning in report["warnings"])


def test_failed_layout_hardening_preserves_worker_word_draft(tmp_path, monkeypatch):
    from pathlib import Path
    import utils.docx_layout_fix as layout
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    store = Store(tmp_path / "data")
    pid = store.create_project("研究项目")["id"]
    store.update_project(pid, state={"skill_id": "social-survey", "outline_confirmed": True},
                         outline=[{"id": "intro", "title": "项目简介"}],
                         sections={"intro": "学生已保存的正文。"})
    def interrupted_hardening(_input, out=None):
        Path(out).write_bytes(b"partial corrupted result")
        raise OSError("interrupted")
    monkeypatch.setattr(layout, "fix", interrupted_hardening)
    output = tmp_path / "output"
    report = export_material(store, pid, output)
    assert "学生已保存的正文" in document_text(Document(output / "proposal.docx"))
    assert any("排版优化未完成" in item for item in report["warnings"])
    assert not (output / ".proposal-hardened.docx").exists()


def test_income_omission_still_rejects_uninspectable_template(tmp_path, monkeypatch):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    store = Store(tmp_path / "data")
    pid = store.create_project("助学金")["id"]
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a docx archive")
    doc = store.add_document(pid, "broken.docx", str(path), "template", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    store.update_project(pid, state={"skill_id": "grant-application", "outline_confirmed": True},
                         template_document_id=doc["id"], outline=[{"id": "letter", "title": "申请书"}],
                         sections={"letter": "尊敬的老师：现提出申请。"})
    store.add_message(pid, "user", "不要写我的家庭收入。")
    with pytest.raises(ValueError, match="无法检查"):
        export_material(store, pid, tmp_path / "worker")


@pytest.mark.parametrize("template_type", ["docx", "pdf"])
def test_cloud_export_fetches_selected_template_and_photo_not_unrelated_source(tmp_path, monkeypatch, template_type):
    """A missing source upload must not block export of already saved text."""
    from PIL import Image
    from proposal.exporter import export_project
    from proposal.supabase_store import SupabaseStore
    backing = Store(tmp_path / "backing")
    pid = backing.create_project("社区研究")["id"]
    backing.update_project(pid, state={"skill_id": "social-survey", "outline_confirmed": True},
                           template_document_id="chosen", outline=[{"id": "intro", "title": "项目简介"}],
                           sections={"intro": "学生保留的完整正文。"})
    template_io = io.BytesIO()
    if template_type == "docx":
        template = Document()
        template.add_paragraph("{{section:intro}}")
        template.save(template_io)
    else:
        template_io.write(b"%PDF-test-fixture")
    image_io = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(image_io, format="PNG")
    cache = tmp_path / "cloud-cache"
    cache.mkdir()
    documents = [
        {"id": "chosen", "project_id": pid, "kind": "template", "original_name": f"school.{template_type}",
         "stored_path": str(cache / f"school.{template_type}"), "extracted_text": "项目简介\n项目背景"},
        {"id": "photo", "project_id": pid, "kind": "photo", "original_name": "photo.png",
         "stored_path": str(cache / "photo.png"), "extracted_text": ""},
        {"id": "unrelated", "project_id": pid, "kind": "source", "original_name": "large.pdf",
         "stored_path": str(cache / "large.pdf"), "extracted_text": "已提取的 OCR 资料", "confirmed": True,
         "confirmation_origin": "user"},
        {"id": "old-template", "project_id": pid, "kind": "template", "original_name": "old.docx",
         "stored_path": str(cache / "old.docx"), "extracted_text": ""},
    ]
    cloud = SupabaseStore("https://example.test", "public-test-key", data_dir=tmp_path / "cloud")
    monkeypatch.setattr(cloud, "get_project", lambda _pid: backing.get_project(pid))
    monkeypatch.setattr(cloud, "list_documents", lambda _pid, **_kw: documents)
    monkeypatch.setattr(cloud, "messages", lambda *_a, **_kw: [])
    fetched = []
    def fetch(doc_id, download=True):
        fetched.append(doc_id)
        assert doc_id != "unrelated", "an inaccessible source is not needed for a saved draft"
        document = next(d for d in documents if d["id"] == doc_id)
        if download:
            from pathlib import Path
            Path(document["stored_path"]).write_bytes(template_io.getvalue() if doc_id == "chosen" else image_io.getvalue())
        return document
    monkeypatch.setattr(cloud, "get_document", fetch)
    output = tmp_path / "result.docx"
    result = export_project(cloud, pid, output)
    rendered = Document(output)
    assert "学生保留的完整正文" in document_text(rendered)
    assert len(rendered.inline_shapes) == 1
    assert set(fetched) == {"chosen", "photo"}
    assert documents[2]["extracted_text"] == "已提取的 OCR 资料"
    assert result["used_original_template"] is (template_type == "docx")


def test_cloud_export_keeps_confirmed_ocr_fields_without_downloading_source_file(tmp_path, monkeypatch):
    from proposal.exporter import export_project
    from proposal.supabase_store import SupabaseStore
    backing = Store(tmp_path / "backing")
    pid = backing.create_project("奖学金")["id"]
    backing.update_project(pid, state={"skill_id": "national-scholarship", "outline_confirmed": True},
                           template_document_id="template", outline=[{"id": "intro", "title": "申请书"}],
                           sections={"intro": "本人现提出申请。"})
    template = Document()
    table = template.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "姓名", "【姓名】"
    table.cell(1, 0).text, table.cell(1, 1).text = "专业", "【专业】"
    raw_template = io.BytesIO()
    template.save(raw_template)
    local_template = tmp_path / "chosen.docx"
    documents = [
        {"id": "template", "project_id": pid, "kind": "template", "original_name": "school.docx",
         "stored_path": str(local_template), "extracted_text": ""},
        {"id": "source", "project_id": pid, "kind": "source", "original_name": "成绩单.pdf",
         "stored_path": str(tmp_path / "absent.pdf"), "extracted_text": "姓名：李明\n专业：环境工程",
         "confirmed": True, "confirmation_origin": "user", "low_confidence_count": 0},
    ]
    cloud = SupabaseStore("https://example.test", "public-test-key", data_dir=tmp_path / "cloud")
    monkeypatch.setattr(cloud, "get_project", lambda _pid: backing.get_project(pid))
    monkeypatch.setattr(cloud, "list_documents", lambda _pid, **_kw: documents)
    monkeypatch.setattr(cloud, "messages", lambda *_a, **_kw: [{"role": "user", "content": "我叫李明"}])
    fetched = []
    def get_document(doc_id, download=True):
        fetched.append(doc_id)
        assert doc_id == "template"
        local_template.write_bytes(raw_template.getvalue())
        return documents[0]
    monkeypatch.setattr(cloud, "get_document", get_document)
    output = tmp_path / "result.docx"
    export_project(cloud, pid, output)
    rendered = Document(output)
    assert rendered.tables[0].cell(0, 1).text == "李明"
    assert rendered.tables[0].cell(1, 1).text == "环境工程"
    assert set(fetched) == {"template"}


@pytest.mark.parametrize("missing_kind", ["template", "photo"])
def test_cloud_missing_selected_asset_keeps_body_with_warning(tmp_path, monkeypatch, missing_kind):
    import urllib.error
    from proposal.exporter import export_project
    from proposal.supabase_store import SupabaseStore
    backing = Store(tmp_path / "backing")
    pid = backing.create_project("项目")["id"]
    backing.update_project(pid, state={"skill_id": "social-survey", "outline_confirmed": True},
        template_document_id="template", outline=[{"id": "intro", "title": "项目简介"}],
        sections={"intro": "学生保存的内容。"})
    template = Document()
    template.add_paragraph("{{section:intro}}")
    template_buffer = io.BytesIO()
    template.save(template_buffer)
    docs = [
        {"id": "template", "project_id": pid, "kind": "template", "original_name": "school.docx", "stored_path": str(tmp_path / "school.docx")},
        {"id": "photo", "project_id": pid, "kind": "photo", "original_name": "实践照片.png", "stored_path": str(tmp_path / "photo.png")},
    ]
    cloud = SupabaseStore("https://example.test", "public-test-key", data_dir=tmp_path / "cloud")
    monkeypatch.setattr(cloud, "get_project", lambda _pid: backing.get_project(pid))
    monkeypatch.setattr(cloud, "list_documents", lambda _pid, **_kw: docs)
    monkeypatch.setattr(cloud, "messages", lambda *_a, **_kw: [])
    def get_document(doc_id, download=True):
        document = next(d for d in docs if d["id"] == doc_id)
        if document["kind"] == missing_kind:
            raise RuntimeError("missing") from urllib.error.HTTPError("https://example.test", 404, "missing", {}, None)
        if doc_id == "template":
            (tmp_path / "school.docx").write_bytes(template_buffer.getvalue())
        else:
            from PIL import Image
            Image.new("RGB", (20, 20), "white").save(tmp_path / "photo.png")
        return document
    monkeypatch.setattr(cloud, "get_document", get_document)
    output = tmp_path / "result.docx"
    result = export_project(cloud, pid, output)
    assert "学生保存的内容" in document_text(Document(output))
    if missing_kind == "template":
        assert result["template_status"] == "needs_review" and not result["used_original_template"]
        assert any("模板" in warning and "通用" in warning for warning in result["warnings"])
    else:
        assert any("实践照片.png" in warning and "暂不可用" in warning for warning in result["warnings"])


def test_cloud_export_never_masks_permission_failure_as_missing_asset(tmp_path, monkeypatch):
    import urllib.error
    from proposal.supabase_store import SupabaseStore
    cloud = SupabaseStore("https://example.test", "public-test-key", data_dir=tmp_path)
    monkeypatch.setattr(cloud, "get_project", lambda _pid: {"template_document_id": "template", "diagrams": []})
    monkeypatch.setattr(cloud, "list_documents", lambda *_a, **_kw: [{"id": "template", "kind": "template"}])
    def denied(*_args, **_kwargs):
        raise RuntimeError("denied") from urllib.error.HTTPError("https://example.test", 403, "denied", {}, None)
    monkeypatch.setattr(cloud, "get_document", denied)
    with pytest.raises(RuntimeError, match="denied"):
        cloud.project_for_export("project")
