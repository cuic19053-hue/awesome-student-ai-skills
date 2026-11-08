"""Spot unsupported participant counts in common social-survey layouts.

This supplements the general project-number check for tables and field forms,
where numbers often have no unit beside them. It does not establish whether a
number is true, scientifically adequate, or in the latest school template.
"""
from __future__ import annotations

import re
from typing import Any

from .project_claims import _numeric_value


_LABELS = {
    "调查样本数量": re.compile(r"(?:调研|调查)?样本(?:量|数|数量)|(?:拟)?(?:调研|调查|受访)(?:者)?(?:人数|人次|数量|数)"),
    "问卷数量": re.compile(r"(?:问卷|调查表)(?:发放|回收|有效)?(?:量|份数|数|数量|份)?"),
    "访谈数量": re.compile(r"(?:访谈|采访)(?:人数|人次|对象数|数量|数|记录数)?"),
    "调研覆盖范围": re.compile(r"(?:覆盖|走访|调研|调查)(?:的)?(?:社区|村庄|行政村)(?:个数|数量|数)?|(?:社区|村庄|行政村)(?:覆盖数|数量|个数)"),
}
_VALUE = r"(?:\d{1,7}|[零〇一二两三四五六七八九十百千]+)"
_TRAILING = r"(?:\s*(?:份|人|位|名|户|次|个|个社区|个村|个村庄|社区|村|村庄))?"
_FIELD_VALUE = re.compile(rf"^\s*[：:=]?\s*(?P<value>{_VALUE}){_TRAILING}\s*$")
_NO_EVIDENCE = re.compile(
    r"示例|例如|比如|举例|假设|假如|虚构|范例|参考值|待确认|未确认|不确定|暂定|待定|预计|建议|"
    r"[？?]|是否|是不是|能否|有没有|(?:没有|尚未|未曾|从未|不是|不要|禁止|无需|不能|未达到).{0,16}"
    r"(?:问卷|访谈|采访|受访|调查|调研|样本|社区|村庄|行政村)"
)
_PARTIAL = re.compile(r"未能识别|读取组件不可用|仅提取|低置信度|替换字符|乱码")


def _category(label: str) -> str | None:
    label = re.sub(r"[（(]\s*(?:人|人次|位|名|份|户|个|社区|村|村庄|份数|人数)\s*[）)]", "", label)
    label = re.sub(r"[\s*（）()：:]+", "", label)
    # Require a field name, not a long sentence containing an incidental word.
    for name, pattern in _LABELS.items():
        if pattern.fullmatch(label):
            return name
    return None


def _number(value: str) -> int | None:
    value = value.strip()
    if not re.fullmatch(_VALUE, value):
        return None
    parsed = _numeric_value(value)
    if parsed is None or parsed != parsed.to_integral_value() or parsed < 0:
        return None
    return int(parsed)


def _field_value(raw: str) -> int | None:
    match = _FIELD_VALUE.fullmatch(raw.strip())
    return _number(match.group("value")) if match else None


def _add(result: dict[str, set[int]], category: str | None, value: int | None) -> None:
    if category is not None and value is not None:
        result.setdefault(category, set()).add(value)


def _counts(text: str, *, source: bool) -> dict[str, set[int]]:
    result: dict[str, set[int]] = {}
    header: list[str | None] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            header = None
            continue
        if source and _NO_EVIDENCE.search(line):
            header = None
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")] if "|" in line else []
        if len(cells) >= 2:
            if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
                continue
            categories = [_category(cell) for cell in cells]
            # Vertical table: | 样本量 | 100 |. Multiple label/value pairs
            # are accepted only when the value cell is a bare count.
            for index, category in enumerate(categories[:-1]):
                _add(result, category, _field_value(cells[index + 1]))
            if header and len(header) == len(cells):
                for category, cell in zip(header, cells):
                    _add(result, category, _field_value(cell))
            header = categories if any(categories) else None
            continue
        header = None
        # Labeled form: 样本量：100 or 访谈人数：10 人.
        label, sep, value = line.partition("：")
        if not sep:
            label, sep, value = line.partition(":")
        if sep:
            _add(result, _category(label.lstrip(" -*#")), _field_value(value))
        # Short natural statements such as “计划调查100人” can support a
        # table's number, but neither unrelated numbers nor missing units can.
        for pattern, category in (
            (rf"(?:样本量|样本数量|受访人数|调查人数|调研人数)\s*(?:为|是|约|计划为)?\s*({_VALUE})\s*(?:人|位|名)?(?![\d年月日.])", "调查样本数量"),
            (rf"(?:调查|调研|走访|访问)\s*({_VALUE})\s*(?:人|位|名)(?![\d])", "调查样本数量"),
            (rf"问卷(?:发放|回收|有效)?(?:数量|数|份数)?\s*(?:为|是|约|计划为)?\s*({_VALUE})\s*(?:份|张)(?![\d])", "问卷数量"),
            (rf"(?:访谈|采访)\s*({_VALUE})\s*(?:人|位|名|次)(?![\d])", "访谈数量"),
        ):
            for match in re.finditer(pattern, line):
                _add(result, category, _number(match.group(1)))
    return result


def unsupported_survey_table_counts(
    skill: dict[str, Any], project: dict[str, Any], history: list[dict[str, Any]],
    documents: list[dict[str, Any]], content: str,
) -> list[str]:
    """Flag unprovided counts; confirmed materials are input, not verification."""
    if skill.get("id") != "social-survey" and (project.get("state") or {}).get("skill_id") != "social-survey":
        return []
    if not isinstance(content, str):
        return []
    generated = _counts(content, source=False)
    if not generated:
        return []
    sources = [str(message["content"]) for message in history
               if message.get("role") == "user" and isinstance(message.get("content"), str)]
    for document in documents:
        if (document.get("project_id") != project.get("id")
                # Official notices may state a minimum or a previous cohort's
                # scale, which does not establish this team's own plan.
                or document.get("kind") != "source"
                or document.get("confirmed") not in (True, 1)
                or document.get("confirmation_origin") != "user"
                or document.get("low_confidence_count")
                or _PARTIAL.search(str(document.get("extraction_warning") or ""))):
            continue
        if isinstance(document.get("extracted_text"), str):
            sources.append(document["extracted_text"][:100_000])
    supported: dict[str, set[int]] = {}
    for source in sources:
        for category, values in _counts(source, source=True).items():
            supported.setdefault(category, set()).update(values)
    return [category for category, values in generated.items()
            if not values <= supported.get(category, set()) or len(supported.get(category, set())) > 1]
