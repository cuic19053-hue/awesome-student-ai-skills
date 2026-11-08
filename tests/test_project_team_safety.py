"""Limited checks for unsupported team, school and implementation claims."""
import pytest
from pathlib import Path

from server.proposal.project_team_safety import unsupported_project_team_claims


SKILL = {"id": "internet-plus", "category": "competition"}
PROJECT = {"id": "project-a", "state": {"confirmed_facts": {}}}
USER = ("我们参加创新大赛高教主赛道，项目叫智灌助手，计划通过土壤湿度监测提示农户灌溉。"
        "团队有三位同学，尚未开展市场调查、没有营业收入，也还没有申请专利。")
ACTUAL = ("我们团队开发了智灌助手项目。该项目通过土壤湿度监测技术，实时监测农田土壤湿度，"
          "并通过智能设备向农户发送灌溉提示。项目团队由三位同学组成，均来自XX大学，"
          "分别负责硬件设计、软件开发和市场推广。")


def check(content, history=(), docs=(), *, project=PROJECT, skill=SKILL):
    return unsupported_project_team_claims(skill, project, list(history), list(docs), content)


def test_actual_real_model_response_without_matching_facts_needs_review():
    assert set(check(ACTUAL, [{"role": "user", "content": USER}])) == {
        "团队学校", "团队分工", "开发状态", "项目功能",
    }


@pytest.mark.parametrize("text", [
    "建议团队成员分别负责硬件设计、软件开发和市场推广。",
    "我们计划开发产品原型，后续拟通过湿度监测提示农户。",
    "可以考虑让团队来自不同专业，尝试软硬件分工。",
    "团队是否来自北京大学？", "团队来自北京大学吗？", "团队来自北京大学？",
    "项目尚未开发原型，也没有上线。", "例如，我们团队来自北京大学。",
])
def test_suggestions_future_questions_negation_and_examples_are_not_asserted_facts(text):
    assert not check(text)


def test_user_stated_team_school_and_roles_can_support_same_claim():
    history = [{"role": "user", "content": "我们团队来自北京大学，成员分别负责硬件设计、软件开发和市场推广。"}]
    assert not check("项目团队来自北京大学，分别负责硬件设计、软件开发和市场推广。", history)
    assert check("项目团队来自清华大学，负责硬件设计。", history) == ["团队学校"]


def test_one_students_school_does_not_justify_every_member_same_school():
    history = [{"role": "user", "content": "我来自北京大学。"}]
    assert check("我们团队成员均来自北京大学。", history) == ["团队学校"]


def test_confirmed_source_must_belong_to_project_and_not_be_policy_or_template():
    output = "项目团队来自北京大学。"
    source = {"project_id": "project-a", "kind": "source", "confirmed": True,
              "confirmation_origin": "user", "extracted_text": "我们团队来自北京大学。"}
    assert not check(output, docs=[source])
    for changed in ({"project_id": "other"}, {"kind": "official"}, {"kind": "template"},
                    {"confirmed": False}, {"extraction_warning": "第2页未能识别文字"}):
        assert check(output, docs=[{**source, **changed}]) == ["团队学校"]
    policy = {**source, "extracted_text": "北京大学学校通知：参赛团队必须来自北京大学。"}
    assert check(output, docs=[policy]) == ["团队学校"]
    policy["extracted_text"] = "学校通知写明参赛要求，团队来自北京大学。"
    assert check(output, docs=[policy]) == ["团队学校"]
    assert check(output, history=[{"role": "user", "content": "学校通知写明参赛要求，团队来自北京大学。"}]) == ["团队学校"]


def test_project_school_for_policy_alone_is_not_team_affiliation():
    project = {"id": "project-a", "school": "北京大学", "state": {"confirmed_facts": {}}}
    assert check("我们团队来自北京大学。", project=project) == ["团队学校"]


def test_actual_development_and_deployment_need_matching_stage():
    history = [{"role": "user", "content": "我们已经开发了一个原型，项目尚未上线。"}]
    assert not check("团队已经开发了原型。", history)
    assert check("项目已经上线。", history) == ["开发状态"]
    assert check("项目已实现实时监测。", history) == ["项目功能"]


def test_later_explicit_correction_replaces_old_team_school():
    history = [{"role": "user", "content": "我们团队来自北京大学。"},
               {"role": "user", "content": "更正，团队来自清华大学。"}]
    assert not check("我们团队来自清华大学。", history)
    assert check("我们团队来自北京大学。", history) == ["团队学校"]


def test_conflicting_team_schools_without_correction_need_review():
    history = [{"role": "user", "content": "我们团队来自北京大学。"},
               {"role": "user", "content": "我们团队来自清华大学。"}]
    assert check("我们团队来自北京大学。", history) == ["团队学校"]


def test_later_explicit_denial_removes_previous_school():
    history = [{"role": "user", "content": "我们团队来自北京大学。"},
               {"role": "user", "content": "我们不是北京大学，团队来自清华大学。"}]
    assert check("我们团队来自北京大学。", history) == ["团队学校"]
    assert not check("我们团队来自清华大学。", history)


def test_named_assignment_and_explicit_correction_do_not_mix_people():
    history = [{"role": "user", "content": "团队张三负责硬件设计。"}]
    assert not check("团队张三负责硬件设计。", history)
    assert check("团队李四负责硬件设计。", history) == ["团队分工"]
    updated = history + [{"role": "user", "content": "更正，李四负责硬件设计。"}]
    assert not check("团队李四负责硬件设计。", updated)
    assert check("团队张三负责硬件设计。", updated) == ["团队分工"]


def test_later_development_denial_cancels_old_affirmation():
    history = [{"role": "user", "content": "团队已经开发了项目。"},
               {"role": "user", "content": "更正，我们还没有开发项目。"}]
    assert check("我们团队已经开发了项目。", history) == ["开发状态"]


def test_number_of_students_alone_is_not_evidence_of_roles():
    history = [{"role": "user", "content": "我们团队有三位同学。"}]
    assert check("团队成员分别负责软件开发和市场推广。", history) == ["团队分工"]


def test_other_skill_categories_are_not_checked():
    assert not check(ACTUAL, skill={"category": "scholarship"})


def test_real_model_new_plan_and_collaborators_need_student_review():
    raw = (Path(__file__).parent / "fixtures" / "internet_plus_quality_retest.txt").read_text()
    history = [{"role": "user", "content": "我们做校园闲置物品交换平台，计划提供信息发布与匹配服务。尚未开发、尚无收入，也没有市场调研或融资。请写项目简介和商业模式，不要编造数据。"}]
    assert {"定位方案", "收费方案", "合作安排", "团队分工", "安全效果"}.issubset(set(check(raw, history)))


@pytest.mark.parametrize("content", [
    "可以考虑采用LBS定位技术。", "建议与学生会合作。", "建议试试抽佣模式。",
    "例如通过LBS定位。", "采用LBS定位技术？", "要采用LBS定位技术吗？", "尚未采用定位技术。",
    "不计划采用抽佣模式。", "不与商家合作。", "项目的定位方案尚未确定。",
    "平台拟提供安全提示，帮助用户提高交易安全意识。",
])
def test_unselected_plans_suggestions_questions_and_denials_are_not_asserted(content):
    assert not check(content)


def test_specific_provided_plans_and_partners_are_respected():
    history = [{"role": "user", "content": "我们计划使用LBS定位，并考虑采用抽佣模式，计划与商家合作。"}]
    # “考虑” in the student's own text is not a settled pricing decision.
    assert set(check("项目将采用LBS定位和抽佣模式，并与商家合作。", history)) == {"收费方案"}
    history[0]["content"] = "我们计划使用LBS定位，采用抽佣模式，并与商家合作。"
    assert not check("项目将采用LBS定位和抽佣模式，并与商家合作。", history)
    assert check("平台将与高校社团和商家合作。", history) == ["合作安排"]


def test_later_retraction_cancels_previously_confirmed_plan():
    history = [{"role": "user", "content": "计划使用LBS定位。"},
               {"role": "user", "content": "更正，不再使用定位技术。"}]
    assert check("平台将使用LBS定位技术。", history) == ["定位方案"]


def test_absolute_safety_guarantee_requires_attention():
    assert check("平台通过定位确保交易双方的安全。") == ["安全效果"]
    assert not check("平台提供安全提示，帮助降低交易风险。")
