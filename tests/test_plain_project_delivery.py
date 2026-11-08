"""Model replies without special tags can still become reviewed Word drafts."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.chat_drafts import candidates, plain_project_chapters
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools


USER = "我们准备三下乡调研社区垃圾分类，请帮我写调研背景和实施方案。"
REPLY = """好的，以下是根据你的主题整理的初稿。

## 调研背景
### 调研问题
团队拟了解居民在日常垃圾分类中遇到的问题，并在实际调查后再分析原因。
### 调研价值
调研有助于团队理解社区实际需求，具体问题和情况以调查结果为准。

## 实施方案
### 日程安排
具体时间待补充，例如可先与社区沟通，再根据实际条件安排走访。

| 阶段 | 计划内容 |
| --- | --- |
| 准备阶段 | 确认问卷内容与实践时间 |
| 调研阶段 | 根据现场情况开展调查 |
"""
PROJECT = {"state": {"skill_id": "social-survey", "skill_category": "practice"}, "outline": [], "sections": {}}


def test_plain_nested_sections_and_table_are_recoverable_for_review():
    result = plain_project_chapters(REPLY, USER, PROJECT)
    assert [title for title, _ in result] == ["调研背景", "实施方案"]
    assert "### 调研问题" in result[0][1] and "### 调研价值" in result[0][1]
    assert "| 调研阶段 |" in result[1][1]
    items = candidates(PROJECT, [{"role": "user", "content": USER}, {"role": "assistant", "content": REPLY}])
    assert all(item["requires_review"] for item in items)
    assert any("举例" in warning for warning in items[1]["warnings"])


def test_single_level_headings_and_matching_custom_outline_are_recovered():
    project = {**PROJECT, "outline": [{"id": "value", "title": "项目意义"}]}
    raw = ("# 项目意义\n为社区垃圾分类了解居民需求，实地情况和最终结论需要在调查完成后整理。\n"
           "# 实施方案\n调查实施时间和参与对象仍需补充，计划先了解社区情况并准备问卷。")
    assert [title for title, _ in plain_project_chapters(raw, USER, project)] == ["项目意义", "实施方案"]


@pytest.mark.parametrize("raw", [
    "以下是示例：\n" + REPLY,
    "## 调研背景\n以下为范文：" + "这是一段不应作为学生资料的示例正文。" * 4,
    "## 调研背景\n" + "正文内容。" * 10 + "\n### 示范案例\n不属于本项目的例子。",
    "## 调研背景\n" + "正文内容。" * 10 + "\n| 标题 | 值 |\n| 未完成 |",
    "# 示例文书\n## 调研背景\n" + "正文内容。" * 10,
    "## 调研背景\n| 标题 | 值 |\n| --- | --- |\n| 一 | 二 |\n尚未写完",
])
def test_examples_and_incomplete_tables_do_not_silently_become_drafts(raw):
    assert not plain_project_chapters(raw, USER, PROJECT)


def test_student_can_edit_save_and_export_unmarked_model_response(tmp_path, monkeypatch):
    store = Store(tmp_path)
    pid = store.create_project(title="垃圾分类调研")["id"]
    store.update_project(pid, state=PROJECT["state"])
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    calls = []
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: calls.append(1) or {"message": {"content": REPLY}})
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    with TestClient(app.app) as client:
        chat = client.post(f"/api/projects/{pid}/chat", json={"message": USER})
        assert chat.status_code == 200, chat.text
        assert calls == [1]
        url = f"/api/projects/{pid}/chat-drafts"
        review = client.get(url).json()
        assert [item["title"] for item in review["items"]] == ["调研背景", "实施方案"]
        selections = [{"id": item["id"], "content": item["content"].replace("例如可先", "计划先")}
                      for item in review["items"]]
        confirmed = client.post(url + "/confirm", json={"snapshot": review["snapshot"], "items": selections})
        assert confirmed.status_code == 200, confirmed.text
        exported = client.post(f"/api/projects/{pid}/export")
        assert exported.status_code == 200, exported.text
        content = client.get(exported.json()["download_url"])
        assert content.status_code == 200
        word = Document(io.BytesIO(content.content))
        text = "\n".join(p.text for p in word.paragraphs)
        table_text = "\n".join(cell.text for table in word.tables for row in table.rows for cell in row.cells)
        assert "调研问题" in text and "计划先" in text
        assert "调研阶段" in table_text and "例如可先" not in text
