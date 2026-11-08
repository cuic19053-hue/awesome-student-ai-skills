"""Partial popular-track drafts must not be reported as complete."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    store = Store(tmp_path)
    tools = ProposalTools(store)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    with TestClient(app.app) as client:
        yield client, store, tools


def _project(store, skill, rows):
    project_id = store.create_project()["id"]
    facts = {"problem": "灌溉费时", "target_user": "农户", "method": "湿度监测", "foundation": "现有项目记录"}
    state = {"skill_id": skill, "outline_confirmed": True, "confirmed_facts": facts}
    return store.update_project(project_id, state=state,
        outline=[{"id": key, "title": title} for key, title, _ in rows],
        sections={key: body for key, _, body in rows})


def test_partial_social_survey_can_export_but_never_claims_complete(workspace):
    client, store, _ = workspace
    project = _project(store, "social-survey", [
        ("background", "调研背景", "本次社会调查拟围绕社区垃圾分类展开，了解居民需求。"),
        ("method", "调研方法", "团队计划结合访谈与问卷收集居民意见，再整理资料。"),
        ("safety", "安全保障", "团队将了解当地天气和交通情况，建立紧急联系机制。"),
    ])
    response = client.post(f"/api/projects/{project['id']}/export")
    assert response.status_code == 200
    data = response.json()
    validation = data["validation"]
    assert validation["passed"] is False
    warnings = "".join(validation["consistency_warnings"])
    assert "实施计划" in warnings and "团队分工" in warnings
    assert "通用内容提示" in warnings and "学校通知和模板" in warnings
    assert "正式标准" in validation["validation_scope"]
    downloaded = client.get(data["download_url"])
    assert downloaded.status_code == 200
    assert "垃圾分类" in "\n".join(p.text for p in Document(io.BytesIO(downloaded.content)).paragraphs)


@pytest.mark.parametrize(("skill", "rows", "missing"), [
    ("internet-plus", [("intro", "项目概述", "项目计划通过湿度监测为农户提供灌溉提示，方案需要继续完善。")], "运营或商业模式"),
    ("internet-plus-red-tour", [("intro", "项目概述", "团队计划在当地开展志愿服务，具体内容还需继续商讨。")], "服务地区与需求"),
    ("challenge-cup", [("background", "研究背景", "本研究拟分析大学生使用人工智能工具时的学习习惯。")], "研究设计或制作方法"),
    ("innovation-research", [("background", "研究背景", "项目拟研究农田灌溉中信息不足的问题并设计合适的方案。")], "实施计划"),
    ("graduate-recommendation", [("profile", "个人学习情况", "大学期间我认真学习专业课程，并逐步了解相关领域。")], "申请动机与匹配"),
])
def test_short_incomplete_outline_does_not_pass_for_popular_tracks(workspace, skill, rows, missing):
    _, store, tools = workspace
    project = _project(store, skill, rows)
    result = tools.validate_project(project["id"])
    assert result["passed"] is False
    assert missing in "".join(result["consistency_warnings"])


def test_combined_school_style_section_is_supported_without_exact_headings(workspace):
    _, store, tools = workspace
    project = _project(store, "social-survey", [("combined", "学校表格综合说明",
        "调研目标是了解垃圾分类习惯，调研对象为社区居民。调研方法采用问卷和访谈。"
        "实施计划分为准备、走访和整理三个阶段。团队分工由成员分别负责沟通和记录。"
        "安全保障包括天气核对、行程报备和紧急联络。")])
    result = tools.validate_project(project["id"])
    assert result["passed"] is True
    assert "不代表学校正式标准" in result["validation_scope"]


def test_heading_or_placeholder_alone_does_not_count_as_content(workspace):
    _, store, tools = workspace
    project = _project(store, "social-survey", [("plan", "实施计划和团队分工", "【实施计划待补充】")])
    result = tools.validate_project(project["id"])
    assert result["passed"] is False
    assert "实施计划" in "".join(result["consistency_warnings"])


def test_no_outline_is_not_a_passing_empty_project(workspace):
    _, store, tools = workspace
    project_id = store.create_project()["id"]
    result = tools.validate_project(project_id)
    assert not result["passed"] and "没有已保存" in "".join(result["consistency_warnings"])


def test_unplanned_schedule_and_team_are_not_counted_as_completed(workspace):
    _, store, tools = workspace
    project = _project(store, "social-survey", [
        ("objectives", "调研目标与对象", "调研目标是了解居民的垃圾分类习惯，调查对象为社区居民。"),
        ("method", "调研方法", "团队计划通过问卷和访谈收集居民的想法，并整理反馈。"),
        ("schedule", "实施计划与日程", "项目实施计划尚未制定，目前只有初步想法，具体日程以后再讨论。"),
        ("team", "团队分工", "目前没有确定团队分工，成员职责需要进一步讨论，具体安排待定。"),
        ("safety", "安全保障", "出发前检查天气和交通信息，并建立团队紧急联络机制。"),
    ])
    result = tools.validate_project(project["id"])
    assert result["passed"] is False
    warning = "".join(result["consistency_warnings"])
    assert "实施计划或日程" in warning and "团队分工" in warning
    assert "通用内容提示" in warning and "学校通知和模板" in warning


def test_negated_topics_inside_combined_school_section_are_not_counted(workspace):
    _, store, tools = workspace
    project = _project(store, "social-survey", [("combined", "学校表格综合说明",
        "调研目标是了解垃圾分类习惯，调研对象为社区居民。调研方法采用问卷和访谈。"
        "实施计划尚未制定，以后再讨论具体日程。团队分工还没有安排，成员职责仍需商量。"
        "安全保障包括天气核对、行程报备和紧急联络。")])
    result = tools.validate_project(project["id"])
    warning = "".join(result["consistency_warnings"])
    assert result["passed"] is False
    assert "实施计划或日程" in warning and "团队分工" in warning


def test_clear_future_schedule_and_roles_count_despite_unfixed_details(workspace):
    _, store, tools = workspace
    project = _project(store, "social-survey", [
        ("objectives", "调研目标与对象", "调研目标是了解居民的垃圾分类习惯，调查对象为社区居民。"),
        ("method", "调研方法", "尚未开展走访，计划采用问卷和访谈收集居民意见。"),
        ("schedule", "实施计划与日程", "活动具体日期尚未确定，计划第一周联系社区，第二周访谈居民，第三周整理记录。"),
        ("team", "团队分工", "团队分工尚未正式确定，但拟由组长负责社区沟通，成员分别负责问卷和记录。"),
        ("safety", "安全保障", "出发前检查天气和交通信息，并建立团队紧急联络机制。"),
    ])
    result = tools.validate_project(project["id"])
    assert result["passed"] is True
    assert "不代表学校正式标准" in result["validation_scope"]


@pytest.mark.parametrize(("skill", "title", "text", "missing"), [
    ("challenge-cup", "已有工作与成果", "目前尚未形成任何研究结果，项目成果需要之后再讨论。", "进展、结果或后续计划"),
    ("internet-plus", "市场与用户分析", "目前还没有确定目标用户，客户需求尚未明确，需要进一步调研。", "目标用户与需求"),
    ("graduate-recommendation", "申请动机与专业匹配", "目前申请动机尚未明确，后续将继续研究适合自己的目标方向。", "申请动机与匹配"),
])
def test_negated_topic_does_not_complete_other_popular_tracks(workspace, skill, title, text, missing):
    _, store, tools = workspace
    project = _project(store, skill, [("part", title, text)])
    result = tools.validate_project(project["id"])
    assert not result["passed"]
    assert missing in "".join(result["consistency_warnings"])


def test_unpunctuated_future_plan_is_not_mistaken_for_a_missing_method(workspace):
    from proposal.completeness import draft_content_suggestions
    _, store, _ = workspace
    project = _project(store, "social-survey", [("method", "调研方法",
        "目前尚未开展具体实验计划使用问卷和访谈收集居民对分类方式的意见。")])
    assert "调研方法" not in draft_content_suggestions(project)
