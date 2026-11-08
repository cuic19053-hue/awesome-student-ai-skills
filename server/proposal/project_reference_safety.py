"""Identify project dates and source names that need a student's attention.

This is an input comparison, not a check against an authoritative source. It
cannot determine whether a supplied year or named document is real or applies.
"""
from __future__ import annotations

import re
from typing import Any


_YEAR = re.compile(r"(?<!\d)((?:19|20|21)\d{2})(?!\d)")
_MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
_TITLE = re.compile(r"《([^《》\n]{3,100})》")
_FORMAL_ENDING = re.compile(r"(?:通知|意见|办法|条例|法律|法规|细则|规定|规范|标准|决定|公报|白皮书)$")
_REPORT_ENDING = re.compile(r"(?:报告|年报|调研报告|调查报告|统计公报)$")
_CITATION_CUE = re.compile(r"根据|依据|据|引自|摘自|参考|查阅|发布|印发|出台|颁布|发布的|刊载")
_REPORTED_CUE = re.compile(r"显示|指出|公布|表明|发布|印发|明确提出|要求")
_AGENCY_REPORT = re.compile(
    r"(?:根据|依据|据|引自|摘自|参考|查阅)\s*"
    r"(?P<agency>[A-Za-z\u4e00-\u9fff\s]{2,30}?"
    r"(?:环保局|统计局|教育局|财政局|民政局|农业农村局|卫生健康委|政府|委员会|团委|住建部|教育部|财政部|研究院|调查中心))"
    r"\s*(?:(?P<year>(?:19|20|21)\d{2})\s*年\s*)?(?:的)?\s*"
    r"(?P<report>[\u4e00-\u9fff]{0,15}?(?:调研报告|调查报告|统计报告|统计公报|年度报告|年报|报告|公报))"
)
_PARTIAL_EXTRACTION = re.compile(r"未能识别|读取组件不可用|仅提取|低置信度|替换字符|乱码")
_NONFACTUAL_SOURCE = re.compile(
    r"示例|举例|例如|比如|假设|虚构|范文|样例|未核实|不确定|尚不清楚|"
    r"(?:不要|别|不能|禁止|没有|未曾|尚未|并非|不是).{0,20}(?:19|20|21)\d{2}|"
    r"(?:不要|别|不能|禁止|没有|未曾|尚未|并非|不是).{0,20}(?:通知|政策|报告|文件|办法|意见)"
)
_QUESTION_SOURCE = re.compile(r"是否|是不是|能否|能不能|有没有|是真的吗|是不是真的|准确吗|存在吗|吗\s*$")


def _normalized(value: str) -> str:
    return re.sub(r"[\s《》\"'“”‘’]", "", value).casefold()


def _affirmative_fragments(text: str) -> list[str]:
    # Preserve the question mark while splitting, so asking whether a date or
    # notice exists cannot authorize a model to present it as established.
    pieces = re.split(r"([\n。；;！？!?，,])", text)
    result = []
    for index in range(0, len(pieces), 2):
        part = pieces[index]
        delimiter = pieces[index + 1] if index + 1 < len(pieces) else ""
        if (not part.strip() or delimiter in {"?", "？"} or _QUESTION_SOURCE.search(part)
                or _NONFACTUAL_SOURCE.search(part)):
            continue
        result.append(part)
    return result


def _sources(project: dict[str, Any], history: list[dict[str, Any]], documents: list[dict[str, Any]]) -> list[str]:
    result = [str(item["content"]) for item in history
              if item.get("role") == "user" and isinstance(item.get("content"), str)]
    facts = (project.get("state") or {}).get("confirmed_facts") or {}
    if isinstance(facts, dict):
        result.extend(str(value) for value in facts.values() if isinstance(value, (str, int, float)) and not isinstance(value, bool))
    for document in documents:
        if (document.get("project_id") != project.get("id") or document.get("kind") not in {"source", "official"}
                or document.get("confirmed") not in (True, 1) or document.get("confirmation_origin") != "user"
                or document.get("low_confidence_count") or _PARTIAL_EXTRACTION.search(str(document.get("extraction_warning") or ""))):
            continue
        text = document.get("extracted_text")
        if isinstance(text, str):
            result.append(text[:100_000])
    return result


def unsupported_project_references(
    skill: dict[str, Any], project: dict[str, Any], history: list[dict[str, Any]],
    documents: list[dict[str, Any]], content: str,
) -> list[str]:
    """Identify dates and attributed references absent from student-provided input."""
    if skill.get("category") not in {"research", "competition", "practice"} or not isinstance(content, str):
        return []
    sources = _sources(project, history, documents)
    # A student's question, negation or example is not affirmative evidence.
    fragments = [part for source in sources for part in _affirmative_fragments(source)]
    source_text = "\n".join(fragments)
    source_normalized = _normalized(source_text)
    provided_years = set(_YEAR.findall(source_text))
    claimed_years = set(_YEAR.findall(content))
    missing_years = claimed_years - provided_years
    provided_days = {(int(month), int(day)) for month, day in _MONTH_DAY.findall(source_text)}
    claimed_days = {(int(month), int(day)) for month, day in _MONTH_DAY.findall(content)}
    missing_days = claimed_days - provided_days

    missing_reference = False
    for match in _TITLE.finditer(content):
        title = match.group(1).strip()
        preceding = content[max(0, match.start() - 30):match.start()]
        following = content[match.end():match.end() + 25]
        is_formal = bool(_FORMAL_ENDING.search(title))
        is_report_cited = bool(_REPORT_ENDING.search(title) and
                               (_CITATION_CUE.search(preceding) or _REPORTED_CUE.search(following)))
        if (is_formal or is_report_cited) and _normalized(title) not in source_normalized:
            missing_reference = True
            break
    if not missing_reference:
        for match in _AGENCY_REPORT.finditer(content):
            agency = _normalized(match.group("agency"))
            report = _normalized(match.group("report"))
            # Require the institution and the report to occur together in one
            # explicit source, rather than joining unrelated documents.
            if not any(agency in _normalized(source) and report in _normalized(source) for source in fragments):
                missing_reference = True
                break
    result = []
    if missing_years or missing_days:
        result.append("年份与时间")
    if missing_reference:
        result.append("政策与报告名称")
    return result
