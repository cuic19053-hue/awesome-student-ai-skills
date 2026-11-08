"""Realistic national-scholarship turns remain useful without invented facts."""
import io
import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.chat_context import is_scholarship_draft_request, scholarship_student_facts
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture
def conversation(tmp_path, monkeypatch):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    project = store.create_project()
    store.update_project(project["id"], state={"skill_id": "national-scholarship"})
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "retriever", tools.retriever)
    # Exercise real extraction/confirmation and keyword indexing without
    # relying on a separate embedding model or remote service.
    monkeypatch.setattr(tools.retriever, "_embed_verified", lambda *_args, **_kwargs: (None, ""))
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(agent, "_post", lambda *_: pytest.fail("local response must not call a model"))
    monkeypatch.setattr(agent, "_stream_post", lambda *_: pytest.fail("local response must not call a model"))
    with TestClient(app.app) as client:
        yield client, store, project["id"]


@pytest.mark.parametrize("stream", [False, True])
def test_ordinary_draft_and_followup_keep_student_facts_and_are_saveable(conversation, stream):
    client, store, pid = conversation
    base = f"/api/projects/{pid}"
    first = client.post(base + "/chat", json={"message":
        "请帮我写国家奖学金申请书。我叫李明，学计算机专业，绩点3.8，专业排名3/80。没有科研经历，不要编造。",
        "stream": stream, "llm_config": {"provider": "preset"}})
    assert first.status_code == 200
    assert "李明" in first.text and "3.8" in first.text and "3/80" in first.text
    assert "<WritingBlock" in first.text
    assert "暂无科研经历" in first.text
    assert "科研成果丰硕" not in first.text and "预备党员" not in first.text
    assert store.get_workbench_credit_balance("local_user")["free_chat_count"] == 3
    second = client.post(base + "/chat", json={"message": "申报条件是什么？请重新写一份申请书。"})
    assert second.status_code == 200
    assert "李明" in second.text and "3.8" in second.text and "3/80" in second.text
    preview = client.get(base + "/chat-drafts").json()
    assert len(preview["items"]) == 1
    assert "李明" in preview["items"][0]["content"]
    saved = client.post(base + "/chat-drafts/confirm", json={
        "snapshot": preview["snapshot"], "items": [{"id": preview["items"][0]["id"]}],
    })
    assert saved.status_code == 200


def test_preparation_question_answers_steps_without_calling_model(conversation):
    client, store, pid = conversation
    response = client.post(f"/api/projects/{pid}/chat", json={
        "message": "我想申请国家奖学金，我的专业排名是3/80，应该怎么准备？",
        "llm_config": {"provider": "preset"},
    })
    assert response.status_code == 200
    assert "成绩单" in response.text and "学校" in response.text
    assert store.get_workbench_credit_balance("local_user")["free_chat_count"] == 3


def test_rewrite_with_corrected_gpa_does_not_add_a_policy_warning(conversation):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫李明，学计算机专业，绩点3.8，排名3/80。")
    response = client.post(f"/api/projects/{pid}/chat", json={
        "message": "更正，我的绩点改为3.7。请重新写国家奖学金申请书。",
    })
    assert response.status_code == 200
    text = response.json()["message"]
    assert "绩点为3.7" in text and "李明" in text and "3/80" in text
    assert "政策资料核查" not in text and "未检索到" not in text


def test_real_gpa_eligibility_question_still_gets_evidence(conversation):
    client, _, pid = conversation
    response = client.post(f"/api/projects/{pid}/chat", json={
        "message": "绩点多少可以申请国家奖学金？请重新写国家奖学金申请书。",
    })
    assert response.status_code == 200
    assert "政策资料核查" in response.json()["message"]


@pytest.mark.parametrize("prompt", ["不要帮我写申请书", "先别写申请书，讨论一下", "请润色这份申请书", "申请书怎么写？", "请修改申请书", "请写国家奖学金申请书的提纲"])
def test_non_drafting_requests_are_not_replaced_by_a_new_draft(prompt):
    assert not is_scholarship_draft_request(prompt, {"state": {"skill_id": "national-scholarship"}})


def test_no_invention_instruction_does_not_cancel_an_explicit_draft():
    prompt = "我没有科研经历，不要编造，直接写申请书。"
    assert is_scholarship_draft_request(prompt, {"state": {"skill_id": "national-scholarship"}})


@pytest.mark.parametrize("prompt", ["帮我重新写一份", "我想申请国家奖学金，帮我写一下", "请直接给我一篇完整申请书"])
def test_contextual_followup_requests_are_recognized(prompt):
    assert is_scholarship_draft_request(prompt, {"state": {"skill_id": "national-scholarship"}})


def test_history_conflicts_and_explicit_correction_are_handled():
    history = [{"role": "user", "content": "我叫李明，我的绩点是3.8。"},
               {"role": "assistant", "content": "你是预备党员，获得奖项。"},
               {"role": "user", "content": "我的绩点是3.9。"}]
    facts, conflict = scholarship_student_facts(history, "请写申请书", [])
    assert facts == {"姓名": "李明"} and conflict
    facts, conflict = scholarship_student_facts(history, "更正，我的绩点改为3.7。请写申请书", [])
    assert facts == {"姓名": "李明", "绩点": "3.7"} and not conflict
    facts, conflict = scholarship_student_facts(history[:1], "我的绩点是3.7，我的绩点是3.9。", [])
    assert facts == {"姓名": "李明"} and conflict


def test_only_matching_confirmed_personal_material_contributes():
    history = [{"role": "user", "content": "我叫李明，学计算机专业。"}]
    docs = [
        {"kind": "source", "confirmed": 1, "confirmation_origin": "user", "extracted_text":
         "姓名：李明\n学院：信息学院\n获奖：数学建模二等奖"},
        {"kind": "source", "confirmed": 0, "confirmation_origin": "user", "extracted_text": "姓名：李明\n绩点：4.0"},
        {"kind": "official", "confirmed": 1, "confirmation_origin": "user", "extracted_text": "姓名：李明\n绩点：4.0"},
        {"kind": "template", "confirmed": 1, "confirmation_origin": "user", "extracted_text": "姓名：李明\n绩点：4.0"},
        {"kind": "source", "confirmed": 1, "confirmation_origin": "user", "extracted_text": "姓名：王五\n绩点：4.0"},
        {"kind": "source", "confirmed": 1, "confirmation_origin": "", "extracted_text": "姓名：李明\n排名：1/100"},
    ]
    for doc in docs:
        doc["project_id"] = "project-a"
    facts, conflict = scholarship_student_facts(history, "请写申请书", docs, project_id="project-a")
    assert not conflict
    assert facts == {"姓名": "李明", "专业": "计算机", "学院": "信息学院", "获奖": "数学建模二等奖"}
    facts, _ = scholarship_student_facts(history, "我没有获奖，请写申请书", docs, project_id="project-a")
    assert "获奖" not in facts


def test_confirmed_document_flows_into_draft_without_cross_project_leak(conversation):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫李明，学计算机专业。")
    doc = store.add_document(pid, "材料.txt", "test.txt", "source", "text/plain")
    store.update_document_extraction(doc["id"], "姓名：李明\n学院：信息学院\n获奖：数学建模二等奖",
                                     "ready", confirmed=True, confirmed_by_user=True)
    response = client.post(f"/api/projects/{pid}/chat", json={"message": "帮我写国家奖学金申请书"})
    assert response.status_code == 200
    assert "信息学院" in response.text and "数学建模二等奖" in response.text
    other = store.create_project()
    store.update_project(other["id"], state={"skill_id": "national-scholarship"})
    other_response = client.post(f"/api/projects/{other['id']}/chat", json={"message": "帮我写国家奖学金申请书"})
    assert other_response.status_code == 200
    assert "李明" not in other_response.text and "数学建模二等奖" not in other_response.text


@pytest.mark.parametrize(("encoding", "name", "confirm", "included"), [
    ("utf-8", "李明", True, True),
    ("gbk", "李明", True, True),
    ("utf-8", "李明", False, False),
    ("utf-8", "王五", True, False),
])
def test_real_multipart_confirmed_text_flows_into_draft(conversation, encoding, name, confirm, included):
    client, store, pid = conversation
    first = client.post(f"/api/projects/{pid}/chat", json={
        "message": "我叫李明，帮我写国家奖学金申请书。",
    })
    assert first.status_code == 200
    content = f"姓名：{name}\n学院：信息学院\n获奖：数学建模二等奖".encode(encoding)
    upload = client.post(f"/api/projects/{pid}/documents?kind=source",
                         files={"files": ("个人信息.txt", content, "text/plain")})
    assert upload.status_code == 200
    document = upload.json()["documents"][0]["document"]
    assert "[行 1]" in document["extracted_text"]
    if confirm:
        response = client.patch(f"/api/documents/{document['id']}/confirm", json={"confirmed": True})
        assert response.status_code == 200, response.text
        assert store.get_document(document["id"])["confirmation_origin"] == "user"
    draft = client.post(f"/api/projects/{pid}/chat", json={"message": "帮我重新写国家奖学金申请书"})
    assert draft.status_code == 200
    assert ("信息学院" in draft.text) is included
    assert ("数学建模二等奖" in draft.text) is included


def test_user_authored_nested_line_marker_is_not_stripped_as_a_field():
    history = [{"role": "user", "content": "我叫李明。"}]
    document = {"project_id": "project-a", "kind": "source", "confirmed": 1, "confirmation_origin": "user", "extracted_text":
                "[行 1] [行 1] 姓名：李明\n[行 2] 学院：信息学院"}
    facts, _ = scholarship_student_facts(history, "请写申请书", [document], project_id="project-a")
    assert facts == {"姓名": "李明"}


def test_real_docx_paragraph_upload_is_used_after_confirmation(conversation):
    client, _, pid = conversation
    client.post(f"/api/projects/{pid}/chat", json={"message": "我叫李明，帮我写国家奖学金申请书。"})
    word = Document()
    for line in ("姓名：李明", "学院：信息学院", "获奖：数学建模二等奖"):
        word.add_paragraph(line)
    data = io.BytesIO()
    word.save(data)
    uploaded = client.post(f"/api/projects/{pid}/documents?kind=source", files={
        "files": ("个人资料.docx", data.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    })
    assert uploaded.status_code == 200
    document = uploaded.json()["documents"][0]["document"]
    assert "[段落 1]" in document["extracted_text"]
    assert client.patch(f"/api/documents/{document['id']}/confirm", json={"confirmed": True}).status_code == 200
    draft = client.post(f"/api/projects/{pid}/chat", json={"message": "帮我重新写国家奖学金申请书"})
    assert "信息学院" in draft.text and "数学建模二等奖" in draft.text


@pytest.mark.parametrize("source", [
    "[段落 1] 姓名：李明\n[段落 2] 学院：信息学院",
    "[表格 1 第 1 行] 姓名：李明\n[表格 1 第 2 行] 学院：信息学院",
    "[第 1 页]\n姓名：李明\n学院：信息学院",
])
def test_extracted_document_references_keep_profile_fields(source):
    history = [{"role": "user", "content": "我叫李明。"}]
    document = {"project_id": "project-a", "kind": "source", "confirmed": 1, "confirmation_origin": "user", "extracted_text": source}
    facts, _ = scholarship_student_facts(history, "请写申请书", [document], project_id="project-a")
    assert facts == {"姓名": "李明", "学院": "信息学院"}


def test_opt_out_of_personal_data_survives_later_turn():
    history = [{"role": "user", "content": "我叫李明，我的绩点是3.8，没有科研经历。"},
               {"role": "user", "content": "请不要使用我的资料。"}]
    facts, _ = scholarship_student_facts(history, "请写申请书", [])
    assert facts == {}
