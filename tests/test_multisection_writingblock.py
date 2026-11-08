"""Safely recover peer chapters from one real-shaped WritingBlock."""
import io
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.chat_drafts import candidates
from proposal.storage import Store


USER = "请起草三下乡社会调查的调研背景和实施方案。"
BODY = (
    "## 一、调研背景\n\n该项目拟围绕校园学习需求开展调查。\n\n"
    "### 1.1 政策依据\n\n【待补充适用通知】\n\n"
    "### 1.2 调研价值\n\n了解学生使用学习工具的实际情况。\n\n"
    "## 二、实施方案\n\n拟通过问卷和访谈开展调研。\n\n"
    "### 2.1 实践时间\n\n【待补充】\n\n"
    "### 2.9 预期成果\n\n形成可供讨论的调研报告。"
)
FIRST_LEVEL_BODY = (
    "# 一、调研背景\n\n该项目拟围绕校园学习需求开展调查。\n\n"
    "## 1.1 政策依据\n\n【待补充适用通知】\n\n"
    "# 二、实施方案\n\n拟通过问卷和访谈开展调研。\n\n"
    "## 2.1 实践时间\n\n【待补充】\n\n"
    "## 2.9 预期成果\n\n形成可供讨论的调研报告。"
)


def block(body):
    return f'<WritingBlock variant="document">\n{body}\n</WritingBlock>'


def project(skill_id="social-survey", category="practice", outline=None):
    return {"state": {"skill_id": skill_id, "skill_category": category},
            "outline": outline or [], "sections": {}}


def preview(body, *, current=None):
    return candidates(current or project(), [{"role": "user", "content": USER},
                                              {"role": "assistant", "content": block(body)}])


def test_peer_chapters_split_and_preserve_real_shaped_subsections():
    result = preview(BODY)
    assert [item["title"] for item in result] == ["调研背景", "实施方案"]
    assert "### 1.1 政策依据" in result[0]["content"]
    assert "## 二、实施方案" not in result[0]["content"]
    assert "### 2.1 实践时间" in result[1]["content"]
    assert all(item["requires_review"] for item in result)


def test_first_level_peer_chapters_split_and_preserve_lower_levels():
    result = preview(FIRST_LEVEL_BODY)
    assert [item["title"] for item in result] == ["调研背景", "实施方案"]
    assert "## 1.1 政策依据" in result[0]["content"]
    assert "# 二、实施方案" not in result[0]["content"]
    assert "## 2.1 实践时间" in result[1]["content"]
    assert all(item["requires_review"] for item in result)


@pytest.mark.parametrize("text", [
    "# 调研背景\n\n已有背景。\n\n# 不认识的标题\n\n需要人工判断。",
    "# 调研背景\n\n第一版。\n\n# 调研背景\n\n另一版。",
    "# 调研背景\n\n背景内容。\n\n# 实施方案\n\n计划尚未完成……",
    "# 调研背景\n\n背景内容。\n\n# 实施方案\n\n",
    "# 调研背景\n\n```markdown\n# 实施方案\n尚未关闭",
    "# 调研背景\n\n背景内容。\n\n## 实施方案\n\n该标题是低一级标题。",
    "## 调研背景\n\n背景内容。\n\n# 其他标题\n\n层级不明确。\n\n## 实施方案\n\n拟开展调查。",
])
def test_first_level_unknown_duplicate_or_mixed_hierarchy_stays_together(text):
    result = preview(text)
    assert len(result) == 1 and result[0]["title"] == "调研背景"
    assert "# " in result[0]["content"]


def test_first_level_fenced_heading_remains_in_chapter():
    text = ("# 调研背景\n\n示意内容。\n\n```markdown\n# 市场分析\n代码内容\n```\n\n"
            "继续正文。\n\n# 实施方案\n\n拟开展调查。")
    result = preview(text)
    assert len(result) == 2 and "# 市场分析" in result[0]["content"]


def test_existing_outline_ids_are_used_without_overwriting():
    current = project(outline=[{"id": "background", "title": "调研背景"},
                               {"id": "plan", "title": "实施方案"}])
    current["sections"] = {"background": "学生已有正文"}
    result = preview(BODY, current=current)
    assert [item["section_id"] for item in result] == ["background", "plan"]
    assert result[0]["conflict"] and current["sections"]["background"] == "学生已有正文"


def test_fenced_code_heading_remains_inside_its_chapter():
    text = ("## 调研背景\n\n这里是示意代码和说明。\n\n```markdown\n## 市场分析\n示例代码\n```\n\n"
            "这段代码不是新章节。\n\n## 实施方案\n\n计划开展调查。")
    result = preview(text)
    assert len(result) == 2
    assert "## 市场分析" in result[0]["content"] and "```" in result[0]["content"]


def test_code_fence_with_info_string_does_not_close_fenced_code():
    text = ("## 调研背景\n\n示意代码。\n\n```text\n```not-a-close\n## 市场分析\n仍是代码\n```\n\n"
            "正文继续。\n\n## 实施方案\n\n计划开展调查。")
    result = preview(text)
    assert len(result) == 2 and result[1]["title"] == "实施方案"
    assert "## 市场分析" in result[0]["content"]


@pytest.mark.parametrize("text", [
    "## 调研背景\n\n已有背景。\n\n## 不认识的标题\n\n需要人工判断。",
    "## 调研背景\n\n第一版。\n\n## 调研背景\n\n另一版。",
    "## 调研背景\n\n背景内容。\n\n## 实施方案\n\n",
    "## 调研背景\n\n背景内容。\n\n## 实施方案\n\n计划尚未完成……",
    "## 调研背景\n\n```markdown\n## 实施方案\n尚未关闭",
])
def test_ambiguous_duplicate_empty_or_truncated_block_stays_together(text):
    result = preview(text)
    assert len(result) == 1 and result[0]["title"] == "调研背景"
    assert "## " in result[0]["content"]


def test_personal_statement_is_never_split():
    personal = project("graduate-recommendation", "other")
    result = preview("## 个人陈述\n\n本人学习情况如下。\n\n## 学习情况\n\n绩点待补充。", current=personal)
    assert len(result) == 1 and result[0]["title"] == "个人陈述"
    assert "## 学习情况" in result[0]["content"]
    result = preview("# 个人陈述\n\n本人学习情况如下。\n\n# 学习情况\n\n绩点待补充。", current=personal)
    assert len(result) == 1 and result[0]["title"] == "个人陈述"
    assert "# 学习情况" in result[0]["content"]


def test_do_not_expand_beyond_twenty_existing_chapters():
    outline = [{"id": f"section_{i}", "title": f"旧章节{i}"} for i in range(20)]
    result = preview(BODY, current=project(outline=outline))
    assert len(result) == 1 and "## 二、实施方案" in result[0]["content"]


@pytest.mark.parametrize("body", [BODY, FIRST_LEVEL_BODY], ids=["second-level", "first-level"])
def test_students_can_review_select_save_and_export_both_chapters(tmp_path, monkeypatch, body):
    store = Store(tmp_path)
    pid = store.create_project(title="校园调查")["id"]
    store.update_project(pid, state={"skill_id": "social-survey", "skill_category": "practice"})
    store.add_message(pid, "user", USER)
    store.add_message(pid, "assistant", block(body))
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    with TestClient(app.app) as client:
        url = f"/api/projects/{pid}/chat-drafts"
        review = client.get(url).json()
        assert [item["title"] for item in review["items"]] == ["调研背景", "实施方案"]
        response = client.post(url + "/confirm", json={"snapshot": review["snapshot"], "items": [
            {"id": item["id"]} for item in review["items"]
        ]})
        assert response.status_code == 200, response.text
        saved = store.get_project(pid)
        assert len(saved["outline"]) == 2 and len(saved["sections"]) == 2
        assert "实施方案" not in next(iter(saved["sections"].values()))
        exported = client.post(f"/api/projects/{pid}/export")
        assert exported.status_code == 200, exported.text
        word = client.get(exported.json()["download_url"])
        text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(word.content)).paragraphs)
        assert "调研背景" in text and "实施方案" in text and "形成可供讨论的调研报告" in text


def test_real_internet_plus_reply_is_reviewable_as_two_chapters_and_edited_word(tmp_path, monkeypatch):
    # The fixture is an actual model reply, replayed without another model call.
    # Its technical, partnership and commercial claims are not established by
    # this test; simulate the student editing them before saving the draft.
    fixture = (Path(__file__).parent / "fixtures" / "internet_plus_quality_retest.txt").read_text()
    store = Store(tmp_path)
    pid = store.create_project(title="校园闲置物品交换")['id']
    store.update_project(pid, state={"skill_id": "internet-plus", "skill_category": "competition"})
    store.add_message(pid, "user", "请为校园闲置物品交换平台写项目简介和商业模式草稿。")
    store.add_message(pid, "assistant", fixture)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    with TestClient(app.app) as client:
        url = f"/api/projects/{pid}/chat-drafts"
        review = client.get(url).json()
        assert [item["title"] for item in review["items"]] == ["项目简介", "商业模式"]
        assert all(item["requires_review"] for item in review["items"])
        assert "LBS定位技术" in review["items"][0]["content"]
        assert "## 收入来源" in review["items"][1]["content"]
        assert "# 商业模式" not in review["items"][0]["content"]
        edited = [
            "本项目计划探索校园闲置物品交换，目前处于创意阶段。具体产品方案与目标用户需求待进一步确认。",
            "## 收入来源\n\n收费方式尚待确定。\n\n## 成本结构\n\n成本项目和预算待进一步测算。",
        ]
        response = client.post(url + "/confirm", json={"snapshot": review["snapshot"], "items": [
            {"id": item["id"], "content": text} for item, text in zip(review["items"], edited)
        ]})
        assert response.status_code == 200, response.text
        saved = store.get_project(pid)
        assert [item["title"] for item in saved["outline"]] == ["项目简介", "商业模式"]
        assert [saved["sections"][item["id"]] for item in saved["outline"]] == edited
        exported = client.post(f"/api/projects/{pid}/export")
        assert exported.status_code == 200, exported.text
        word = client.get(exported.json()["download_url"])
        text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(word.content)).paragraphs)
        assert "项目简介" in text and "商业模式" in text
        assert "校园闲置物品交换" in text and "收费方式尚待确定" in text
        assert "LBS" not in text and "广告公司" not in text and "确保交易双方的安全" not in text


def test_new_chat_draft_cannot_push_directory_beyond_twenty(tmp_path, monkeypatch):
    store = Store(tmp_path)
    pid = store.create_project(title="已满的目录")["id"]
    outline = [{"id": f"section_{i}", "title": f"旧章节{i}"} for i in range(20)]
    store.update_project(pid, state={"skill_id": "social-survey", "skill_category": "practice"}, outline=outline)
    store.add_message(pid, "user", USER)
    store.add_message(pid, "assistant", block(BODY))
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    with TestClient(app.app) as client:
        url = f"/api/projects/{pid}/chat-drafts"
        review = client.get(url).json()
        assert len(review["items"]) == 1
        result = client.post(url + "/confirm", json={"snapshot": review["snapshot"], "items": [
            {"id": review["items"][0]["id"]},
        ]})
        assert result.status_code == 422 and "最多支持 20 个章节" in result.text
        assert store.get_project(pid)["outline"] == outline and store.get_project(pid)["sections"] == {}
