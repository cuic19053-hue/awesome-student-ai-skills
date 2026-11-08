"""Survey-specific numerical review for form fields and Markdown tables."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from proposal.social_survey_quality import unsupported_survey_table_counts


SKILL = {"id": "social-survey", "category": "practice"}
PROJECT = {"id": "p1", "state": {"skill_id": "social-survey"}}


def issues(content, history=None, documents=None, skill=SKILL, project=PROJECT):
    return unsupported_survey_table_counts(skill, project, history or [], documents or [], content)


@pytest.mark.parametrize("content", [
    "| 调查样本量 | 100 |\n| 访谈人数 | 10 |",
    "| 项目 | 样本量 | 访谈人数 |\n| --- | --- | --- |\n| 社区居民 | 100 | 10 |",
    "样本量：100\n访谈人数：10人",
    "| 样本量（人） | 100 |\n| 访谈人数（人） | 10 |",
])
def test_warns_for_unsupported_bare_counts_in_forms_and_tables(content):
    assert set(issues(content)) == {"调查样本数量", "访谈数量"}


def test_explicit_student_counts_suppress_only_the_corresponding_warning():
    generated = "| 样本量 | 100 |\n| 访谈人数 | 10 |\n| 问卷数量 | 120 |"
    history = [{"role": "user", "content": "我们计划调查100人，访谈10人。"}]
    assert issues(generated, history) == ["问卷数量"]


@pytest.mark.parametrize("input_text", [
    "是否调查100人？", "目前没有调查100人", "比如计划调查100人", "尚未确认计划调查100人",
    "样本量：100或200", "样本量：100？", "样本量：100.5",
])
def test_question_negation_example_uncertainty_and_noninteger_do_not_support_count(input_text):
    history = [{"role": "user", "content": input_text}]
    assert issues("| 样本量 | 100 |", history) == ["调查样本数量"]


def test_confirmed_same_project_material_supports_matching_count():
    doc = {"project_id": "p1", "kind": "source", "confirmed": True,
           "confirmation_origin": "user", "extracted_text": "样本量：100"}
    assert issues("| 样本量 | 100 |", documents=[doc]) == []
    for patch in ({"project_id": "other"}, {"confirmed": False}, {"confirmation_origin": ""},
                  {"kind": "template"}, {"kind": "official"}, {"low_confidence_count": 1},
                  {"extraction_warning": "仅提取部分内容"}):
        assert issues("| 样本量 | 100 |", documents=[{**doc, **patch}]) == ["调查样本数量"]


def test_conflicting_student_values_require_attention():
    history = [{"role": "user", "content": "样本量：100"}, {"role": "user", "content": "样本量：200"}]
    assert issues("样本量：100", history) == ["调查样本数量"]


def test_non_survey_is_not_affected_and_structure_numbers_do_not_trigger():
    assert issues("| 样本量 | 100 |", skill={"id": "innovation-research"},
                  project={"id": "p1", "state": {"skill_id": "innovation-research"}}) == []
    assert issues("## 第1阶段\n调研将分为3个环节。\n| 时间 | 工作 |\n| 1 | 联系社区 |") == []


def test_unsupported_coverage_and_chinese_numerals_are_detected():
    assert issues("| 覆盖社区数 | 三 |") == ["调研覆盖范围"]
    assert issues("| 覆盖社区数 | 3 |", [{"role": "user", "content": "覆盖社区数：三"}]) == []
