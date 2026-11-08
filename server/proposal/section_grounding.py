"""Identify personal sections that have no student-provided starting material.

This is a narrow no-input check, not a verifier of generated statements.  A
supplied fact or confirmed document does not prove that later prose is true.
"""
from __future__ import annotations

import re
from typing import Any

PERSONAL_CATEGORIES = frozenset({"scholarship", "honor", "political", "military", "study_abroad"})
PERSONAL_SKILL_IDS = frozenset({"graduate-recommendation", "selected-graduate", "major-transfer"})
PERSONAL_SECTION = re.compile(
    r"申请书|个人|家庭|经济|困难|学习|学业|成绩|排名|科研|竞赛|获奖|荣誉|"
    r"实践|志愿|学生工作|干部|履职|经历|表现|思想|品德|综合素质|申请理由"
)
PERSONAL_FACT = re.compile(
    r"(?:我叫|我名叫|我是(?!想|希望|准备|打算|需要|申请|要|来)|我在(?!想|考虑)|我曾|"
    r"我有(?!一个问题|个问题|些问题)|我家|我参加|我获得|我担任|我负责|我没有|"
    r"本人(?:是|在|有|曾|参加|获得|担任|负责|没有)|我的(?:姓名|专业|学院|成绩|绩点|排名|家庭|经历)|"
    r"(?:姓名|专业|学院|绩点|排名|家庭年收入|获奖情况)\s*[：:=](?!\s*(?:待补充|未知|不详|未填写))\s*\S)"
)
PROFILE_KEYS = frozenset({
    "name", "applicant_name", "college", "major", "discipline", "gpa", "rank", "ranking",
    "family_income", "academic_performance", "awards", "achievements", "experience",
    "research", "volunteer", "student_work", "political_stage",
})
FAMILY_SECTION = re.compile(r"家庭|经济|困难|收入|贫困")
FAMILY_KEYS = frozenset({"family_income", "family_members", "family_situation", "financial_hardship", "household"})
FAMILY_FACT = re.compile(
    r"(?:我家|我的家庭|本人家庭|家里|父母|家庭成员|家庭年收入|家庭收入|家庭经济情况)"
    r"[^。！？!?\n]{0,35}(?:收入|支出|工作|务农|务工|失业|生病|残疾|成员|人口|困难|负担|元|万|人)"
)


def _has_value(value: Any) -> bool:
    return isinstance(value, (str, int, float)) and str(value).strip() not in {
        "", "待补充", "未知", "不详", "未填写", "None",
    }


def is_personal_skill(skill: dict[str, Any]) -> bool:
    return skill.get("category") in PERSONAL_CATEGORIES or skill.get("id") in PERSONAL_SKILL_IDS


def personal_section_privacy_notice(skill: dict[str, Any], title: str, history: list[dict[str, Any]]) -> str:
    """Avoid sending stored personal material to a model after an explicit opt-out."""
    if not is_personal_skill(skill) or not PERSONAL_SECTION.search(title):
        return ""
    from .chat_context import _income_omission_requested, _income_use_requested

    personal_allowed = True
    income_allowed = True
    for message in history:
        text = message.get("content")
        if message.get("role") != "user" or not isinstance(text, str):
            continue
        if re.search(r"(?:不要|别|禁止|不可|不能)(?:再)?(?:使用|填写|写入|引用|展示|透露).{0,8}(?:我的|本人|个人)?(?:资料|信息)", text):
            personal_allowed = False
        elif re.search(r"(?:可以|允许|同意|请|恢复)(?:再|重新|继续)?(?:使用|填写|写入|引用).{0,8}(?:我的|本人|个人)?(?:资料|信息)", text):
            personal_allowed = True
        if _income_omission_requested(text):
            income_allowed = False
        elif _income_use_requested(text):
            income_allowed = True
    if not personal_allowed:
        return "你要求不使用个人资料，因此暂不自动生成这一部分。你可以手动编辑，或明确说明可以重新使用资料。"
    if skill.get("id") in {"grant-application", "motivation-scholarship"} and not income_allowed:
        return "你要求不写家庭收入；为避免带入已保存的收入，暂不自动生成这一部分。你可以手动编辑。"
    return ""


def missing_personal_starting_material(
    project: dict[str, Any], skill: dict[str, Any], title: str,
    history: list[dict[str, Any]], documents: list[dict[str, Any]],
) -> bool:
    if not is_personal_skill(skill) or not PERSONAL_SECTION.search(title):
        return False
    # Collective applications need their own facts model rather than personal
    # first-person assumptions.
    if skill.get("id") == "class-collective":
        return False
    family_section = bool(FAMILY_SECTION.search(title))
    facts = (project.get("state") or {}).get("confirmed_facts") or {}
    keys = FAMILY_KEYS if family_section else PROFILE_KEYS
    if isinstance(facts, dict) and any(_has_value(facts.get(key)) for key in keys):
        return False
    for message in history:
        text = message.get("content")
        if message.get("role") != "user" or not isinstance(text, str):
            continue
        if re.search(r"示例|举例|例如|比如|假设|虚构|朋友|同学|他人|别人", text):
            continue
        if (FAMILY_FACT.search(text) if family_section else PERSONAL_FACT.search(text)):
            return False
    # Only explicitly confirmed source text is considered.  Names and other
    # labels must be present; school notices and templates are not profiles.
    for document in documents:
        if (document.get("kind") != "source" or not document.get("confirmed")
                or document.get("confirmation_origin") != "user"):
            continue
        text = document.get("extracted_text")
        if not isinstance(text, str) or not text.strip():
            continue
        if re.search(r"示例|举例|例如|比如|假设|虚构|同学|他人|申请条件|申报条件|学校通知|评审规则", text):
            continue
        if (re.search(r"(?:姓名|申请人|本人)\s*[：:]\s*[\u4e00-\u9fffA-Za-z·]{2,30}", text)
                and (not family_section or FAMILY_FACT.search(text))):
            return False
    return True
