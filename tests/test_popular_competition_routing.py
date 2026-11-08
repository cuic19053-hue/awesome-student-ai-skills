"""Student wording for popular competitions must not silently select a track."""
import pytest

from utils.dispatcher import Dispatcher


@pytest.fixture(params=[False, True], ids=["no-semantic-model", "local-vectors"])
def router(request):
    if request.param:
        return Dispatcher(intent_decider=False)
    return Dispatcher(intent_decider=False, semantic_scorer=lambda _: {})


@pytest.mark.parametrize(("question", "expected"), [
    ("我准备报名中国国际大学生创新大赛高教主赛道，项目是智能农业灌溉。", "internet-plus"),
    ("我要写互联网+职教赛道商业计划书。", "internet-plus"),
    ("中国国际大学生创新大赛红旅，做乡村振兴项目。", "internet-plus-red-tour"),
    ("中国大学生创新大赛高教主赛道，计划做智能灌溉。", "internet-plus"),
    ("互联网+红色之旅赛道商业计划书。", "internet-plus-red-tour"),
    ("我想参加挑战杯社会调查，研究大学生使用AI助手的学习习惯。", "challenge-cup"),
    ("我准备参加三下乡，做农村留守儿童教育调研，帮我写社会实践调研类申报书。", "social-survey"),
    ("我不参加互联网+，我要报名挑战杯。", "challenge-cup"),
    ("我不参加挑战杯，准备三下乡社会调查。", "social-survey"),
    ("三下乡支教项目，希望用问卷了解学生需求。", "volunteer-teaching"),
    ("参加中国国际大学生创新大赛高教主赛道，项目是大创创新训练的成果。", "internet-plus"),
    ("我要参加中国国际大学生创新大赛红旅赛道，项目以前是三下乡社会调查。", "internet-plus-red-tour"),
    ("不是互联网+红旅，我要互联网+主赛道。", "internet-plus"),
    ("我不报互联网+主赛道，要报互联网+红旅赛道。", "internet-plus-red-tour"),
    ("不是互联网+红旅我要互联网+主赛道", "internet-plus"),
    ("我不报互联网+主赛道我要报互联网+红旅赛道", "internet-plus-red-tour"),
])
def test_specific_event_and_track_route_to_the_expected_skill(router, question, expected):
    result = router.route(question, allow_model=False)
    assert result["selected"] == expected
    assert result["candidates"][0]["name"] == expected


@pytest.mark.parametrize("question", [
    "我准备报名中国国际大学生创新大赛，项目是智能农业灌溉。",
    "我想报名中国大学生创新大赛。",
    "我想参加互联网+，帮我写商业计划书。",
    "我要申报互联网+主赛道还是红旅赛道？",
    "想参加挑战杯还是互联网+？",
    "挑战杯社会调查还是三下乡社会调查？",
    "三下乡调研还是支教？",
    "报名中国国际大学生创新大赛，项目曾做创业训练。",
    "中国国际大学生创新大赛主赛道还是挑战杯？",
])
def test_unresolved_track_or_explicit_choice_is_not_guessed(router, question):
    result = router.route(question, allow_model=False)
    assert result["selected"] is None and result["needs_clarification"]


def test_unknown_innovation_competition_presents_both_track_candidates():
    router = Dispatcher(intent_decider=False, semantic_scorer=lambda _: {})
    result = router.route("我要报名中国国际大学生创新大赛。")
    assert result["selected"] is None
    assert {item["name"] for item in result["candidates"]} >= {"internet-plus", "internet-plus-red-tour"}


@pytest.mark.parametrize(("question", "expected"), [
    ("请帮我写九推个人陈述。", "graduate-recommendation"),
    ("我想报名研究生夏令营申请，请写个人陈述。", "graduate-recommendation"),
    ("孩子要参加儿童夏令营，请安排活动。", None),
    ("不要九推，我要申请转专业。", "major-transfer"),
    ("要申请保研还是申请转专业？", None),
])
def test_graduate_application_shorthand_and_camp_are_distinguished(router, question, expected):
    assert router.route(question, allow_model=False)["selected"] == expected
