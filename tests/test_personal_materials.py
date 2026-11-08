"""Confirmed, single-person material extraction uses the actual upload path."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

import server.app as app
from proposal.personal_materials import confirmed_personal_material_fields
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture
def upload_client(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_args, **_kwargs: (None, ""))
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "tools", ProposalTools(store, retriever))
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    with TestClient(app.app) as client:
        yield client, store, store.create_project()["id"]


def _upload(client, store, project_id, name, content, *, kind="source", confirm=True):
    response = client.post(f"/api/projects/{project_id}/documents?kind={kind}", files={
        "files": (name, content, "application/octet-stream"),
    })
    assert response.status_code == 200, response.text
    doc = response.json()["documents"][0]["document"]
    if confirm and kind != "template":
        assert client.patch(f"/api/documents/{doc['id']}/confirm", json={"confirmed": True}).status_code == 200
    return store.get_document(doc["id"])


def _word(rows):
    document = Document()
    table = document.add_table(rows=len(rows), cols=max(map(len, rows)))
    for row, values in zip(table.rows, rows):
        for cell, value in zip(row.cells, values):
            cell.text = value
    data = io.BytesIO()
    document.save(data)
    return data.getvalue()


def _pdf(pages):
    """Create a real PDF with a Unicode map, independent of system fonts."""
    writer = PdfWriter()
    cmap = b"""/CIDInit /ProcSet findresource begin
12 dict begin begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> def
/CMapName /Id def /CMapType 2 def
1 begincodespacerange <0000> <FFFF> endcodespacerange
1 beginbfrange <0000> <FFFF> <0000> endbfrange
endcmap CMapName currentdict /CMap defineresource pop end end"""
    stream = DecodedStreamObject()
    stream.set_data(cmap)
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
        NameObject("/ToUnicode"): writer._add_object(stream),
    })
    font_ref = writer._add_object(font)
    for lines in pages:
        page = writer.add_blank_page(width=595, height=842)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): font_ref,
        })})
        body = "BT /F1 12 Tf 30 750 Td " + " 0 -20 Td ".join(
            f"<{line.encode('utf-16-be').hex()}> Tj" for line in lines
        ) + " ET"
        page_stream = DecodedStreamObject()
        page_stream.set_data(body.encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(page_stream)
    data = io.BytesIO()
    writer.write(data)
    return data.getvalue()


def test_real_confirmed_word_table_with_paired_cells(upload_client):
    client, store, project_id = upload_client
    data = _word([("姓名", "李明", "学院", "信息学院"), ("专业", "计算机", "绩点", "3.8")])
    doc = _upload(client, store, project_id, "个人资料.docx", data)
    assert "姓名 | 李明 | 学院 | 信息学院" in doc["extracted_text"]
    assert confirmed_personal_material_fields(doc, "李明", project_id=project_id) == {
        "姓名": "李明", "学院": "信息学院", "专业": "计算机", "绩点": "3.8",
    }


def test_no_title_real_pdf_and_gbk_txt(upload_client):
    client, store, project_id = upload_client
    pdf = _upload(client, store, project_id, "信息.pdf", _pdf([["姓名：李明", "学院：信息学院"]]))
    assert "[第 1 页]" in pdf["extracted_text"]
    assert confirmed_personal_material_fields(pdf, "李明", project_id=project_id) == {
        "姓名": "李明", "学院": "信息学院",
    }
    txt = _upload(client, store, project_id, "信息.txt", "姓名：李明\n学院：信息学院".encode("gbk"))
    assert confirmed_personal_material_fields(txt, "李明", project_id=project_id)["学院"] == "信息学院"


@pytest.mark.parametrize("rows", [
    [("姓名", "李明"), ("学院", "信息学院"), ("姓名", "王五")],
    [("姓名", "李明"), ("姓名", "李明")],
    [("姓名", "学院"), ("李明", "信息学院"), ("王五", "外国语学院")],
    [("姓名", "李明", "学院", "专业")],
    [("姓名", "李明", "学院", "信息学院"), ("王五", "外国语学院", "备注", "获奖")],
])
def test_multiple_people_repeated_labels_or_crossed_columns_are_rejected(upload_client, rows):
    client, store, project_id = upload_client
    # Use a rectangular table, as in an actual Word document.
    data = _word(rows)
    doc = _upload(client, store, project_id, "表格.docx", data)
    assert confirmed_personal_material_fields(doc, "李明", project_id=project_id) == {}


def test_unconfirmed_other_person_other_project_and_official_material_are_excluded(upload_client):
    client, store, project_id = upload_client
    text = "姓名：李明\n学院：信息学院".encode()
    unconfirmed = _upload(client, store, project_id, "未确认.txt", text, confirm=False)
    assert confirmed_personal_material_fields(unconfirmed, "李明", project_id=project_id) == {}
    official = _upload(client, store, project_id, "通知.txt", text, kind="official")
    assert confirmed_personal_material_fields(official, "李明", project_id=project_id) == {}
    source = _upload(client, store, project_id, "材料.txt", text)
    assert confirmed_personal_material_fields(source, "王五", project_id=project_id) == {}
    assert confirmed_personal_material_fields(source, "李明", project_id="different-project") == {}


def test_multi_page_requires_each_page_to_identify_the_same_person(upload_client):
    client, store, project_id = upload_client
    pdf = _upload(client, store, project_id, "两页.pdf", _pdf([["姓名：李明"], ["学院：信息学院"]]))
    assert confirmed_personal_material_fields(pdf, "李明", project_id=project_id) == {}
    pdf = _upload(client, store, project_id, "同一学生.pdf", _pdf([
        ["姓名：李明", "专业：计算机"], ["姓名：李明", "学院：信息学院", "绩点：3.8"],
    ]))
    assert confirmed_personal_material_fields(pdf, "李明", project_id=project_id) == {
        "姓名": "李明", "专业": "计算机", "学院": "信息学院", "绩点": "3.8",
    }
    other = _upload(client, store, project_id, "不同学生.pdf", _pdf([
        ["姓名：李明", "专业：计算机"], ["姓名：王五", "学院：信息学院"],
    ]))
    assert confirmed_personal_material_fields(other, "李明", project_id=project_id) == {}


@pytest.mark.parametrize(("label", "value_one", "value_two"), [
    ("学号", "20250101", "20250202"),
    ("班级", "计算机一班", "计算机二班"),
    ("学校", "甲大学", "乙大学"),
    ("出生年月", "2005年1月", "2006年2月"),
])
def test_same_name_different_identity_fields_are_not_combined(upload_client, label, value_one, value_two):
    client, store, project_id = upload_client
    pdf = _upload(client, store, project_id, "同名学生.pdf", _pdf([
        ["姓名：李明", f"{label}：{value_one}", "专业：计算机"],
        ["姓名：李明", f"{label}：{value_two}", "绩点：3.8"],
    ]))
    assert confirmed_personal_material_fields(pdf, "李明", project_id=project_id) == {}


def test_same_name_and_consistent_identity_fields_allow_multi_page(upload_client):
    client, store, project_id = upload_client
    pdf = _upload(client, store, project_id, "同一学生.pdf", _pdf([
        ["姓名：李明", "学号：20250101", "学校：甲大学", "专业：计算机"],
        ["姓名：李明", "学号：20250101", "学校：甲大学", "绩点：3.8"],
    ]))
    assert confirmed_personal_material_fields(pdf, "李明", project_id=project_id) == {
        "姓名": "李明", "专业": "计算机", "绩点": "3.8",
    }


def test_same_name_different_student_id_never_reaches_draft(upload_client, monkeypatch):
    from proposal.agent import OllamaAgent
    client, store, project_id = upload_client
    monkeypatch.setattr(app, "agent", OllamaAgent(store, app.tools))
    store.update_project(project_id, state={"skill_id": "national-scholarship"})
    store.add_message(project_id, "user", "我叫李明，准备申请国家奖学金。")
    _upload(client, store, project_id, "同名学生.pdf", _pdf([
        ["姓名：李明", "学号：20250101", "专业：计算机"],
        ["姓名：李明", "学号：20250202", "绩点：3.8"],
    ]))
    result = client.post(f"/api/projects/{project_id}/chat", json={"message": "请写国家奖学金申请书。"})
    assert result.status_code == 200
    assert "计算机" not in result.json()["message"]
    assert "3.8" not in result.json()["message"]


def _national_scholarship_student(upload_client, monkeypatch):
    from proposal.agent import OllamaAgent
    client, store, project_id = upload_client
    monkeypatch.setattr(app, "agent", OllamaAgent(store, app.tools))
    store.update_project(project_id, state={"skill_id": "national-scholarship"})
    store.add_message(project_id, "user", "我叫李明，我的专业是数学，准备申请国家奖学金。")
    return client, store, project_id


def test_conflicting_identifiers_across_uploaded_documents_do_not_mix_students(upload_client, monkeypatch):
    client, store, project_id = _national_scholarship_student(upload_client, monkeypatch)
    _upload(client, store, project_id, "材料甲.txt", "姓名：李明\n学号：20250101\n学院：信息学院".encode())
    _upload(client, store, project_id, "材料乙.pdf", _pdf([["姓名：李明", "学号：20250202", "绩点：3.8"]]))
    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "请写国家奖学金申请书。"})
    assert response.status_code == 200
    text = response.json()["message"]
    assert "李明" in text and "数学" in text
    assert "信息学院" not in text and "3.8" not in text
    assert "不同说法" in text
    draft_url = f"/api/projects/{project_id}/chat-drafts"
    draft = client.get(draft_url).json()
    saved = client.post(draft_url + "/confirm", json={
        "snapshot": draft["snapshot"], "items": [{"id": draft["items"][0]["id"]}],
    })
    assert saved.status_code == 200
    exported = client.post(f"/api/projects/{project_id}/export")
    assert exported.status_code == 200
    downloaded = client.get(exported.json()["download_url"])
    word = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(downloaded.content)).paragraphs)
    assert "李明" in word and "数学" in word
    assert "信息学院" not in word and "3.8" not in word


@pytest.mark.parametrize(("confirmed", "kind", "other_name"), [
    (False, "source", "李明"),
    (True, "official", "李明"),
    (True, "template", "李明"),
    (True, "source", "王五"),
])
def test_ineligible_documents_cannot_block_matching_material(upload_client, monkeypatch, confirmed, kind, other_name):
    client, store, project_id = _national_scholarship_student(upload_client, monkeypatch)
    _upload(client, store, project_id, "资料.txt", "姓名：李明\n学号：20250101\n学院：信息学院".encode())
    _upload(client, store, project_id, "其他.txt", f"姓名：{other_name}\n学号：20250202\n绩点：3.8".encode(),
            kind=kind, confirm=confirmed)
    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "请写国家奖学金申请书。"})
    assert response.status_code == 200
    text = response.json()["message"]
    assert "信息学院" in text and "数学" in text
    assert "3.8" not in text


def test_same_identity_across_confirmed_documents_can_be_combined(upload_client, monkeypatch):
    client, store, project_id = _national_scholarship_student(upload_client, monkeypatch)
    _upload(client, store, project_id, "材料甲.txt", "姓名：李明\n学号：20250101\n学院：信息学院".encode())
    _upload(client, store, project_id, "材料乙.pdf", _pdf([["姓名：李明", "学号：20250101", "绩点：3.8"]]))
    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "请写国家奖学金申请书。"})
    assert response.status_code == 200
    assert all(value in response.json()["message"] for value in ("李明", "数学", "信息学院", "3.8"))


@pytest.mark.parametrize(("student_number", "included"), [("20250101", True), ("20250202", False)])
def test_material_student_id_must_match_explicit_user_student_id(upload_client, monkeypatch, student_number, included):
    client, store, project_id = _national_scholarship_student(upload_client, monkeypatch)
    store.add_message(project_id, "user", "我的学号是20250101。")
    _upload(client, store, project_id, "资料.txt",
            f"姓名：李明\n学号：{student_number}\n学院：信息学院".encode())
    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "请写国家奖学金申请书。"})
    assert response.status_code == 200
    text = response.json()["message"]
    assert ("信息学院" in text) is included
    assert "李明" in text and "数学" in text and "20250101" not in text and student_number not in text


def test_user_corrected_student_id_is_used_to_disambiguate(upload_client, monkeypatch):
    client, store, project_id = _national_scholarship_student(upload_client, monkeypatch)
    store.add_message(project_id, "user", "我的学号是20250101。")
    store.add_message(project_id, "user", "更正，我的学号改为20250202。")
    _upload(client, store, project_id, "资料.txt", "姓名：李明\n学号：20250202\n学院：信息学院".encode())
    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "请写国家奖学金申请书。"})
    assert response.status_code == 200
    assert "信息学院" in response.json()["message"]


def test_other_students_student_id_is_not_used_to_disambiguate(upload_client, monkeypatch):
    client, store, project_id = _national_scholarship_student(upload_client, monkeypatch)
    store.add_message(project_id, "user", "我的同学王五的学号是20250101。")
    _upload(client, store, project_id, "资料.txt", "姓名：李明\n学号：20250202\n学院：信息学院".encode())
    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "请写国家奖学金申请书。"})
    assert response.status_code == 200
    assert "信息学院" in response.json()["message"]


def test_ambiguous_narrative_is_excluded(upload_client):
    client, store, project_id = upload_client
    text = "姓名：李明\n学院：信息学院\n王五获得二等奖".encode()
    doc = _upload(client, store, project_id, "多人材料.txt", text)
    assert confirmed_personal_material_fields(doc, "李明", project_id=project_id) == {}


def test_unreadable_pdf_page_and_low_confidence_ocr_are_not_used(upload_client, monkeypatch):
    from proposal import documents
    client, store, project_id = upload_client
    monkeypatch.setattr(documents, "_ocr_image", lambda _data: ("", 0))
    pdf = _upload(client, store, project_id, "部分空白.pdf", _pdf([["姓名：李明", "学院：信息学院"], []]))
    assert "第 2 页未能识别" in pdf["extraction_warning"]
    assert confirmed_personal_material_fields(pdf, "李明", project_id=project_id) == {}
    source = _upload(client, store, project_id, "资料.txt", "姓名：李明\n学院：信息学院".encode())
    source["low_confidence_count"] = 1
    assert confirmed_personal_material_fields(source, "李明", project_id=project_id) == {}


def test_multi_page_pdf_reaches_conversation_and_saved_word(upload_client, monkeypatch):
    from proposal.agent import OllamaAgent
    client, store, project_id = upload_client
    monkeypatch.setattr(app, "agent", OllamaAgent(store, app.tools))
    store.update_project(project_id, state={"skill_id": "national-scholarship"})
    store.add_message(project_id, "user", "我叫李明，准备申请国家奖学金。")
    _upload(client, store, project_id, "个人资料.pdf", _pdf([
        ["姓名：李明", "专业：计算机"], ["姓名：李明", "学院：信息学院", "绩点：3.8"],
    ]))
    result = client.post(f"/api/projects/{project_id}/chat", json={"message": "请写国家奖学金申请书。"})
    assert result.status_code == 200
    assert all(value in result.json()["message"] for value in ("李明", "计算机", "信息学院", "3.8"))
    draft_url = f"/api/projects/{project_id}/chat-drafts"
    draft = client.get(draft_url).json()
    saved = client.post(draft_url + "/confirm", json={
        "snapshot": draft["snapshot"], "items": [{"id": draft["items"][0]["id"]}],
    })
    assert saved.status_code == 200
    exported = client.post(f"/api/projects/{project_id}/export")
    assert exported.status_code == 200
    downloaded = client.get(exported.json()["download_url"])
    assert downloaded.status_code == 200
    text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(downloaded.content)).paragraphs)
    assert "信息学院" in text and "3.8" in text


def test_income_is_only_extracted_for_the_explicit_supported_scenario(upload_client):
    client, store, project_id = upload_client
    doc = _upload(client, store, project_id, "资料.txt", "姓名：李明\n家庭年收入：2万元".encode())
    assert confirmed_personal_material_fields(doc, "李明", project_id=project_id) == {"姓名": "李明"}
    assert confirmed_personal_material_fields(doc, "李明", project_id=project_id, include_family_income=True) == {
        "姓名": "李明", "家庭年收入": "2万元",
    }
