"""Explicit, model-free recovery of chapter drafts from the current project's chat."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

OPEN = re.compile(r"<WritingBlock\b[^<>]{0,300}>", re.I)
CLOSE = re.compile(r"</WritingBlock\s*>", re.I)
HEADING = re.compile(r"\A\s*#{1,3}\s+([^\n]{1,160})\n+")
ORDINAL = re.compile(r"^\s*(?:[一二三四五六七八九十百]+|\d+)[、.．）)]\s*")
MAX_CONTENT = 30_000


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def title_key(title: str) -> str:
    return re.sub(r"\s+", "", ORDINAL.sub("", title.strip())).casefold()


def candidates(project: dict, messages: list[dict]) -> list[dict]:
    """Take the latest complete version per heading, never trust reused block IDs.

    Some historical responses contain concatenated cumulative snapshots. For each
    closing tag, use the last valid opening tag, not a greedy nested block.
    Incomplete blocks are deliberately not imported.
    """
    latest = {}
    outline = {title_key(s["title"]): s for s in project.get("outline", [])}
    for message in messages:
        if message.get("role") != "assistant":
            continue
        raw = message.get("content", "")
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
            key = title_key(title)
            existing = outline.get(key)
            sid = existing["id"] if existing else "chat_" + fingerprint(key)[:16]
            previous = str(project.get("sections", {}).get(sid) or "")
            identifier = fingerprint([raw, title, body])
            imported = project.get("state", {}).get("_chat_draft_sources", {}).get(sid, {}).get("candidate") == identifier
            latest[key] = {
                "id": identifier,
                "section_id": sid,
                "title": title,
                "content": body,
                "already_saved": previous.strip() == body.strip() or imported,
                "conflict": bool(previous.strip() and previous.strip() != body.strip() and not imported),
                "warnings": ["含界面标记，请先在下方编辑框核对清理。"]
                if re.search(r"<(?:box|row|button|radio|text)\b|\{@body|GenUI\.", body) else [],
            }
    return list(latest.values())[-40:]


def review(store, project: dict) -> dict:
    messages = store.messages(project["id"], limit=200)
    items = candidates(project, messages)
    return {
        "snapshot": fingerprint([project.get("material_revision", 0),
                                 project.get("outline"), project.get("sections"),
                                 [item["id"] for item in items]]),
        "items": items,
        "notice": "仅整理最近 200 条对话中的完整章节草稿，不调用模型、不扣积分。请核对后明确保存；不会自动确认项目事实。",
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
            raise HTTPException(409, "项目或对话已变化，请重新预览；尚未覆盖任何正文。")
        available = {item["id"]: item for item in current["items"]}
        if len({item.id for item in payload.items}) != len(payload.items):
            raise HTTPException(422, "不能重复选择同一章节")
        outline, sections, state = (deepcopy(project[k]) for k in ("outline", "sections", "state"))
        sources = dict(state.get("_chat_draft_sources", {}))
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
                raise HTTPException(409, f"“{item['title']}”已有不同正文，未覆盖；请在章节编辑器手动核对合并。")
            if not any(s["id"] == sid for s in outline):
                outline.append({"id": sid, "title": item["title"]})
            sections[sid] = content
            sources[sid] = {"candidate": item["id"], "source": "user_confirmed_chat_draft"}
        state.update(outline_confirmed=True, _chat_draft_sources=sources)
        saved = store.update_project(project_id, expected_revision=project.get("material_revision", 0),
                                     outline=outline, sections=sections, state=state)
        if not saved:
            raise HTTPException(409, "项目已变化，未保存，请重新预览")
        return {"saved": len(payload.items), "material_revision": saved["material_revision"],
                "notice": "所选章节已保存；原聊天保留，项目事实未自动改写。"}

    app.include_router(router)
