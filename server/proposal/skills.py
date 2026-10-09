from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "index.json"
SUBSKILLS_DIR = ROOT / "subskills"


def normalize_skill_id(value: str) -> str:
    return str(value or "").strip().replace("_", "-").lower()


def valid_fact_key(value: str) -> bool:
    key = str(value or "")
    reserved = {
        "confirmed_facts", "fact_sources", "references", "official_sources",
        "initial_request", "outline_confirmed", "template_answer", "template_preference",
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
        text = skill["skill_path"].read_text(encoding="utf-8")
        return text[:max_chars]


registry = SkillRegistry()
