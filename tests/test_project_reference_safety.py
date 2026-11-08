"""Unprovided years and attributed documents are flagged, not fact-checked."""
import json
from pathlib import Path

import pytest

from server.proposal.project_reference_safety import unsupported_project_references

SKILL = {"id": "social-survey", "category": "practice"}
PROJECT = {"id": "p1", "state": {"confirmed_facts": {}}}


def check(content, history=(), documents=(), project=PROJECT, skill=SKILL):
    return unsupported_project_references(skill, project, list(history), list(documents), content)


def test_real_survey_retest_requires_reference_review():
    case = json.loads((Path(__file__).parent / "fixtures" / "social_survey_retest_regression.json").read_text())
    issues = check(case["assistant"], [{"role": "user", "content": case["user"]}])
    assert "年份与时间" in issues
    assert "政策与报告名称" in issues


def test_first_real_survey_output_invents_unspecified_calendar_days():
    case = json.loads((Path(__file__).parent / "fixtures" / "social_survey_model_regression.json").read_text())
    assert "年份与时间" in check(case["assistant"], [{"role": "user", "content": case["user"]}])


def test_matching_user_information_removes_review_without_claiming_it_is_true():
    source = "活动计划在2027年开展，依据《关于生活垃圾分类工作的通知》；根据 XX 县环保局 2021 年的调研报告安排。"
    output = "计划于2027年启动。依据《关于生活垃圾分类工作的通知》，根据 XX 县环保局 2021 年的调研报告制定方案。"
    assert check(output, [{"role": "user", "content": source}]) == []


def test_only_mismatched_year_needs_review_when_reference_is_provided():
    source = "依据《关于生活垃圾分类工作的通知》，项目在2027年开展。"
    assert check("根据《关于生活垃圾分类工作的通知》，2024年启动项目。",
                 [{"role": "user", "content": source}]) == ["年份与时间"]


def test_unsupported_document_is_flagged_even_when_year_is_provided():
    history = [{"role": "user", "content": "本项目2026年开展。"}]
    assert check("2026年依据《关于加强校园管理的通知》开展。", history) == ["政策与报告名称"]
    assert check("根据 XX 县环保局的调研报告，该社区居民参与度很高。", history) == ["政策与报告名称"]


def test_confirmed_current_project_source_or_official_notice_can_supply_reference():
    doc = {"project_id": "p1", "kind": "official", "confirmed": True, "confirmation_origin": "user",
           "extracted_text": "2024年《关于推动校园垃圾分类的指导意见》"}
    output = "依据2024年《关于推动校园垃圾分类的指导意见》开展调研。"
    assert not check(output, documents=[doc])
    for change in ({"project_id": "other"}, {"confirmed": False}, {"confirmation_origin": ""},
                   {"kind": "template"}, {"extraction_warning": "第 2 页未能识别文字"}):
        altered = {**doc, **change}
        assert set(check(output, documents=[altered])) == {"年份与时间", "政策与报告名称"}


def test_prior_assistant_claim_is_not_a_source():
    reply = "2024年依据《关于推动校园垃圾分类的通知》开展。"
    assert set(check(reply, [{"role": "assistant", "content": reply}])) == {"年份与时间", "政策与报告名称"}


@pytest.mark.parametrize("source", [
    "请不要引用2024年《某项通知》。",
    "例如2024年《关于垃圾分类工作的通知》只是范文，不是我的材料。",
])
def test_denials_and_examples_are_not_evidence(source):
    output = "2024年根据《关于垃圾分类工作的通知》开展。"
    assert set(check(output, [{"role": "user", "content": source}])) == {"年份与时间", "政策与报告名称"}


@pytest.mark.parametrize("source", [
    "2023年政策是真的吗？是否有《某项通知》？",
    "2023年政策是不是真的？有没有《某项通知》？",
    "2023年政策是真的吗，是否有《某项通知》？",
])
def test_questions_do_not_make_dates_or_notices_factual(source):
    output = "2023年根据《某项通知》开展。"
    assert set(check(output, [{"role": "user", "content": source}])) == {"年份与时间", "政策与报告名称"}


def test_question_does_not_erase_a_separate_positive_fact():
    source = "项目将在2023年启动，是否有《某项通知》？"
    assert check("2023年根据《某项通知》开展。", [{"role": "user", "content": source}]) == ["政策与报告名称"]


def test_unattributed_project_titles_are_not_mistaken_for_official_reports():
    assert not check("本项目名称为《社区垃圾分类社会调查报告》，将形成《校园项目可行性报告》。")
    assert check("根据《社区垃圾分类社会调查报告》，当地参与率较高。") == ["政策与报告名称"]


def test_confirmed_facts_can_include_year_or_document_name():
    project = {"id": "p1", "state": {"confirmed_facts": {"application_year": "2027", "policy": "《相关工作通知》"}}}
    assert not check("2027年根据《相关工作通知》实施。", project=project)


def test_unrelated_personal_category_is_not_subject_to_this_project_guard():
    assert not check("2025年根据《某项通知》申请。", skill={"category": "scholarship"})
