"""Explicit, model-free recovery of chapter drafts from the current project's chat."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .chat_safety import INCOMPLETE_DRAFT_PREFIX, PERSONAL_NUMBER_REVIEW_PREFIX, PROJECT_CLAIM_REVIEW_PREFIX

OPEN = re.compile(r"<WritingBlock\b[^<>]{0,300}>", re.I)
CLOSE = re.compile(r"</WritingBlock\s*>", re.I)
HEADING = re.compile(r"\A\s*#{1,3}\s+([^\n]{1,160})\n+")
ORDINAL = re.compile(
    r"^\s*(?:[一二三四五六七八九十百]+[、.．）)]\s*"
    r"|\d{1,2}(?:[.．]\d{1,2}){1,3}(?:[、.．）)]\s*|\s+)"
    r"|\d{1,3}(?:[、）)]\s*|[.．](?=\s|[^\d])\s*))"
)
MAX_CONTENT = 30_000
LETTER_TITLE = re.compile(r"(?m)^\s*(?:#{1,3}\s*)?([\u4e00-\u9fffA-Za-z0-9·（）() ]{2,38}(?:申请书|个人陈述))\s*$")
LETTER_SALUTATION = re.compile(r"\A\s*尊敬的[^\n：:]{1,35}[：:]")
LETTER_END = re.compile(r"(?m)^\s*(?:此致\s*)?敬礼\s*[！!]?[ \t]*$")
LETTER_SIGNATURE = re.compile(r"^\s*(?:(?:申请人|申请学生|姓名|日期|申请日期)\s*[：:]\s*[^\n]{0,80}|\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)\s*$")
PROJECT_HEADING = re.compile(r"(?m)^[ \t]*#{1,3}[ \t]+([^\n]{2,80})[ \t]*$")
PROJECT_CHAPTERS = frozenset({
    "摘要", "项目摘要", "项目简介", "项目概述", "作品简介", "研究目标", "项目目标", "项目背景", "研究背景", "立项背景", "立项依据",
    "研究内容", "项目内容", "研究方案", "实施方案", "研究方法", "技术路线", "创新点", "可行性分析",
    "预期成果", "预期产出", "进度安排", "项目预算", "经费预算", "团队基础", "已有基础",
    "市场分析", "市场与用户分析", "产品与服务", "产品或服务", "商业模式", "商业模式与运营计划", "运营计划", "团队介绍",
    "调研背景", "调查背景", "调研背景与问题", "调查背景与问题", "调研目标", "调查目标",
    "调研目标与对象", "调查目标与对象", "调研对象", "调查对象", "调研方法", "调查方法",
    "调研内容与方法", "调查内容与方法", "调查设计", "调研设计", "问卷设计", "实施计划与日程",
    "团队分工与准备", "安全保障", "安全保障与应急安排", "调研安排", "实践计划", "实施计划",
})


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def title_key(title: str) -> str:
    return re.sub(r"\s+", "", ORDINAL.sub("", title.strip())).casefold()


def plain_application_letter(raw: str, last_user_text: str) -> tuple[str, str] | None:
    """Recover only a complete application letter after an explicit request.

    Explanation, examples, incomplete model markup and surrounding advice are
    not imported. All candidates still require the student's confirmation.
    """
    if not isinstance(raw, str) or not isinstance(last_user_text, str) or OPEN.search(raw) or CLOSE.search(raw):
        return None
    from .chat_context import _is_personal_draft_request
    if not _is_personal_draft_request(last_user_text, r"(?:申请书|个人陈述)"):
        return None
    headings = list(LETTER_TITLE.finditer(raw))
    if len(headings) != 1 or re.search(r"示例|范文|例如|举例|虚构|假设|```", raw[:headings[0].start()]):
        return None
    heading = headings[0]
    text = raw[heading.end():].strip()
    if not LETTER_SALUTATION.match(text):
        return None
    end = LETTER_END.search(text)
    if not end or "此致" not in text[:end.end()] or end.end() > MAX_CONTENT:
        return None
    body = text[:end.end()].strip()
    # Keep only explicit sign-off lines, never the model's later suggestions.
    for line in text[end.end():].splitlines():
        if not line.strip():
            continue
        if not LETTER_SIGNATURE.fullmatch(line):
            break
        body += "\n" + line.strip()
    if len(body) < 50 or len(body) > MAX_CONTENT:
        return None
    return heading.group(1).strip(), body


def plain_project_chapters(raw: str, last_user_text: str, project: dict) -> list[tuple[str, str]]:
    """Offer complete project sections only after a direct writing request.

    The student must review and confirm each candidate. Advice, samples,
    partial markup, and incomplete final sentences are never imported.
    """
    category = (project.get("state") or {}).get("skill_category", "")
    skill_id = (project.get("state") or {}).get("skill_id", "")
    from .skills import registry
    if not category:
        category = (registry.get(skill_id) or {}).get("category", "")
    if category not in {"research", "competition", "practice"}:
        return []
    if not isinstance(raw, str) or not isinstance(last_user_text, str) or OPEN.search(raw) or CLOSE.search(raw):
        return []
    if re.search(r"```", raw):
        return []
    if re.search(r"怎么写|如何写|怎样写|写作(?:建议|方法|思路)|(?:不要|别|不必|无需|不用|暂不)(?:帮我|再|先|直接)?(?:写|撰写|起草|生成)", last_user_text):
        return []
    if not re.search(r"(?:起草|撰写|编写|写一份|写一段|帮我写|请写|直接写|生成(?:一份|一段|正文|草稿)|整理成文)", last_user_text):
        return []
    all_headings = list(PROJECT_HEADING.finditer(raw))
    # Only the introduction can label the whole response as a sample. A real
    # draft may mention examples inside a paragraph, such as a placeholder
    # illustrating an unspecified date; that alone should not make the
    # entire response unavailable for review.
    if not all_headings:
        return []
    known = {title_key(title) for title in PROJECT_CHAPTERS}
    known.update(title_key(str(item.get("title") or "")) for item in (project.get("outline") or []) if isinstance(item, dict))
    recognized = [match for match in all_headings if title_key(match.group(1)) in known]
    if not recognized or re.search(r"示例|范文|例如|举例|虚构|假设", raw[:recognized[0].start()]):
        return []
    # A level-three heading belongs inside the level-two chapter, rather than
    # accidentally ending the chapter and leaving it empty. Older outputs
    # whose peer chapters all use level three are still supported.
    level = min(len(match.group().lstrip().split(None, 1)[0]) for match in recognized)
    headings = [match for match in all_headings if len(match.group().lstrip().split(None, 1)[0]) <= level]
    if not headings:
        return []
    result = []
    for index, match in enumerate(headings):
        title = ORDINAL.sub("", match.group(1).strip()).strip()
        if title_key(title) not in known:
            continue
        if re.search(r"(?:不要|别|无需|不必)(?:写|生成|起草).{0,5}" + re.escape(title), last_user_text):
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(raw)
        body = raw[match.end():end].strip()
        # The model may append a separate chat follow-up after the final draft.
        body = re.split(r"\n\s*\n(?=(?:请确认|如需|如果你|如有|接下来我|希望以上))", body, maxsplit=1)[0].strip()
        # Markdown horizontal rules delimit a finished chapter; they are not
        # part of its last sentence and must not make a complete draft look cut off.
        body = re.sub(r"(?m)\n[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$", "", body).strip()
        # Do not promote a stand-alone example or example subsection to the
        # student's document. Inline examples remain explicitly reviewable.
        if re.match(r"(?:以下|下面|这是|仅供参考).{0,12}(?:示例|范文|举例|虚构|假设)", body) or re.search(
            r"(?m)^\s*#{1,4}\s*[^\n]{0,40}(?:示例|范文|示范|虚构案例)", body
        ):
            continue
        if not 30 <= len(body) <= MAX_CONTENT:
            continue
        if re.match(r"(?:你可以|您可以|建议你|建议您|写作时|以下是(?:建议|步骤|要点))", body):
            continue
        # A complete Markdown table legitimately ends in a vertical bar.
        # Require an alignment row and at least one subsequent data row.
        table_end = bool(re.search(
            r"(?m)^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*\n"
            r"(?:[ \t]*\|[^\n]+\|[ \t]*(?:\n|\Z))+\Z", body
        ))
        if (not re.search(r"[。！？.!?）)]$", body) and not table_end) or re.search(r"(?:\.\.\.|…|未完待续)[。.!！]?$", body):
            continue
        result.append((title, body))
    return result


def split_project_writing_block(content: str, project: dict) -> list[tuple[str, str]]:
    """Split clearly identifiable peer ``#`` or ``##`` chapters.

    Ambiguous, duplicated, truncated or excessive headings remain as the
    original single block. Preserve subheadings; fenced code is never a chapter.
    """
    headings: list[tuple[int, int, str]] = []
    fence: tuple[str, int] | None = None
    peer_level: int | None = None
    offset = 0
    for line in content.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        marker = re.match(r"^[ \t]*(`{3,}|~{3,})", bare)
        if marker:
            current = marker.group(1)
            if fence is None:
                fence = (current[0], len(current))
            elif current[0] == fence[0] and len(current) >= fence[1] and not bare[marker.end():].strip():
                fence = None
        elif fence is None:
            match = re.match(r"^[ \t]*(#{1,3})[ \t]+([^\n]{1,160}?)[ \t]*$", bare)
            if match:
                level = len(match.group(1))
                if peer_level is None:
                    if level not in {1, 2}:
                        return []
                    peer_level = level
                if level < peer_level:
                    # A later higher-level heading changes the hierarchy, so
                    # we cannot confidently identify the peer chapters.
                    return []
                if level == peer_level:
                    headings.append((offset, offset + len(line), match.group(2).strip()))
        offset += len(line)
    if fence is not None or len(headings) < 2 or len(headings) > 20 or content[:headings[0][0]].strip():
        return []
    outline = project.get("outline") or []
    existing = {title_key(str(item.get("title") or "")) for item in outline if isinstance(item, dict)}
    recognized = {title_key(title) for title in PROJECT_CHAPTERS} | existing
    names = [ORDINAL.sub("", title).strip() for _, _, title in headings]
    keys = [title_key(title) for title in names]
    if any(not key or key not in recognized for key in keys) or len(set(keys)) != len(keys):
        return []
    # Avoid expanding an already substantial directory beyond its UI/API cap.
    if len(outline) + sum(key not in existing for key in keys) > 20:
        return []
    sections: list[tuple[str, str]] = []
    for index, (_, end, _) in enumerate(headings):
        boundary = headings[index + 1][0] if index + 1 < len(headings) else len(content)
        body = content[end:boundary].strip()
        if not body or re.search(r"(?:\.{3,}|…+|未完待续|[：:])\s*$", body):
            return []
        sections.append((names[index], body))
    return sections


def candidates(project: dict, messages: list[dict]) -> list[dict]:
    """Take the latest complete version per heading, never trust reused block IDs.

    Some historical responses contain concatenated cumulative snapshots. For each
    closing tag, use the last valid opening tag, not a greedy nested block.
    Incomplete blocks are deliberately not imported.
    """
    latest = {}
    outline = {title_key(s["title"]): s for s in project.get("outline", [])}
    state = project.get("state") or {}
    from .skills import registry
    skill = registry.get(str(state.get("skill_id") or "")) or {}
    project_candidate = (state.get("skill_category") or skill.get("category")) in {"research", "competition", "practice"}
    last_user_text = ""
    for message in messages:
        if message.get("role") == "user":
            last_user_text = message.get("content", "")
            continue
        if message.get("role") != "assistant":
            continue
        raw = message.get("content", "")
        if not isinstance(raw, str):
            continue
        if raw.startswith((PERSONAL_NUMBER_REVIEW_PREFIX, INCOMPLETE_DRAFT_PREFIX)):
            # Do not fall back to an earlier version after the student asked
            # for a new draft whose personal numbers need manual attention.
            latest.clear()
            continue
        project_review = raw.startswith(PROJECT_CLAIM_REVIEW_PREFIX)
        project_review_warning = "项目数据或成果需要逐项核对，修改后再选择保存。"
        if project_review:
            # Prefer the latest result requiring review over silently using an
            # older, potentially unrelated version of the student's request.
            latest.clear()
            match = re.match(re.escape(PROJECT_CLAIM_REVIEW_PREFIX) + r"([^）\n]{1,120})）", raw)
            if match:
                project_review_warning = f"请核对并修改：{match.group(1)}。"
        found = []
        cursor = 0
        for closing in CLOSE.finditer(raw):
            openings = list(OPEN.finditer(raw, cursor, closing.start()))
            cursor = closing.end()
            if not openings:
                continue
            content = raw[openings[-1].end():closing.start()].strip()
            heading = HEADING.match(content)
            if not heading or len(content) > MAX_CONTENT:
                continue
            title = ORDINAL.sub("", heading[1].strip())
            body = content[heading.end():].strip()
            if not body:
                continue
            # Some models place several peer chapters inside one block.
            # Split only when their structure is unambiguous; otherwise keep
            # the original text together for the student's review.
            split = split_project_writing_block(content, project) if project_candidate else []
            found.extend(split or [(title, body)])
        if not found:
            letter = plain_application_letter(raw, last_user_text)
            if letter:
                found.append(letter)
            else:
                found.extend(plain_project_chapters(raw, last_user_text, project))
        for title, body in found:
            key = title_key(title)
            existing = outline.get(key)
            sid = existing["id"] if existing else "chat_" + fingerprint(key)[:16]
            previous = str(project.get("sections", {}).get(sid) or "")
            identifier = fingerprint([raw, title, body])
            # Import provenance records a past confirmation, not the presence
            # of a current chapter. Clearing/removing it must leave a path to
            # explicitly restore the chat draft rather than disabling it.
            in_outline = existing is not None
            imported = bool(in_outline and previous.strip()
                            and project.get("state", {}).get("_chat_draft_sources", {}).get(sid, {}).get("candidate") == identifier)
            latest[key] = {
                "id": identifier,
                "section_id": sid,
                "title": title,
                "content": body,
                "already_saved": bool(in_outline and previous.strip()
                                      and (previous.strip() == body.strip() or imported)),
                "conflict": bool(previous.strip() and previous.strip() != body.strip() and not imported),
                # A real model test added unprovided team and project claims
                # without any numbers. Do not preselect generated project
                # drafts until the student has reviewed their substance.
                "requires_review": project_review or project_candidate,
                "warnings": ([project_review_warning] if project_review else [])
                + (["请检查项目方案、进展和数据，再勾选保存。"] if project_candidate and not project_review else [])
                + (["正文包含举例，请按项目实际情况检查并修改。"]
                   if project_candidate and re.search(r"示例|范文|例如|举例|虚构|假设", body) else [])
                + (["含界面标记，请先在下方编辑框核对清理。"]
                   if re.search(r"<(?:box|row|button|radio|text)\b|\{@body|GenUI\.", body) else []),
            }
    return list(latest.values())[-40:]


def review(store, project: dict) -> dict:
    messages = store.messages(project["id"], limit=200)
    items = candidates(project, messages)
    # Legacy document updates do not always advance the project revision.
    # Include their review-relevant state without exposing material contents in
    # the snapshot returned to the browser.
    documents = sorted((
        (str(doc.get("id") or ""), doc.get("original_name"), doc.get("kind"),
         doc.get("confirmed"), doc.get("confirmation_origin"),
         doc.get("extraction_status"), doc.get("extraction_warning"),
         doc.get("low_confidence_count"),
         hashlib.sha256(str(doc.get("extracted_text") or "").encode()).hexdigest())
        for doc in store.list_documents(project["id"])
    ), key=lambda doc: doc[0])
    return {
        "snapshot": fingerprint([project.get("material_revision", 0),
                                 project.get("outline"), project.get("sections"),
                                 documents,
                                 [item["id"] for item in items],
                                 [(message.get("role"), message.get("content")) for message in messages]]),
        "items": items,
        "notice": "选择需要保存的草稿，也可以先在下方修改内容。",
    }


def require_export_content(project: dict, allow_empty: bool = False) -> None:
    if allow_empty:
        return
    if not any(str(project.get("sections", {}).get(s["id"]) or "").strip()
               for s in project.get("outline", [])):
        raise ValueError("尚无已保存的章节正文。请先点击“从对话整理草稿”核对并保存；如确需空白草稿，请明确确认。")


class DraftSelection(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{64}$")
    content: str | None = Field(default=None, max_length=MAX_CONTENT)
    replace_existing: bool = False


class DraftConfirmation(BaseModel):
    snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")
    items: list[DraftSelection] = Field(min_length=1, max_length=40)


def register_chat_drafts(app, get_store):
    router = APIRouter(prefix="/api/projects/{project_id}/chat-drafts")

    def owned_project(project_id):
        store = get_store()
        project = store.get_project(project_id)  # Supabase current-user JWT / RLS.
        if not project:
            raise HTTPException(404, "项目不存在")
        return store, project

    @router.get("")
    def preview(project_id: str):
        store, project = owned_project(project_id)
        return review(store, project)

    @router.post("/confirm")
    def confirm(project_id: str, payload: DraftConfirmation):
        store, project = owned_project(project_id)
        current = review(store, project)
        if payload.snapshot != current["snapshot"]:
            raise HTTPException(409, "项目、材料或对话已变化，请重新预览；尚未覆盖任何正文。")
        available = {item["id"]: item for item in current["items"]}
        if len({item.id for item in payload.items}) != len(payload.items):
            raise HTTPException(422, "不能重复选择同一章节")
        outline, sections, state = (deepcopy(project[k]) for k in ("outline", "sections", "state"))
        sources = dict(state.get("_chat_draft_sources", {}))
        backups = []
        total = 0
        for selected in payload.items:
            item = available.get(selected.id)
            if not item:
                raise HTTPException(409, "草稿版本已变化，请重新预览")
            content = (selected.content if selected.content is not None else item["content"]).strip()
            if not content:
                raise HTTPException(422, "选中章节的正文不能为空")
            total += len(content)
            if total > 1_000_000:
                raise HTTPException(413, "所选正文过大，请分批保存")
            sid = item["section_id"]
            old = str(sections.get(sid) or "")
            if old.strip() and old.strip() != content:
                if not selected.replace_existing:
                    raise HTTPException(409, f"“{item['title']}”已有不同正文，请明确选择替换后再保存。")
                backups.append((sid, old))
            if not any(s["id"] == sid for s in outline):
                if len(outline) >= 20:
                    raise HTTPException(422, "目录最多支持 20 个章节，请先调整目录后再保存新草稿。")
                outline.append({"id": sid, "title": item["title"]})
            sections[sid] = content
            sources[sid] = {"candidate": item["id"], "source": "user_confirmed_chat_draft"}
        state.update(outline_confirmed=True, _chat_draft_sources=sources)
        # Preserve the previous version before replacing it. A failed backup or
        # revision conflict must never overwrite the student's current text.
        for sid, old in backups:
            store.save_section_version(project_id, sid, old, source="before_chat_replacement")
        from .materials import MaterialConflict
        try:
            saved = store.update_project(project_id, expected_revision=project.get("material_revision", 0),
                                         outline=outline, sections=sections, state=state)
        except MaterialConflict as exc:
            raise HTTPException(409, "项目已变化，未保存，请重新预览。") from exc
        if not saved:
            raise HTTPException(409, "项目已变化，未保存，请重新预览")
        return {"saved": len(payload.items), "material_revision": saved["material_revision"],
                "notice": "草稿已保存。"}

    app.include_router(router)
