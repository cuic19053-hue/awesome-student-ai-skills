from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "index.json"
SUBSKILLS_DIR = ROOT / "subskills"


def redact_source_contacts(text: str) -> str:
    """Remove obvious contact and identity numbers before model context."""
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "【邮箱已隐藏】", text)
    text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "【电话已隐藏】", text)
    return re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", "【证件号已隐藏】", text)


def model_safe_guidance(text: str) -> str:
    """Keep writing structure while excluding unverified examples and numeric rules.

    This is a guardrail, not evidence validation. Official requirements still
    have to come from a scope-matched source or the user's confirmed notice.
    """
    text = redact_source_contacts(text)
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is not None:
            lines = lines[end + 1:]
    result = []
    fenced = False
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if re.search(r"(?:案例|例如|示例|样例|范文示范)", line):
            continue
        if re.search(r"\d+(?:\.\d+)?\s*[%％]", line):
            continue
        if re.search(r"\d[\d,]*(?:\.\d+)?\s*(?:万元|万|元|人|天|个月|年|小时|篇|张|项|次|字|分|岁)", line):
            continue
        result.append(line)
    return "\n".join(result) + "\n【示例、代码和数值性要求已过滤；申报规则须核对适用官方来源。】"


def normalize_skill_id(value: str) -> str:
    return str(value or "").strip().replace("_", "-").lower()


def valid_fact_key(value: str) -> bool:
    key = str(value or "")
    reserved = {
        "confirmed_facts", "fact_sources", "references", "official_sources",
        "initial_request", "outline_confirmed", "template_answer", "template_preference",
        "planned_items", "material_revision", "material",
    }
    return bool(
        re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key)
        and not key.startswith(("skill_", "template_", "confirmed_", "fact_"))
        and key not in reserved
    )


class SkillRegistry:
    """Read-only registry for the repository's checked-in skill catalogue."""

    def __init__(self, index_path: Path = INDEX_PATH):
        self.index_path = index_path
        payload = json.loads(index_path.read_text(encoding="utf-8"))
        self.skills = payload.get("skills", [])
        self._by_id = {
            normalize_skill_id(item.get("name") or item.get("id", "")): item
            for item in self.skills
            if item.get("name") or item.get("id")
        }

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "id": normalize_skill_id(item.get("name") or item.get("id", "")),
                "name": item.get("display_name") or item.get("name", ""),
                "category": item.get("category", ""),
                "description": item.get("description", ""),
                "triggers": item.get("triggers", []),
            }
            for item in self.skills
        ]

    def get(self, skill_id: str) -> dict[str, Any] | None:
        item = self._by_id.get(normalize_skill_id(skill_id))
        if not item:
            return None
        path = (ROOT / item.get("skill_md_path", "")).resolve()
        if not path.is_relative_to(SUBSKILLS_DIR.resolve()) or not path.is_file():
            return None
        result = dict(item)
        result["id"] = normalize_skill_id(item.get("name") or item.get("id", ""))
        result["skill_path"] = path
        return result

    def guidance(self, skill_id: str, max_chars: int = 14000) -> str:
        skill = self.get(skill_id)
        if not skill:
            return ""
        text = redact_source_contacts(skill["skill_path"].read_text(encoding="utf-8"))
        return text[:max_chars]

    def model_guidance(self, skill_id: str, max_chars: int = 14000) -> str:
        skill = self.get(skill_id)
        if not skill:
            return ""
        return model_safe_guidance(skill["skill_path"].read_text(encoding="utf-8"))[:max_chars]


registry = SkillRegistry()
