"""Derived, versioned routing cards; the indexed skill catalogue remains authoritative."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

PROFILE_PATH = Path(__file__).with_name("semantic_catalog.json")


def build_skill_cards(skills: list[dict[str, Any]], profile_path: Path = PROFILE_PATH) -> list[dict[str, Any]]:
    try:
        profiles = json.loads(profile_path.read_text(encoding="utf-8")).get("skills_semantic_profiles", {})
    except (OSError, ValueError, TypeError):
        profiles = {}
    cards = []
    for skill in skills:
        name = skill["name"]
        aliases = list(dict.fromkeys(str(item) for item in (
            *skill.get("triggers", []), *profiles.get(name, [])
        ) if item))
        related = [other["name"] for other in skills
                   if other["name"] != name and other.get("category") == skill.get("category")]
        cards.append({
            "id": name,
            "name": skill.get("display_name", name),
            "category": skill.get("category", ""),
            "description": skill.get("description", ""),
            "aliases": aliases,
            "related_skills": related,
            # No invented eligibility criteria: authoritative notices have priority.
            "eligibility": [],
            "exclusions": [],
            "clarification": "请补充申报名称、适用学校和年度，以便确认具体要求。",
            "skill_md_path": skill.get("skill_md_path", ""),
        })
    return cards


def infer_task_type(text: str) -> str:
    if any(word in text for word in ("区别", "对比", "比较", "哪个好")):
        return "compare"
    if any(word in text for word in ("修改", "润色", "改写", "完善初稿")):
        return "revise"
    if any(word in text for word in ("盲审", "打分", "评审", "评估", "评测")):
        return "evaluate"
    if any(word in text for word in ("怎么申请", "申请条件", "有什么要求", "咨询", "能否申请")):
        return "consult"
    return "apply"


def infer_honor_variant(text: str) -> str | None:
    """Infer the outstanding-student subcategory without accepting negated terms."""
    variants = set()
    for clause in re.split(r"[，,。;；!！?？]|或者|或是|还是|或", text):
        for label, aliases in (
            ("outstanding_youth_league", ("优秀共青团员", "优秀团员")),
            ("outstanding_student", ("优秀学生", "三好学生")),
        ):
            for alias in aliases:
                position = clause.find(alias)
                if position < 0:
                    continue
                prefix = clause[max(0, position - 8):position]
                if not re.search(r"(?:不要|不报|不申请|不想|不是|不考虑|不参加|别)(?:.{0,4})$", prefix):
                    variants.add(label)
    return next(iter(variants)) if len(variants) == 1 else None
