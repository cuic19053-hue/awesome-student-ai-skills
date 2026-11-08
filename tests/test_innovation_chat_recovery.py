"""Recover real-shaped project chat drafts only via explicit student review."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.chat_drafts import candidates, plain_project_chapters
from proposal.storage import Store

USER = "我想申请大创，题目是校园智能垃圾分类助手，帮我明确研究目标并起草项目摘要，不要虚构成果。"
REPLY = """好的，我们先整理初稿。

### 研究目标
1. **总目标**：开发基于图像识别技术的智能垃圾分类助手，帮助学生识别校园常见垃圾。
2. **阶段目标**：进行需求分析，采集和标注图像，再训练模型并开展测试。

### 项目摘要
本项目拟针对校园垃圾分类场景开发识别助手，通过图像识别辅助学生判断垃圾类别。项目计划开展需求分析、数据采集、模型训练及校园试用，具体效果有待实验验证。

请确认以上内容是否符合你的预期，如果有修改意见，请告诉我。
"""
PROJECT = {"state": {"skill_id": "innovation-research", "skill_category": "research"}, "outline": [], "sections": {}}


def test_project_sections_are_candidate_text_not_followup():
    result = plain_project_chapters(REPLY, USER, PROJECT)
    assert [title for title, _ in result] == ["研究目标", "项目摘要"]
    assert "图像识别" in result[0][1] and "有待实验验证" in result[1][1]
    assert "请确认" not in result[1][1]


@pytest.mark.parametrize(("user", "response"), [
    ("大创摘要应该怎么写？", REPLY),
    ("请写项目摘要", "下面是示例：\n" + REPLY),
    ("不要写项目摘要", REPLY),
    ("请写项目摘要", "### 项目摘要\n" + "这是没有完成的章节" * 6),
    ("请写项目摘要", "<WritingBlock>\n" + REPLY),
    ("请写项目摘要", "### 项目摘要\n" + "你可以根据自己的项目描述撰写，" * 4 + "再补充内容。"),
])
def test_question_examples_refusals_and_incomplete_answers_are_not_imported(user, response):
    assert plain_project_chapters(response, user, PROJECT) == []


def test_project_letter_fallback_does_not_apply_to_personal_skills():
    project = {**PROJECT, "state": {"skill_id": "national-scholarship", "skill_category": "scholarship"}}
    assert plain_project_chapters(REPLY, USER, project) == []


def test_previous_student_chapter_requires_explicit_replace():
    project = {**PROJECT, "outline": [{"id": "abstract", "title": "项目摘要"}],
               "sections": {"abstract": "学生此前手写的项目摘要。"}}
    result = candidates(project, [{"role": "user", "content": USER}, {"role": "assistant", "content": REPLY}])
    abstract = next(item for item in result if item["title"] == "项目摘要")
    assert abstract["section_id"] == "abstract" and abstract["conflict"]
    assert project["sections"]["abstract"] == "学生此前手写的项目摘要。"


def test_real_shaped_draft_can_be_previewed_saved_and_exported(tmp_path, monkeypatch):
    store = Store(tmp_path)
    pid = store.create_project(title="校园智能垃圾分类助手")["id"]
    store.update_project(pid, state=PROJECT["state"])
    store.add_message(pid, "user", USER)
    store.add_message(pid, "assistant", REPLY)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    with TestClient(app.app) as client:
        url = f"/api/projects/{pid}/chat-drafts"
        preview = client.get(url).json()
        assert len(preview["items"]) == 2
        assert store.get_project(pid)["sections"] == {}
        saved = client.post(url + "/confirm", json={"snapshot": preview["snapshot"],
            "items": [{"id": item["id"]} for item in preview["items"]]})
        assert saved.status_code == 200, saved.text
        exported = client.post(f"/api/projects/{pid}/export")
        assert exported.status_code == 200, exported.text
        file = client.get(exported.json()["download_url"])
        doc = Document(io.BytesIO(file.content))
        text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
        assert "图像识别" in text and "有待实验验证" in text and "请确认以上" not in text
