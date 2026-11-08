"""Quantified project checks; this does not attempt general fact verification."""
from pathlib import Path

import pytest

from server.proposal.project_claims import unsupported_project_numbers


SKILL = {"id": "internet-plus", "category": "competition"}
PROJECT = {"id": "project-a", "state": {"confirmed_facts": {}}}


def check(content, history=(), documents=(), *, project=PROJECT, skill=SKILL):
    return unsupported_project_numbers(skill, project, list(history), list(documents), content)


def test_actual_ollama_response_with_invented_business_numbers_is_flagged():
    response = (Path(__file__).parent / "fixtures/internet_plus_model_regression.txt").read_text()
    history = [{"role": "user", "content": "项目叫智灌助手，团队三位同学，尚未开展市场调查、没有营业收入，也没有申请专利。"}]
    assert set(check(response, history)) == {"市场数据", "价格", "融资与股权"}


@pytest.mark.parametrize("text", [
    "市场规模是不是5000亿元？", "市场规模可能为5000亿元。", "市场规模预计5000亿元。",
    "例如市场规模5000亿元。", "我没有做市场调研，市场规模5000亿元吗？",
])
def test_questions_examples_and_uncertain_figures_do_not_authorize_claims(text):
    assert check("市场规模为5000亿元。", [{"role": "user", "content": text}]) == ["市场数据"]


def test_explicit_matching_figure_can_be_used_without_cross_category_confusion():
    history = [{"role": "user", "content": "市场规模是5000亿元。计划融资50万元。"}]
    assert not check("市场规模5000亿元，计划融资50万元。", history)
    assert check("定价50万元。", history) == ["价格"]
    assert check("市场规模50万元。", history) == ["市场数据"]


def test_matching_only_one_of_two_conflicting_figures_still_requires_review():
    history = [{"role": "user", "content": "市场规模5000亿元。"},
               {"role": "user", "content": "市场规模100亿元。"}]
    assert check("市场规模5000亿元。", history) == ["市场数据"]


def test_other_assistant_and_unconfirmed_or_wrong_project_materials_are_not_evidence():
    history = [{"role": "assistant", "content": "市场规模5000亿元。"}]
    doc = {"project_id": "project-a", "kind": "source", "confirmed": False,
           "confirmation_origin": "user", "extracted_text": "市场规模5000亿元。"}
    assert check("市场规模5000亿元。", history, [doc]) == ["市场数据"]
    doc["confirmed"] = True
    doc["project_id"] = "other-project"
    assert check("市场规模5000亿元。", history, [doc]) == ["市场数据"]
    doc["project_id"] = "project-a"
    doc["extraction_warning"] = "第 2 页未能识别文字"
    assert check("市场规模5000亿元。", history, [doc]) == ["市场数据"]
    doc["extraction_warning"] = ""
    assert not check("市场规模5000亿元。", history, [doc])


def test_other_measurements_and_categories_do_not_claim_support():
    history = [{"role": "user", "content": "团队共有50人。"}]
    assert check("定价50元。", history) == ["价格"]
    assert check("5000亿元市场规模。", history) == ["市场数据"]
    assert check("面向5000亿元农业市场。", history) == ["市场数据"]
    assert check("已有500名用户。", history) == ["用户与客户"]
    assert not check("市场规模5000亿元。", history, skill={"category": "scholarship"})


def test_no_model_generated_figures_does_not_trigger():
    assert not check("面向农户探索土壤湿度监测，市场规模【待补充】。")


def test_actual_social_survey_model_output_requires_review():
    import json
    case = json.loads((Path(__file__).parent / "fixtures/social_survey_model_regression.json").read_text())
    history = [{"role": "user", "content": case["user"]}]
    found = set(check(case["assistant"], history, skill={"id": "social-survey", "category": "practice"}))
    assert {"调研覆盖范围", "问卷数量", "访谈数量", "宣讲场次"} <= found


@pytest.mark.parametrize(("content", "expected"), [
    ("计划走访5个行政村。", "调研覆盖范围"),
    ("拟发放问卷100份。", "问卷数量"),
    ("访谈记录11份。", "访谈数量"),
    ("举行政策宣讲1场。", "宣讲场次"),
    ("拟采集100份问卷。", "问卷数量"),
])
def test_survey_quantities_without_explicit_sources_require_review(content, expected):
    assert expected in check(content, [{"role": "user", "content": "尚未实地调查或发放问卷。"}],
                             skill={"category": "practice"})


def test_survey_values_are_scoped_to_the_correct_topic():
    skill = {"category": "practice"}
    history = [{"role": "user", "content": "计划发放问卷100份。计划走访5个行政村。"}]
    assert not check("预计发放问卷100份，走访5个行政村。", history, skill=skill)
    assert "访谈数量" in check("预计收集访谈记录100份。", history, skill=skill)
    assert "问卷数量" in check("预计发放问卷5份。", history, skill=skill)
    assert not check("该项目计划调研社区垃圾分类，具体安排待补充。", history, skill=skill)


@pytest.mark.parametrize(("claim", "expected"), [
    ("计划走访五个行政村。", "调研覆盖范围"),
    ("拟发放问卷一百份。", "问卷数量"),
    ("访谈记录十一份。", "访谈数量"),
    ("举行政策宣讲一场。", "宣讲场次"),
    ("问卷覆盖率为百分之六十。", "效果与统计比例"),
    ("调查显示，百分之六十的人支持垃圾分类。", "效果与统计比例"),
    ("市场规模三点五亿元。", "市场数据"),
])
def test_unprovided_chinese_quantities_require_review(claim, expected):
    history = [{"role": "user", "content": "尚未实地调查，未提供具体数量。"}]
    assert expected in check(claim, history, skill={"category": "practice"})


@pytest.mark.parametrize(("source", "claim"), [
    ("计划走访5个行政村。", "计划走访五个行政村。"),
    ("计划走访五个行政村。", "计划走访5个行政村。"),
    ("发放问卷100份。", "发放问卷一百份。"),
    ("发放问卷一百份。", "发放问卷100份。"),
    ("访谈记录11份。", "访谈记录十一份。"),
    ("计划举行政策宣讲一场。", "计划举行政策宣讲1场。"),
    ("调查覆盖率为60%。", "调查覆盖率为百分之六十。"),
    ("调查覆盖率为百分之六十。", "调查覆盖率为60%。"),
    ("市场规模3.5亿元。", "市场规模三点五亿元。"),
    ("市场规模一亿二千万元。", "市场规模1.2亿元。"),
    ("融资20万元。", "融资二十万元。"),
    ("覆盖两百户调查对象。", "覆盖200户调查对象。"),
])
def test_chinese_and_arabic_numbers_match_in_the_same_topic(source, claim):
    assert not check(claim, [{"role": "user", "content": source}], skill={"category": "practice"})


@pytest.mark.parametrize("source", [
    "例如问卷一百份。", "尚未发放问卷一百份。", "问卷是不是一百份？", "问卷可能是一百份。",
])
def test_chinese_quantities_in_examples_negations_or_questions_are_not_evidence(source):
    assert "问卷数量" in check("共发放问卷100份。", [{"role": "user", "content": source}],
                           skill={"category": "practice"})


def test_chinese_numbers_remain_project_scoped_and_explicitly_confirmed():
    claim = "计划发放问卷一百份。"
    doc = {"project_id": "project-a", "kind": "source", "confirmed": False,
           "confirmation_origin": "user", "extracted_text": "发放问卷100份。"}
    assert "问卷数量" in check(claim, documents=[doc], skill={"category": "practice"})
    assert "问卷数量" in check(claim, documents=[{**doc, "confirmed": True, "project_id": "other"}],
                           skill={"category": "practice"})
    assert "问卷数量" in check(claim, documents=[{**doc, "confirmed": True, "confirmation_origin": "system"}],
                           skill={"category": "practice"})
    assert not check(claim, documents=[{**doc, "confirmed": True}], skill={"category": "practice"})


def test_ambiguous_chinese_numbers_are_not_silently_converted():
    history = [{"role": "user", "content": "计划发放问卷120份。"}]
    assert "问卷数量" in check("计划发放问卷一百二份。", history, skill={"category": "practice"})
    history = [{"role": "user", "content": "计划发放问卷一百二份。"}]
    assert "问卷数量" in check("计划发放问卷120份。", history, skill={"category": "practice"})


def test_same_chinese_number_does_not_cross_topics_or_units():
    history = [{"role": "user", "content": "计划发放问卷一百份。"}]
    assert "访谈数量" in check("形成访谈记录100份。", history, skill={"category": "practice"})
    assert "问卷数量" in check("发放问卷100人。", history, skill={"category": "practice"})
    villages = [{"role": "user", "content": "计划走访5个村庄。"}]
    assert "调研覆盖范围" in check("计划走访五个行政村。", villages, skill={"category": "practice"})


@pytest.mark.parametrize("quantity", ["十几", "几十", "几百", "数十", "上百"])
def test_approximate_chinese_quantities_are_not_ignored_or_guessed(quantity):
    claim = f"计划发放问卷{quantity}份。"
    assert "问卷数量" in check(claim, skill={"category": "practice"})
    assert not check(claim, [{"role": "user", "content": claim}], skill={"category": "practice"})
