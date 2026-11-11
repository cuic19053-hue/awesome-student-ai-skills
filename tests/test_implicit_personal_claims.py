"""Generated applications need checks even when prose omits 'I'."""
from __future__ import annotations

import pytest

import server.app
from proposal.personal_claims import unsupported_personal_numbers
from proposal.skills import registry


def check(text, history=(), facts=None):
    return unsupported_personal_numbers(
        registry.get("national-scholarship"),
        {"id": "p", "state": {"confirmed_facts": facts or {}}},
        list(history), [], text,
    )


@pytest.mark.parametrize("text", [
    "绩点3.9，志愿服务300小时。",
    "| 绩点 | 志愿服务时长 |\n| --- | --- |\n| 3.9 | 300小时 |",
    "| 项目 | 内容 |\n| --- | --- |\n| GPA | 3.9 |\n| 志愿服务 | 300小时 |",
])
def test_subjectless_prose_and_tables_cannot_hide_invented_figures(text):
    assert check(text) == ["绩点", "志愿服务时长"]


@pytest.mark.parametrize("text", [
    "专业排名1/100。", "本人排名第1名。", "专业排名前1%。",
    "| 专业排名 |\n| --- |\n| 1/100 |",
])
def test_rank_claims_need_the_students_evidence(text):
    assert check(text) == ["排名"]


def test_original_reproduction_also_checks_an_explicit_award_claim():
    assert check("本人专业排名1/100，获得国家级竞赛一等奖。") == ["排名", "获奖经历"]


@pytest.mark.parametrize("text", [
    "评审通知提到志愿服务时长100小时。",
    "申请条件要求绩点3.9，排名前1%。",
    "例如绩点3.9，志愿服务300小时。",
    "朋友的专业排名1/100。",
    "【待补充：例如绩点3.9，排名1/100】",
    "我希望获得国家奖学金。",
    "学校要求\n| 绩点 | 志愿服务时长 |\n| --- | --- |\n| 3.9 | 300小时 |",
])
def test_policy_examples_other_people_and_future_aspirations_are_not_claims(text):
    assert check(text) == []


def test_confirmed_values_can_support_implicit_prose():
    assert check("绩点3.9，专业排名1/100，志愿服务300小时。", facts={
        "gpa": "3.9", "rank": "1/100", "volunteer_hours": "300",
    }) == []


def test_rank_denominator_cannot_be_changed_and_a_supplied_rank_supports_ordinal():
    assert check("专业排名1/100。", facts={"rank": "1/80"}) == ["排名"]
    assert check("专业排名第1名。", facts={"rank": "1/80"}) == []


def test_model_history_cannot_prove_rank_awards_or_hours():
    history = [{"role": "assistant", "content": "我排名1/100，获得国家级竞赛一等奖，志愿服务300小时。"}]
    assert check("专业排名1/100，获得国家级竞赛一等奖，志愿服务300小时。", history) == [
        "志愿服务时长", "排名", "获奖经历",
    ]


def test_clear_user_self_report_supports_its_following_profile_table():
    history = [{"role": "user", "content": "我叫李明。\n| 项目 | 内容 |\n| --- | --- |\n| 专业排名 | 1/100 |\n| 志愿服务 | 300小时 |"}]
    assert check("专业排名1/100，志愿服务300小时。", history) == []


def test_user_award_and_later_rank_correction_are_respected():
    history = [
        {"role": "user", "content": "我排名1/100，获得国家级竞赛一等奖。"},
        {"role": "user", "content": "我的排名更正为3/100。"},
    ]
    assert check("本人排名1/100，获得国家级竞赛一等奖。", history) == ["排名"]
    assert check("本人排名3/100，获得国家级竞赛一等奖。", history) == []


@pytest.mark.parametrize("text", [
    "我叫李明。以下是班里张三的资料。\n| 姓名 | 专业排名 | 志愿服务 |\n| --- | --- | --- |\n| 张三 | 1/80 | 300小时 |",
    "我叫李明。\n| 姓名 | 专业排名 | 志愿服务 |\n| --- | --- | --- |\n| 李明 | 3/80 | 10小时 |\n| 张三 | 1/80 | 300小时 |",
    "我叫李明。辅导员说张三专业排名1/80，志愿服务300小时。",
    "我叫李明，张三专业排名1/80，志愿服务300小时。",
    "我听说张三专业排名1/80，志愿服务300小时。",
])
def test_one_self_introduction_does_not_authorize_other_people_or_mixed_tables(text):
    assert check("本人专业排名1/80，志愿服务300小时。", [
        {"role": "user", "content": text},
    ], facts={"applicant_name": "李明"}) == ["志愿服务时长", "排名"]


def test_single_person_matching_table_can_support_claims():
    text = "我的资料：\n| 姓名 | 专业排名 | 志愿服务 |\n| --- | --- | --- |\n| 李明 | 1/80 | 300小时 |"
    assert check("本人排名1/80，志愿服务300小时。", [{"role": "user", "content": text}],
                 facts={"applicant_name": "李明"}) == []


def test_owned_table_gpa_and_explicit_gpa_correction():
    text = "我的资料：\n| 姓名 | GPA |\n| --- | --- |\n| 李明 | 3.9/4.0 |"
    history = [{"role": "user", "content": text}]
    assert check("绩点3.9，满分4.0。", history, facts={"applicant_name": "李明"}) == []
    history.append({"role": "user", "content": "我的绩点更正为3.7。"})
    assert check("绩点3.9。", history, facts={"applicant_name": "李明"}) == ["绩点"]


def test_school_requirement_in_users_message_is_not_student_evidence():
    history = [{"role": "user", "content": "我叫李明。我的学校要求绩点3.9，排名前1%。"}]
    assert check("本人绩点3.9，排名前1%。", history) == ["绩点", "排名"]


def test_old_chat_figures_cannot_override_the_current_confirmed_profile():
    history = [{"role": "user", "content": "我叫李明，我的绩点3.9，排名1/80。"}]
    assert check("本人绩点3.9，排名1/80。", history, facts={"gpa": "3.7", "rank": "3/80"}) == ["绩点", "排名"]
