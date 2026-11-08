"""Project claims: direct contradictions, not a general fact checker."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from proposal.project_contradictions import project_fact_contradictions


SKILL = {"id": "internet-plus", "category": "competition"}
PROJECT = {"id": "project-one", "state": {"confirmed_facts": {}}}


def check(history, content, *, project=PROJECT, documents=None, skill=SKILL):
    return project_fact_contradictions(skill, project, history, documents or [], content)


@pytest.mark.parametrize(("user_text", "output", "expected"), [
    ("目前没有营收。", "项目已经实现营收，经营情况良好。", "营收"),
    ("我们还没有开展市场调研。", "团队已经完成市场调研。", "市场调研"),
    ("目前尚未搭建原型。", "团队已完成原型制作。", "原型"),
    ("我们没有申请专利。", "项目已获得专利授权。", "专利"),
    ("尚未开展任何实验。", "实验结果表明系统可行。", "实验或测试"),
])
def test_direct_contradiction_is_flagged(user_text, output, expected):
    assert expected in check([{"role": "user", "content": user_text}], output)


@pytest.mark.parametrize("output", [
    "项目目前没有营收。", "我们计划开展市场调研。", "建议后续搭建原型。",
    "未来拟申请专利。", "下一阶段将开展实验。", "若后续完成测试，可进一步总结结果。",
])
def test_absence_and_future_plans_are_not_treated_as_completed(output):
    history = [{"role": "user", "content": "没有营收，没有市场调研，没有原型，没有专利，也没有做实验。"}]
    assert check(history, output) == []


def test_later_user_correction_replaces_previous_absence():
    history = [{"role": "user", "content": "我目前没有原型，也没有开展实验。"},
               {"role": "user", "content": "更正，团队已经完成原型，仍然没有做实验。"}]
    assert check(history, "项目已经完成原型制作，并已开展实验。") == ["实验或测试"]


def test_example_question_other_people_and_model_messages_are_not_student_facts():
    history = [{"role": "user", "content": "例如：我们没有原型。"},
               {"role": "user", "content": "是不是没有做实验？"},
               {"role": "assistant", "content": "你们没有专利。"}]
    assert check(history, "团队已完成原型，已开展实验，已获得专利。") == []


def test_only_confirmed_same_project_source_can_supply_initial_absence():
    good = {"project_id": "project-one", "kind": "source", "confirmed": 1,
            "confirmation_origin": "user", "extracted_text": "当前尚未开展实验。"}
    output = "项目已经完成实验。"
    assert check([], output, documents=[good]) == ["实验或测试"]
    for change in ({"project_id": "other"}, {"kind": "template"}, {"confirmed": 0},
                   {"confirmation_origin": ""}, {"low_confidence_count": 1}):
        assert check([], output, documents=[{**good, **change}]) == []


def test_confirmed_facts_and_other_categories():
    project = {"id": "project-one", "state": {"confirmed_facts": {"has_prototype": False}}}
    assert check([], "团队已完成原型制作。", project=project) == ["原型"]
    assert check([{"role": "user", "content": "没有原型"}], "我们已完成原型。",
                 skill={"id": "national-scholarship", "category": "scholarship"}) == []


def test_affirmative_and_denial_in_separate_clauses_do_not_hide_other_topics():
    history = [{"role": "user", "content": "还没有开展实验，但已经申请了专利。"}]
    assert check(history, "团队已完成测试，已获得专利。") == ["实验或测试"]


def test_simulated_experiment_is_not_mistaken_for_future_tense():
    history = [{"role": "user", "content": "目前尚未做任何实验。"}]
    assert check(history, "团队已经开展了模拟实验。") == ["实验或测试"]
    assert check(history, "团队拟开展模拟实验。") == []


@pytest.mark.parametrize("output", ["团队已经完成实验方案。", "团队已完成市场调研计划。",
                                   "团队已经完成原型设计。", "团队已经制定专利申请计划。"])
def test_a_finished_plan_does_not_imply_the_work_was_done(output):
    history = [{"role": "user", "content": "没有实验，也没有市场调研、原型和专利。"}]
    assert check(history, output) == []


def test_example_in_one_sentence_does_not_hide_later_actual_statement():
    history = [{"role": "user", "content": "例如某些企业已盈利。我们的项目目前没有营收。"}]
    assert check(history, "例如部分竞品已有用户。我们已经实现营收。") == ["营收"]
    assert check([{"role": "user", "content": "例如，我们目前没有营收。"}], "我们已经实现营收。") == []


def test_later_future_plan_does_not_erase_a_completed_claim():
    history = [{"role": "user", "content": "我们目前还没有申请专利。"}]
    assert check(history, "团队已拥有专利并计划后续推广。") == ["专利"]
    assert check(history, "团队计划后续申请专利并推广。") == []
