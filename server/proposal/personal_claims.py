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
_GPA = re.compile(r"(?:绩点|GPA)\s*(?:为|是|达到|：|:|=)?\s*(?P<score>" + _NUMBER + r")(?:\s*/\s*(?P<scale>" + _NUMBER + r"))?", re.I)
_SCALE = re.compile(r"(?:满分(?:制)?|满绩点|总分)\s*(?:为|是|：|:|=)?\s*(?P<first>" + _NUMBER + r")|(?P<second>" + _NUMBER + r")\s*分制")
_HOURS = re.compile(r"(?:志愿(?:服务|活动|工作)?|义工).{0,25}?(" + _NUMBER + r")\s*(?:个)?(?:小时|时(?!间)|h\b)", re.I)
_USER = re.compile(r"(?:本人|我(?!们))")
_CLAIM_SUBJECT = re.compile(r"(?:本人|申请人|该生|我(?!们))")
_EXAMPLE = re.compile(r"示例|举例|例如|比如|假设|虚构|模板|(?:别人|他人|同学|朋友).{0,8}(?:绩点|GPA|志愿|义工)", re.I)
_NEGATIVE = re.compile(r"(?:没有|未曾|从未|尚未|不要|不能|禁止|不应|未经).{0,15}(?:志愿|绩点|GPA)", re.I)


def _number(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _statements(text: str) -> list[str]:
    # Keep commas: "我的绩点3.8，满分4.0" is one claim.
    result: list[str] = []
    for sentence in re.split(r"[。！？!?\n]", text):
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
    # Remove placeholders before filtering example language too, so an
    # example inside one blank cannot hide a different factual claim.
    content_without_placeholders = re.sub(r"【[^】]*待补充[^】]*】|\[[^\]]*待补充[^\]]*\]", "", content)
    for sentence in _statements(content_without_placeholders):
        if not _CLAIM_SUBJECT.search(sentence):
            continue
        scores, scales = _gpa_values(sentence)
        claimed_scores |= scores
        claimed_scales |= scales
        claimed_hours |= {number for raw in _HOURS.findall(sentence) if (number := _number(raw)) is not None}
    if not (claimed_scores or claimed_scales or claimed_hours):
        return []

    from .chat_context import scholarship_student_facts
    profile, _ = scholarship_student_facts(history, "", documents, project_id=str(project.get("id") or ""))
    facts = (project.get("state") or {}).get("confirmed_facts") or {}
    facts = facts if isinstance(facts, dict) else {}
    source_scores: set[Decimal] = set()
    source_scales: set[Decimal] = set()
    source_hours: set[Decimal] = set()
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
    for item in history:
        text = item.get("content")
        if item.get("role") != "user" or not isinstance(text, str):
            continue
        for sentence in _statements(text):
            if not _USER.search(sentence):
                continue
            _, scales = _gpa_values(sentence)
            source_scales |= scales
            source_hours |= {number for raw in _HOURS.findall(sentence) if (number := _number(raw)) is not None}
    issues = []
    if claimed_scores and (not source_scores or not claimed_scores <= source_scores):
        issues.append("绩点")
    if claimed_scales and (not source_scales or not claimed_scales <= source_scales):
        issues.append("绩点满分制")
    if claimed_hours and (not source_hours or not claimed_hours <= source_hours or len(source_hours) > 1):
        issues.append("志愿服务时长")
    return issues
