"""Keep clearly different applicants' materials out of personal writing.

The check only removes an explicitly identified different person when the
current applicant's name is also clear. Unknown identity is not verification,
and no name-based rule can distinguish people who have the same name.
"""
from __future__ import annotations

import re
from typing import Any

from .chat_context import scholarship_student_facts
from .section_grounding import is_personal_skill


_LABELLED_NAME = re.compile(
    r"(?m)(?:^|\]|\|)\s*(?:申请人姓名|学生姓名|姓名|申请人)\s*(?:[：:=]|\|)\s*"
    r"([\u4e00-\u9fffA-Za-z·]{2,24})(?=\s*(?:\||[，,；;。！？!?（(\r\n]|$))"
)
_NAME = re.compile(r"[\u4e00-\u9fffA-Za-z·]{2,24}")


def _applicant_name(project: dict[str, Any], history: list[dict[str, Any]]) -> str | None:
    # Use only explicitly self-reported user messages and explicitly confirmed
    # project fields; never infer the applicant from an assistant's message.
    profile, conflicted = scholarship_student_facts(history, "", [], project_id=str(project.get("id") or ""))
    if conflicted and not profile.get("姓名"):
        return None
    candidates = [profile.get("姓名")]
    confirmed = (project.get("state") or {}).get("confirmed_facts") or {}
    if isinstance(confirmed, dict):
        candidates.extend(confirmed.get(key) for key in ("name", "applicant_name"))
    valid = {name.strip().casefold() for name in candidates
             if isinstance(name, str) and _NAME.fullmatch(name.strip())}
    return next(iter(valid)) if len(valid) == 1 else None


def filter_personal_evidence(
    skill: dict[str, Any], project: dict[str, Any], history: list[dict[str, Any]],
    documents: list[dict[str, Any]], evidence: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Return filtered search results and excluded document IDs.

    Only confirmed source documents with explicit conflicting name labels are
    removed; school notices, reference texts, unlabeled material, and cases
    where the applicant is unknown stay available for the existing workflow.
    """
    applicant = _applicant_name(project, history) if is_personal_skill(skill) and skill.get("id") != "class-collective" else None
    if not applicant:
        return evidence, []
    project_id = str(project.get("id") or "")
    excluded = []
    for doc in documents:
        if (not project_id or doc.get("project_id") != project_id or doc.get("kind") != "source"
                or not doc.get("confirmed") or doc.get("confirmation_origin") != "user"):
            continue
        text = doc.get("extracted_text")
        if not isinstance(text, str) or len(text) > 100_000:
            continue
        names = {match.group(1).casefold() for match in _LABELLED_NAME.finditer(text)}
        if names and names != {applicant} and doc.get("id"):
            excluded.append(str(doc["id"]))
    if not excluded:
        return evidence, []
    removed = set(excluded)
    results = evidence.get("results") or []
    filtered = {**evidence, "results": [item for item in results if str(item.get("document_id") or "") not in removed]}
    return filtered, excluded
