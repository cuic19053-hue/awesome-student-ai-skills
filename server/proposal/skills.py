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
    example_section_level = 0
    example_paragraph = False
    example_started = False
    for line in lines:
        if line.lstrip().startswith("```"):
            was_fenced = fenced
            fenced = not fenced
            if was_fenced and example_paragraph:
                example_paragraph = False
            continue
        if fenced:
            continue
        stripped = line.strip()
        heading = re.match(r"^(#{1,6})\s+", stripped)
        if example_section_level:
            if not heading or len(heading.group(1)) > example_section_level:
                continue
            example_section_level = 0
        if heading and len(heading.group(1)) > 1 and re.search(r"(?:案例|示例|样例|范文|硬门槛|一票否决)", stripped):
            example_section_level = len(heading.group(1))
            example_paragraph = False
            continue
        if example_paragraph:
            if heading:
                example_paragraph = False
            elif not stripped:
                if example_started:
                    example_paragraph = False
                continue
            else:
                example_started = True
                continue
        if re.search(r"(?:案例|例如|举例|示例|样例|范文|硬门槛|一票否决)", line):
            if stripped.endswith(("：", ":")) and not heading:
                example_paragraph = True
                example_started = False
            continue
        if re.search(r"(?:不达标|双达标|是否已获得过|重复获得|直接筛掉)", line):
            continue
        # Build instructions in repository Skills describe external IDE/CLI
        # use; the workbench has its own explicit draft/export workflow.
        if re.search(r"(?:build\.py|生成正式|直接提交|可提交的\s*\.docx)", line, re.IGNORECASE):
            continue
        # Skill blockquotes frequently contain complete sample applications;
        # retaining only their label lets weak models copy invented identities.
        if line.lstrip().startswith(">"):
            continue
        # Inline examples in collection tables can seed invented identities too.
        if re.search(r"(?:^|[，,（(：:\s])如\s*[\"“'‘（(]", line):
            continue
        if re.search(r"\d{4}|\d+\s*/\s*\d+|\d+\s*级", line):
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

    def model_guidance_page(self, skill_id: str, offset: int, page_size: int = 8000) -> dict[str, Any]:
        """Page the *filtered* guide, never a raw Skill file or a filesystem path."""
        skill = self.get(skill_id)
        if not skill:
            return {"error": "未找到该技能。"}
        if type(offset) is not int or offset < 0:
            return {"error": "指南偏移量必须是非负整数。"}
        guidance = model_safe_guidance(skill["skill_path"].read_text(encoding="utf-8"))
        if offset > len(guidance):
            return {"error": "指南偏移量超出范围。"}
        end = min(offset + page_size, len(guidance))
        return {"guidance": guidance[offset:end], "offset": offset,
                "next_offset": end if end < len(guidance) else None}


registry = SkillRegistry()


def discovery_tool_schemas() -> list[dict[str, Any]]:
    """Read-only catalogue and guidance tools for the conversation runtime."""
    return [
        {"type": "function", "function": {
            "name": "list_available_skills",
            "description": "查看可用申报 Skill 的名称和类别；仅供选择，不改变当前项目。",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        }},
        {"type": "function", "function": {
            "name": "load_skill_guidance",
            "description": "按需查阅当前项目已选 Skill 的写作指南；结果如有 next_offset，可传回该值读取后续内容。不能切换赛道或执行脚本。",
            "parameters": {"type": "object", "properties": {
                "skill_id": {"type": "string", "description": "当前项目的 Skill 标识"},
                "offset": {"type": "integer", "minimum": 0, "description": "从上次结果的 next_offset 继续；首次读取可省略"},
            }, "required": ["skill_id"], "additionalProperties": False},
        }},
    ]


def invoke_discovery_tool(name: str, arguments: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """Bound discovery to checked-in skills without changing project state.

    Catalogue descriptions often include stale numeric eligibility rules; expose
    only identifiers, names, categories, and nonnumeric routing aliases until
    official evidence is checked.
    """
    state = project.get("state") or {}
    # Old project records without a skill were explicitly created as innovation
    # research. An explicit empty ID is a new, not-yet-routed conversation.
    current = normalize_skill_id(state.get("skill_id", "innovation-research"))
    if name == "list_available_skills":
        if arguments:
            return {"error": "查看技能目录不接受参数。"}
        skills = []
        for item in registry.list():
            if not registry.get(item["id"]):
                continue
            aliases = list(dict.fromkeys(
                redact_source_contacts(alias.strip())
                for alias in item.get("triggers", [])
                if isinstance(alias, str) and 1 < len(alias.strip()) <= 40
                and not re.search(r"\d", alias)
            ))[:8]
            skills.append({"id": item["id"], "name": item["name"],
                           "category": item["category"], "aliases": aliases})
        return {"skills": skills, "current_skill_id": current or None,
                "notice": "技能目录仅供识别用途，申报规则须核对适用官方通知。"}
    if name != "load_skill_guidance":
        return {"error": "未授权的技能工具。"}
    if (not set(arguments) <= {"skill_id", "offset"}
            or not isinstance(arguments.get("skill_id"), str)):
        return {"error": "请提供一个有效的技能标识。"}
    requested = normalize_skill_id(arguments["skill_id"])
    selected = registry.get(requested)
    if not selected:
        return {"error": "未找到该技能，请先查看技能目录。"}
    if not current:
        return {"error": "当前对话尚未选定申报赛道，请先确认再加载对应指南。"}
    if requested != current:
        return {"error": "该技能与当前项目的赛道不同，请先明确确认并选择对应项目或赛道。"}
    page = registry.model_guidance_page(requested, arguments.get("offset", 0))
    if "error" in page:
        return page
    return {"skill_id": requested, "name": selected.get("display_name") or requested, **page,
            "notice": "写作指南不等于官方规则，也不证明学生事实；未知内容须核验或留空。"}
