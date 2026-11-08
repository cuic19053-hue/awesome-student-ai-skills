"""A source-bound first draft for a need-based merit scholarship application.

Only explicit student facts enter the letter.  The draft neither decides
eligibility nor invents financial-hardship recognition or personal history.
"""
from __future__ import annotations

from typing import Any

from .chat_context import (
    _is_personal_draft_request,
    _outstanding_clauses,
    _outstanding_omission_fields,
    _outstanding_truthfulness_instruction,
    outstanding_student_omissions,
    scholarship_student_facts,
)


def is_motivation_draft_request(text: str, project: dict[str, Any]) -> bool:
    if (project.get("state") or {}).get("skill_id") != "motivation-scholarship":
        return False
    # An instruction to hide one field is not a refusal to write the letter.
    intent = "。".join(part for part in _outstanding_clauses(text)
                      if not _outstanding_omission_fields(part)
                      and not _outstanding_truthfulness_instruction(part))
    return _is_personal_draft_request(intent, r"(?:国家励志奖学金|励志奖学金)")


def motivation_student_facts(history: list[dict[str, Any]], user_text: str,
                             documents: list[dict[str, Any]], *, project_id: str) -> tuple[dict[str, str], bool, set[str]]:
    facts, conflicted = scholarship_student_facts(
        history, user_text, documents, project_id=project_id, include_family_income=True,
        field_level_grade_omission=True,
    )
    return facts, conflicted, outstanding_student_omissions(history, user_text)


def motivation_placeholder_draft(facts: dict[str, str], *, conflicted: bool = False,
                                 omitted: set[str] | None = None) -> str:
    omitted = omitted or set()
    field = lambda label: facts.get(label, f"【{label}待补充】")
    profile = []
    if "姓名" not in omitted:
        profile.append(f"我叫{field('姓名')}")
    if "学院" not in omitted:
        profile.append(f"现就读于{field('学院')}")
    if "专业" not in omitted:
        profile.append(f"所学专业为{field('专业')}")
    study = []
    if "绩点" not in omitted:
        study.append(f"绩点为{field('绩点')}")
    if "排名" not in omitted:
        study.append(f"排名为{field('排名')}")
    note = "请补充【待补充】的内容，完成后可以在工作台保存草稿。"
    if conflicted:
        note += "部分信息有不同说法，请告诉我应使用哪一项。"
    return "".join((
        '<WritingBlock variant="document">\n## 国家励志奖学金申请书\n\n尊敬的评审老师：\n\n',
        "我申请【申请学年待补充】国家励志奖学金，现将本人情况说明如下。\n\n",
        ("，".join(profile) + "。\n\n") if profile else "",
        ("我的" + "，".join(study) + "。\n\n") if study else "",
        "【学习情况和学业经历待补充】\n\n",
        "" if facts.get("不写家庭收入") else f"我的家庭年收入为{field('家庭年收入')}。\n\n",
        "【家庭经济情况及困难认定进展待补充】\n\n",
        "【在校表现、申请理由和未来计划待补充】\n\n恳请老师审阅。\n\n此致\n敬礼！\n\n",
        "" if "姓名" in omitted else f"申请人：{field('姓名')}\n",
        "日期：【待补充】\n</WritingBlock>\n\n", note,
    ))
