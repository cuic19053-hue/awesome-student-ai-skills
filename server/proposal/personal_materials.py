"""Conservative profile extraction from explicitly confirmed source material.

Only small, labelled, single-person records are supported. The caller must
still combine results with the student's own messages and handle conflicts;
no project state or user-supplied material is changed here.
"""
from __future__ import annotations

import re
from typing import Any


_REFERENCE = re.compile(
    r"^\[(?P<kind>行\s+[1-9]\d*|段落\s+[1-9]\d*|表格\s+[1-9]\d*\s+第\s+[1-9]\d*\s+行)\][ \t]*"
)
_PAGE = re.compile(r"^\[第\s+([1-9]\d*)\s+页\]$")
_HEADINGS = frozenset({
    "个人资料", "个人信息", "个人基本信息", "学生资料", "学生信息", "学生基本信息",
    "学生个人信息", "申请人资料", "申请人信息", "申请人基本信息", "基本信息", "基本情况",
})
_IGNORED = frozenset({"学号", "性别", "年级", "班级", "学校", "出生年月", "联系方式", "电话", "邮箱"})
_ALIASES = {"GPA": "绩点", "获奖情况": "获奖", "奖项": "获奖"}
_BASE_LABELS = frozenset({"姓名", "学院", "专业", "绩点", "排名", "获奖"})
_BAD_CONTEXT = re.compile(r"示例|举例|例如|比如|假设|虚构|范文|样本|同学|他人|申请条件|申报条件|学校通知|评审规则")
_SIMPLE_TEXT = r"[\u4e00-\u9fffA-Za-z0-9·（）()\- ]{2,80}"


def _label(value: str) -> str:
    label = value.strip().rstrip(":：").strip()
    return _ALIASES.get(label.upper(), _ALIASES.get(label, label))


def _valid_value(label: str, value: str) -> bool:
    if not value or value in _BASE_LABELS | _IGNORED | {"家庭年收入", "GPA"}:
        return False
    if any(marker in value for marker in ("待补充", "示例", "样例", "假设", "虚构", "其他人", "同学")):
        return False
    if label == "姓名":
        return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z· ]{2,30}", value)) and not bool(
            re.search(r"我|姓名|专业|学院|来自|就读|绩点|排名|申请书", value)
        )
    if label in {"学院", "专业"}:
        return bool(re.fullmatch(_SIMPLE_TEXT, value)) and not bool(re.search(r"姓名|绩点|排名|年收入|申请书", value))
    if label == "绩点":
        return bool(re.fullmatch(r"\d{1,3}(?:\.\d{1,3})?(?:\s*/\s*\d{1,3}(?:\.\d{1,3})?)?", value))
    if label == "排名":
        return bool(re.fullmatch(r"(?:第\s*\d{1,5}\s*名|\d{1,5}\s*/\s*\d{1,5})", value))
    if label == "家庭年收入":
        return bool(re.fullmatch(r"(?:约|大约|近)?\s*\d{1,9}(?:\.\d{1,2})?\s*(?:万元|万|元)", value))
    if label == "获奖":
        return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9·（）()、，,\- ]{2,80}", value))
    return False


def confirmed_personal_material_fields(
    document: dict[str, Any], expected_name: str, *, project_id: str, include_family_income: bool = False,
    identity_out: dict[str, str] | None = None,
) -> dict[str, str]:
    """Read labelled fields from a single confirmed, unambiguous student record.

    Accepts extractor-generated line/paragraph/page references and DOCX rows
    represented as label/value cells separated by `` | ``. Mixed-person lists,
    repeated fields, uncertain rows, examples, non-source material, and names
    not explicitly matching the current student are rejected. Each page of a
    multi-page PDF must independently identify the same person. If requested,
    auxiliary identifiers are returned separately only after complete parsing,
    so callers can detect conflicts across documents without putting them in a draft.
    """
    confirmed = document.get("confirmed")
    if (not isinstance(project_id, str) or not project_id or document.get("project_id") != project_id
            or document.get("kind") != "source"
            or (confirmed is not True and (type(confirmed) is not int or confirmed != 1))
            or document.get("confirmation_origin") != "user"
            or not isinstance(expected_name, str) or not _valid_value("姓名", expected_name.strip())):
        return {}
    text = document.get("extracted_text")
    if not isinstance(text, str) or not text.strip() or len(text) > 100_000 or _BAD_CONTEXT.search(text):
        return {}
    # A user can confirm a partial extraction, but missing pages or uncertain
    # OCR cannot establish that the document contains just one person's data.
    warning = str(document.get("extraction_warning") or "")
    if (document.get("low_confidence_count") or 0) or re.search(
        r"未能识别|读取组件不可用|仅提取|低置信度|替换字符|乱码", warning,
    ):
        return {}
    labels = _BASE_LABELS | ({"家庭年收入"} if include_family_income else set())
    accepted: dict[str, str] = {}
    # Auxiliary identity fields are deliberately not written into a draft,
    # but conflicting values can reveal two same-named students or mixed
    # records, particularly across pages. Do not merge that material.
    identity: dict[str, str] = {}
    pages = 0
    page_has_name = False
    for original in text.splitlines():
        line = original.strip()
        if not line:
            continue
        page_marker = _PAGE.fullmatch(line)
        if page_marker:
            if (pages and not page_has_name) or int(page_marker.group(1)) != pages + 1:
                return {}
            pages += 1
            if pages > 10:
                return {}
            page_has_name = False
            continue
        ref = _REFERENCE.match(line)
        table = bool(ref and ref.group("kind").startswith("表格"))
        if ref:
            line = line[ref.end():].strip()
        # An embedded second reference is user content, not another trusted
        # extraction marker. Never strip it to make a field appear valid.
        if not line or line.startswith("["):
            return {}
        if line.rstrip("：:").strip() in _HEADINGS:
            continue
        if table and "|" in line:
            cells = [part.strip() for part in line.split("|")]
            if len(cells) % 2 or any(not part for part in cells):
                return {}
            pairs = list(zip(cells[::2], cells[1::2]))
        else:
            match = re.fullmatch(r"([^：:|]{1,25})\s*[：:]\s*(.*?)\s*", line)
            if not match:
                return {}
            pairs = [(match.group(1), match.group(2))]
        for raw_key, raw_value in pairs:
            key, value = _label(raw_key), raw_value.strip()
            if key in _IGNORED:
                # A column heading or another label in the value position is
                # not a labelled single-person value.
                if not value or _label(value) in labels | _IGNORED:
                    return {}
                normalized_value = re.sub(r"\s+", "", value)
                if key in identity and identity[key] != normalized_value:
                    return {}
                identity[key] = normalized_value
                continue
            if key == "家庭年收入" and not include_family_income:
                if not _valid_value(key, value):
                    return {}
                continue
            if key == "姓名" and pages:
                if page_has_name or value != expected_name.strip() or not _valid_value(key, value):
                    return {}
                page_has_name = True
                if "姓名" in accepted:
                    continue
            if key not in labels or key in accepted or not _valid_value(key, value):
                return {}
            accepted[key] = value
    if (pages and not page_has_name) or accepted.get("姓名") != expected_name.strip():
        return {}
    if identity_out is not None:
        identity_out.update(identity)
    return accepted
