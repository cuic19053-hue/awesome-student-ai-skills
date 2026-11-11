"""Narrow checks for numerical personal claims in generated application text.

A match indicates only that the same value was supplied by the student; it is
not an external verification. Unsupported matches require a person's review.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .section_grounding import is_personal_skill

_NUMBER = r"\d{1,5}(?:\.\d{1,3})?"
_GPA = re.compile(r"(?:绩点|GPA)\s*(?:更正为|更新为|改成|改为|为|是|达到|：|:|=)?\s*(?P<score>" + _NUMBER + r")(?:\s*/\s*(?P<scale>" + _NUMBER + r"))?", re.I)
_SCALE = re.compile(r"(?:满分(?:制)?|满绩点|总分)\s*(?:为|是|：|:|=)?\s*(?P<first>" + _NUMBER + r")|(?P<second>" + _NUMBER + r")\s*分制")
_HOURS = re.compile(r"(?:志愿(?:服务|活动|工作)?|义工).{0,25}?(" + _NUMBER + r")\s*(?:个)?(?:小时|时(?!间)|h\b)", re.I)
_USER = re.compile(r"(?:本人|我(?!们))")
_CLAIM_SUBJECT = re.compile(r"(?:本人|申请人|该生|我(?!们))")
_EXAMPLE = re.compile(r"示例|举例|例如|比如|假设|虚构|模板|(?:别人|他人|同学|朋友).{0,8}(?:绩点|GPA|志愿|义工)", re.I)
_NEGATIVE = re.compile(r"(?:没有|未曾|从未|尚未|不要|不能|禁止|不应|未经).{0,15}(?:志愿|绩点|GPA|排名|获奖|获得|荣获)", re.I)
_REFERENCE_CONTEXT = re.compile(r"通知|政策|规定|条件|门槛|要求|标准|资格|例如|示例|假设|建议|希望|争取|计划|目标")
_OTHER_PERSON = re.compile(r"他人|别人|第三人|(?:朋友|同学)的|他的|她的|某同学")
_RANK = re.compile(
    r"(?:专业|年级|班级|综合测评|综合成绩|学业成绩)?\s*(?:排名|名次)\s*(?:更正为|更新为|改成|改为|为|是|：|:|=)?\s*"
    r"(?:(?P<place>\d{1,5})\s*/\s*(?P<total>\d{1,5})|第?\s*(?P<ordinal>\d{1,5})\s*名|"
    r"(?P<percent>前?\s*\d{1,3}(?:\.\d{1,3})?\s*[%％]))"
)
_AWARD = re.compile(
    r"(?:荣获|获得|获评|被评为|(?:获奖情况|获奖|奖项)\s*[：:=])\s*(?:过|了)?\s*"
    r"(?P<award>[^，,；;。！？!?\n]{1,45}?(?:一等奖|二等奖|三等奖|特等奖|优秀奖|金奖|银奖|铜奖|奖学金|荣誉称号))"
)


def _table_text(text: str) -> str:
    """Add labelled rows for ordinary Markdown profile tables."""
    headers: list[str] = []
    expanded: list[str] = []
    context: list[str] = []
    for line in text.splitlines():
        if "|" not in line:
            headers = []
            context = (context + [line])[-3:]
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        if not headers:
            headers = cells
            continue
        if len(cells) != len(headers):
            continue
        prefix = "政策要求：" if _REFERENCE_CONTEXT.search(" ".join(context)) else ""
        if len(cells) == 2 and re.search(r"绩点|GPA|排名|名次|志愿|义工|获奖|奖项", cells[0], re.I):
            expanded.append(prefix + cells[0] + "：" + cells[1])
        expanded.extend(prefix + key + "：" + value for key, value in zip(headers, cells)
                        if re.search(r"绩点|GPA|排名|名次|志愿|义工|获奖|奖项", key, re.I))
    return text + "\n" + "\n".join(expanded)


def _rank_values(text: str) -> set[tuple[str, ...]]:
    values: set[tuple[str, ...]] = set()
    for match in _RANK.finditer(text):
        if match.group("place"):
            values.add(("fraction", str(int(match.group("place"))), str(int(match.group("total")))))
        elif match.group("ordinal"):
            values.add(("ordinal", str(int(match.group("ordinal")))))
        else:
            values.add(("percent", re.sub(r"\s+", "", match.group("percent")).replace("％", "%")))
    return values


def _award_values(text: str) -> set[str]:
    return {re.sub(r"\s+|[“”\"《》]", "", match.group("award")) for match in _AWARD.finditer(text)}


def _personal_source_statements(text: str, expected_name: str) -> list[str]:
    """Preserve ownership when reading chat self-reports and profile tables."""
    result: list[str] = []
    prose = "\n".join(line for line in text.splitlines() if "|" not in line)
    for sentence in _statements(prose):
        anchored = False
        for clause in re.split(r"[，,；;]", sentence):
            if (_OTHER_PERSON.search(clause) or _REFERENCE_CONTEXT.search(clause)
                    or re.search(r"听说|听到|看到|介绍|辅导员|老师说|我说|我问|我觉得|我认为|想知道", clause)):
                anchored = False
                continue
            if _USER.search(clause):
                anchored = True
                result.append(clause)
            elif anchored and re.match(r"\s*(?:满分|采用|绩点|GPA|专业排名|排名|志愿|义工|获奖|获得|荣获)", clause, re.I):
                result.append("本人" + clause)
            else:
                anchored = False
    if not expected_name or _EXAMPLE.search(text) or _OTHER_PERSON.search(text):
        return result
    # Each table needs its own identity. A self-introduction somewhere else in
    # a message cannot authorize a classmate's or a multi-person table.
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if "|" not in lines[index]:
            index += 1
            continue
        start = index
        while index < len(lines) and "|" in lines[index]:
            index += 1
        rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
                for line in lines[start:index]]
        rows = [row for row in rows if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in row)]
        if len(rows) < 2:
            continue
        names: list[str] = []
        headers = rows[0]
        if "姓名" in headers:
            name_index = headers.index("姓名")
            if any(len(row) != len(headers) for row in rows[1:]):
                continue
            names = [row[name_index] for row in rows[1:]]
        else:
            names = [row[1] for row in rows if len(row) == 2 and row[0] == "姓名"]
        if names:
            if len(names) != 1 or names[0] != expected_name:
                continue
        else:
            preceding = "\n".join(lines[max(0, start - 2):start]).strip()
            own_heading = (r"(?:我叫\s*" + re.escape(expected_name)
                           + r"|(?:我的|本人的)(?:个人)?(?:资料|信息|成绩)(?:如下)?)[：:。\s]*$")
            if not re.search(own_heading, preceding):
                continue
        table = "\n".join(lines[start:index])
        result.extend("本人" + item for item in _statements(_table_text(table)[len(table):]))
    return result


def _number(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _statements(text: str) -> list[str]:
    # Keep commas: "我的绩点3.8，满分4.0" is one claim.
    result: list[str] = []
    for sentence in re.split(r"[。！？!?\n]", _table_text(text)):
        if not sentence or _EXAMPLE.search(sentence):
            continue
        if not _NEGATIVE.search(sentence):
            result.append(sentence)
            continue
        # A denial in one clause must not hide an unrelated affirmative claim.
        # Retain subject context across conjunctions within the same sentence.
        subject = _CLAIM_SUBJECT.search(sentence)
        positive = [clause for clause in re.split(r"[，,；;]|但是|但", sentence)
                    if clause and not _NEGATIVE.search(clause)]
        joined = "，".join(positive)
        if joined:
            result.append((subject.group() if subject and not _CLAIM_SUBJECT.search(joined) else "") + joined)
    return result


def _gpa_values(value: str) -> tuple[set[Decimal], set[Decimal]]:
    scores: set[Decimal] = set()
    scales: set[Decimal] = set()
    for match in _GPA.finditer(value):
        score = _number(match.group("score"))
        if score is not None:
            scores.add(score)
        scale = _number(match.group("scale")) if match.group("scale") else None
        if scale is not None:
            scales.add(scale)
        # A scale is valid only in the same statement as a GPA.
        for item in _SCALE.finditer(value):
            scale = _number(item.group("first") or item.group("second"))
            if scale is not None:
                scales.add(scale)
    return scores, scales


def unsupported_personal_numbers(
    skill: dict[str, Any], project: dict[str, Any], history: list[dict[str, Any]], documents: list[dict[str, Any]], content: str,
) -> list[str]:
    if not is_personal_skill(skill):
        return []
    if not isinstance(content, str):
        return []
    claimed_scores: set[Decimal] = set()
    claimed_scales: set[Decimal] = set()
    claimed_hours: set[Decimal] = set()
    claimed_ranks: set[tuple[str, ...]] = set()
    claimed_awards: set[str] = set()
    # Remove placeholders before filtering example language too, so an
    # example inside one blank cannot hide a different factual claim.
    content_without_placeholders = re.sub(r"【[^】]*待补充[^】]*】|\[[^\]]*待补充[^\]]*\]", "", content)
    for sentence in _statements(content_without_placeholders):
        if _OTHER_PERSON.search(sentence):
            continue
        # Application prose and tables commonly omit the first-person subject.
        # Keep policy examples and general advice out of this implicit context.
        if not _CLAIM_SUBJECT.search(sentence) and _REFERENCE_CONTEXT.search(sentence):
            continue
        scores, scales = _gpa_values(sentence)
        claimed_scores |= scores
        claimed_scales |= scales
        claimed_hours |= {number for raw in _HOURS.findall(sentence) if (number := _number(raw)) is not None}
        claimed_ranks |= _rank_values(sentence)
        if not re.search(r"希望|争取|计划|目标|申请获得", sentence):
            claimed_awards |= _award_values(sentence)
    if not (claimed_scores or claimed_scales or claimed_hours or claimed_ranks or claimed_awards):
        return []

    from .chat_context import scholarship_student_facts
    profile, _ = scholarship_student_facts(history, "", documents, project_id=str(project.get("id") or ""))
    facts = (project.get("state") or {}).get("confirmed_facts") or {}
    facts = facts if isinstance(facts, dict) else {}
    source_scores: set[Decimal] = set()
    source_scales: set[Decimal] = set()
    source_hours: set[Decimal] = set()
    source_ranks: set[tuple[str, ...]] = set()
    source_awards: set[str] = set()
    for value in (profile.get("绩点"), facts.get("gpa"), facts.get("GPA")):
        if value is not None:
            scores, scales = _gpa_values("绩点" + str(value))
            source_scores |= scores
            source_scales |= scales
    for key in ("volunteer_hours", "volunteer_service_hours"):
        if facts.get(key) is not None:
            number = _number(str(facts[key]).strip().removesuffix("小时").strip())
            if number is not None:
                source_hours.add(number)
    for value in (profile.get("排名"), facts.get("rank"), facts.get("ranking")):
        if value is not None:
            source_ranks |= _rank_values("排名" + str(value))
    for value in (profile.get("获奖"), facts.get("awards"), facts.get("achievements")):
        if isinstance(value, str):
            source_awards |= _award_values("获奖情况：" + value)
    supplied_scores = set(source_scores)
    supplied_ranks = set(source_ranks)
    history_scores: set[Decimal] = set()
    history_ranks: set[tuple[str, ...]] = set()
    for item in history:
        text = item.get("content")
        if item.get("role") != "user" or not isinstance(text, str):
            continue
        expected_name = str(profile.get("姓名") or facts.get("applicant_name") or facts.get("name") or "")
        for sentence in _personal_source_statements(text, expected_name):
            scores, scales = _gpa_values(sentence)
            if scores:
                history_scores = scores
            source_scales |= scales
            if source_scores:
                source_scales |= {number for match in _SCALE.finditer(sentence)
                                  if (number := _number(match.group("first") or match.group("second"))) is not None}
            source_hours |= {number for raw in _HOURS.findall(sentence) if (number := _number(raw)) is not None}
            reported_ranks = _rank_values(sentence)
            if reported_ranks:
                history_ranks = reported_ranks
            if not re.search(r"希望|争取|计划|目标|申请获得", sentence):
                source_awards |= _award_values(sentence)
    source_scores = supplied_scores or history_scores
    source_ranks = supplied_ranks or history_ranks
    issues = []
    if claimed_scores and (not source_scores or len(source_scores) > 1 or not claimed_scores <= source_scores):
        issues.append("绩点")
    if claimed_scales and (not source_scales or len(source_scales) > 1 or not claimed_scales <= source_scales):
        issues.append("绩点满分制")
    if claimed_hours and (not source_hours or not claimed_hours <= source_hours or len(source_hours) > 1):
        issues.append("志愿服务时长")
    rank_conflict = (len({value[1] for value in source_ranks if value[0] != "percent"}) > 1
                     or len({value for value in source_ranks if value[0] == "fraction"}) > 1)
    source_ranks |= {("ordinal", value[1]) for value in source_ranks if value[0] == "fraction"}
    if claimed_ranks and (rank_conflict or not claimed_ranks <= source_ranks):
        issues.append("排名")
    if claimed_awards and not claimed_awards <= source_awards:
        issues.append("获奖经历")
    return issues
