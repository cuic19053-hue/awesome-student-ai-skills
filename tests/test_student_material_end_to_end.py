"""Student journey with real, confirmed DOCX/PDF uploads and Word output."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

import server.app as app
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture
def student_client(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_args, **_kwargs: (None, ""))
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(agent, "_post", lambda *_args, **_kwargs: pytest.fail("Unexpected model call"))
    monkeypatch.setattr(agent, "_stream_post", lambda *_args, **_kwargs: pytest.fail("Unexpected model call"))
    with TestClient(app.app) as client:
        project_id = client.post("/api/projects/conversation").json()["id"]
        selected = client.post(f"/api/projects/{project_id}/skill", json={"skill_id": "national-scholarship"})
        assert selected.status_code == 200
        initial = client.post(f"/api/projects/{project_id}/chat", json={
            "message": "我叫李明，请帮我写国家奖学金申请书。",
        })
        assert initial.status_code == 200
        yield client, store, project_id


def _docx(rows):
    document = Document()
    table = document.add_table(rows=len(rows), cols=max(len(row) for row in rows))
    for table_row, values in zip(table.rows, rows):
        for cell, value in zip(table_row.cells, values):
            cell.text = value
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _pdf(lines):
    """Make a readable, single-page CJK PDF without depending on host fonts."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    cmap = DecodedStreamObject()
    cmap.set_data(b"""/CIDInit /ProcSet findresource begin
12 dict begin begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> def
/CMapName /Id def /CMapType 2 def
1 begincodespacerange <0000> <FFFF> endcodespacerange
1 beginbfrange <0000> <FFFF> <0000> endbfrange
endcmap CMapName currentdict /CMap defineresource pop end end""")
    child = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/CIDFontType2"),
        NameObject("/BaseFont"): NameObject("/Test"), NameObject("/CIDSystemInfo"): DictionaryObject({
            NameObject("/Registry"): NameObject("/Adobe"), NameObject("/Ordering"): NameObject("/Identity"),
            NameObject("/Supplement"): NumberObject(0),
        }),
    })
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type0"),
        NameObject("/BaseFont"): NameObject("/Test"), NameObject("/Encoding"): NameObject("/Identity-H"),
        NameObject("/DescendantFonts"): ArrayObject([writer._add_object(child)]),
        NameObject("/ToUnicode"): writer._add_object(cmap),
    })
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): writer._add_object(font),
    })})
    stream = DecodedStreamObject()
    body = "BT /F1 12 Tf 30 750 Td " + " 0 -20 Td ".join(
        f"<{line.encode('utf-16-be').hex()}> Tj" for line in lines
    ) + " ET"
    stream.set_data(body.encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _upload(client, project_id, filename, payload, *, kind="source", confirm=True):
    response = client.post(f"/api/projects/{project_id}/documents?kind={kind}", files={
        "files": (filename, payload, "application/octet-stream"),
    })
    assert response.status_code == 200, response.text
    document = response.json()["documents"][0]["document"]
    if confirm and kind != "template":
        result = client.patch(f"/api/documents/{document['id']}/confirm", json={"confirmed": True})
        assert result.status_code == 200, result.text
    return document


def _draft(client, project_id):
    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "请重新写国家奖学金申请书。"})
    assert response.status_code == 200, response.text
    return response.json()["message"]


def test_confirmed_word_table_reaches_saved_draft_and_downloaded_word(student_client):
    client, store, project_id = student_client
    data = _docx([("姓名", "李明", "学院", "信息学院"), ("专业", "计算机", "绩点", "3.8")])
    _upload(client, project_id, "个人资料.docx", data)
    text = _draft(client, project_id)
    assert all(value in text for value in ("李明", "信息学院", "计算机", "3.8"))
    assert "[表格" not in text
    draft_url = f"/api/projects/{project_id}/chat-drafts"
    review = client.get(draft_url).json()
    assert len(review["items"]) == 1
    saved = client.post(draft_url + "/confirm", json={
        "snapshot": review["snapshot"], "items": [{"id": review["items"][0]["id"]}],
    })
    assert saved.status_code == 200, saved.text
    assert "信息学院" in next(iter(store.get_project(project_id)["sections"].values()))
    exported = client.post(f"/api/projects/{project_id}/export")
    assert exported.status_code == 200, exported.text
    result = client.get(exported.json()["download_url"])
    assert result.status_code == 200
    word_text = "\n".join(p.text for p in Document(io.BytesIO(result.content)).paragraphs)
    assert "信息学院" in word_text and "3.8" in word_text


def test_confirmed_pdf_without_title_reaches_draft(student_client):
    client, _, project_id = student_client
    _upload(client, project_id, "单页资料.pdf", _pdf(["姓名：李明", "学院：信息学院", "绩点：3.8"]))
    text = _draft(client, project_id)
    assert "信息学院" in text and "3.8" in text
    assert "[第 1 页]" not in text


@pytest.mark.parametrize(("name", "confirmed", "kind"), [
    ("李明", False, "source"),
    ("王五", True, "source"),
    ("李明", True, "official"),
    ("李明", True, "template"),
])
def test_wrong_or_unconfirmed_material_never_populates_student_draft(student_client, name, confirmed, kind):
    client, _, project_id = student_client
    _upload(client, project_id, "材料.docx", _docx([("姓名", name), ("学院", "信息学院")]),
            kind=kind, confirm=confirmed)
    assert "信息学院" not in _draft(client, project_id)


def test_another_projects_confirmed_material_never_populates_student_draft(student_client):
    client, store, project_id = student_client
    other_id = store.create_project()["id"]
    _upload(client, other_id, "另一个项目.docx", _docx([("姓名", "李明"), ("学院", "信息学院")]))
    assert "信息学院" not in _draft(client, project_id)


def test_multiple_students_in_one_word_table_are_not_mixed_into_draft(student_client):
    client, _, project_id = student_client
    data = _docx([("姓名", "学院"), ("李明", "信息学院"), ("王五", "外国语学院")])
    _upload(client, project_id, "学生名单.docx", data)
    text = _draft(client, project_id)
    assert "信息学院" not in text and "外国语学院" not in text and "王五" not in text
