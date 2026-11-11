"""One conversation loop shared by synchronous and streaming chat."""
from __future__ import annotations

import json
import re
from time import monotonic
from typing import Any, Iterator

from .agent import ModelUnavailable
from .chat_context import (OUTSTANDING_CLARIFICATION, ambiguous_confirmation, conversation_messages, fallback_scholarship_draft,
                           final_text, grant_placeholder_draft, is_grant_draft_request,
                           is_outstanding_draft_request, outstanding_student_category, outstanding_student_draft,
                           outstanding_student_omissions,
                           is_scholarship_draft_request, is_scholarship_placeholder_request,
                           is_scholarship_preparation_request,
                           scholarship_placeholder_draft, scholarship_preparation_reply,
                           scholarship_student_facts, without_policy_claims)
from .chat_model import model_events
from .chat_safety import INCOMPLETE_DRAFT_PREFIX, PERSONAL_NUMBER_REVIEW_PREFIX, PROJECT_CLAIM_REVIEW_PREFIX
from .chat_tools import CHAT_TOOLS, TOOL_LABELS, ChatToolRouter
from .knowledge import has_writing_intent, mixed_drafting_request
from .transfer_draft import is_transfer_draft_request, transfer_draft, transfer_student_facts
from .graduate_draft import is_graduate_draft_request, graduate_placeholder_draft

MAX_TOOL_CALLS_PER_TURN = 8
BUFFERED_PROGRESS_INTERVAL_SECONDS = 6
READ_ONLY_CACHED_TOOLS = frozenset({
    "get_project_state", "get_writing_guidance", "search_project_materials", "search_public_knowledge",
    "search_papers", "search_official_notices", "fetch_official_notice", "validate_project",
    "list_available_skills", "load_skill_guidance",
})
from .motivation_draft import is_motivation_draft_request, motivation_placeholder_draft, motivation_student_facts


def _project_issues(skill, project, history, documents, content):
    from .project_claims import unsupported_project_numbers
    from .project_contradictions import project_fact_contradictions
    from .project_reference_safety import unsupported_project_references
    from .project_team_safety import unsupported_project_team_claims
    from .social_survey_quality import unsupported_survey_table_counts
    return list(dict.fromkeys([
        *unsupported_project_numbers(skill, project, history, documents, content),
        *project_fact_contradictions(skill, project, history, documents, content),
        *unsupported_project_references(skill, project, history, documents, content),
        *unsupported_project_team_claims(skill, project, history, documents, content),
        *unsupported_survey_table_counts(skill, project, history, documents, content),
    ]))


def _complete_project_blocks(project, text: str, user_text: str) -> str:
    """Recover closed blocks and chapters followed by another peer heading."""
    from .chat_drafts import (OPEN, CLOSE, PROJECT_HEADING, PROJECT_CHAPTERS,
                              candidates, plain_project_chapters, title_key)
    blocks: list[str] = []
    cursor = 0
    for closing in CLOSE.finditer(text):
        openings = list(OPEN.finditer(text, cursor, closing.start()))
        preamble = text[cursor:openings[-1].start()] if openings else ""
        cursor = closing.end()
        if not openings:
            continue
        if re.search(r"示例|范文|举例|假设|虚构", preamble):
            continue
        block = text[openings[-1].start():closing.end()]
        if len(block) <= 30_300 and candidates(project, [{"role": "assistant", "content": block}]):
            blocks.append(block)
        if len(blocks) >= 20:
            break
    # Models often put several chapters in one still-open WritingBlock. A
    # later peer heading can establish the boundary of a preceding chapter;
    # the final, possibly truncated chapter is never treated as complete.
    tail = text[cursor:]
    openings = list(OPEN.finditer(tail))
    if len(blocks) < 20 and openings and not re.search(r"示例|范文|举例|假设|虚构", tail[:openings[-1].start()]):
        fragment = tail[openings[-1].end():]
        headings = list(PROJECT_HEADING.finditer(fragment))
        known = {title_key(title) for title in PROJECT_CHAPTERS}
        known.update(title_key(str(item.get("title") or "")) for item in (project.get("outline") or []) if isinstance(item, dict))
        first = next((heading for heading in headings if title_key(heading.group(1)) in known), None)
        if first:
            level = len(first.group().lstrip().split(None, 1)[0])
            peers = [heading for heading in headings if len(heading.group().lstrip().split(None, 1)[0]) <= level]
            if len(peers) >= 2:
                completed = fragment[:peers[-1].start()]
                for title, body in plain_project_chapters(completed, user_text, project):
                    blocks.append(f'<WritingBlock variant="document">\n## {title}\n\n{body}\n</WritingBlock>')
                    if len(blocks) >= 20:
                        break
    return "\n\n".join(blocks)


class ChatRuntime:
    """Run one turn without owning the model transport, storage, or billing."""

    def __init__(self, agent: Any):
        self.agent = agent
        self.store = agent.store
        self.tools = agent.tools

    @staticmethod
    def _answer(text: str, called: list[str], model: str, stream: bool) -> Iterator[dict[str, Any]]:
        if stream:
            yield {"type": "delta", "text": text}
        yield {"type": "done", "message": text, "tool_calls": called, "model": model}

    def run(self, project_id: str, user_text: str, *, stream: bool) -> Iterator[dict[str, Any]]:
        project = self.store.get_project(project_id)
        if not project:
            if stream:
                yield {"type": "error", "error": "找不到这个项目。"}
                return
            raise ValueError("找不到这个项目。")

        # Snapshot history before appending the current message: do not assume
        # a second database read returns this request's message last.
        history = self.store.messages(project_id, limit=200)
        self.store.add_message(project_id, "user", user_text)
        if ambiguous_confirmation(history, user_text):
            text = "你刚才回复“确认”，但我上一条问的是需要区分的选项。我不能替你猜。请直接说明你选择哪一种，或补充具体条件。"
            self.store.add_message(project_id, "assistant", text)
            yield from self._answer(text, [], self.agent.model, stream)
            return

        draft_request = mixed_drafting_request(user_text)
        policy_reply = self.agent._policy_evidence_reply(project_id, user_text)
        previous_assistant = next((item["content"] for item in reversed(history) if item.get("role") == "assistant"), "")
        if is_motivation_draft_request(draft_request or user_text, project):
            facts, conflicted, omitted = motivation_student_facts(
                history, user_text, self.store.list_documents(project_id), project_id=project_id,
            )
            text = motivation_placeholder_draft(facts, conflicted=conflicted, omitted=omitted)
            called = []
            if policy_reply is not None:
                text = f"【政策资料核查】\n{policy_reply}\n\n【写作内容】\n{text}"
                called.append("search_public_knowledge")
            self.store.add_message(project_id, "assistant", text)
            yield from self._answer(text, called, "evidence-only", stream)
            return
        if is_transfer_draft_request(draft_request or user_text, project):
            facts, conflicted, omitted = transfer_student_facts(history, user_text)
            text = transfer_draft(facts, conflicted=conflicted, omitted=omitted)
            called = []
            if policy_reply is not None:
                text = f"【政策资料核查】\n{policy_reply}\n\n【写作内容】\n{text}"
                called.append("search_public_knowledge")
            self.store.add_message(project_id, "assistant", text)
            yield from self._answer(text, called, "evidence-only", stream)
            return
        graduate_docs = self.store.list_documents(project_id) if (project.get("state") or {}).get("skill_id") == "graduate-recommendation" else []
        if is_graduate_draft_request(draft_request or user_text, project, documents=graduate_docs, history=history):
            text = graduate_placeholder_draft(history, user_text, graduate_docs,
                                              project_id=project_id)
            called = []
            if policy_reply is not None:
                text = f"【政策资料核查】\n{policy_reply}\n\n【写作内容】\n{text}"
                called.append("search_public_knowledge")
            self.store.add_message(project_id, "assistant", text)
            yield from self._answer(text, called, "evidence-only", stream)
            return
        if is_outstanding_draft_request(draft_request or user_text, project, previous_assistant):
            category = outstanding_student_category(history, user_text)
            if category is None:
                self.store.add_message(project_id, "assistant", OUTSTANDING_CLARIFICATION)
                yield from self._answer(OUTSTANDING_CLARIFICATION, [], "evidence-only", stream)
                return
            facts, conflicted = scholarship_student_facts(history, user_text, self.store.list_documents(project_id),
                                                         project_id=project_id, field_level_grade_omission=True)
            text = outstanding_student_draft(category, facts, conflicted=conflicted,
                                             omitted=outstanding_student_omissions(history, user_text))
            called = []
            if policy_reply is not None:
                text = f"【政策资料核查】\n{policy_reply}\n\n【写作内容】\n{text}"
                called.append("search_public_knowledge")
            self.store.add_message(project_id, "assistant", text)
            yield from self._answer(text, called, "evidence-only", stream)
            return
        grant_draft = is_grant_draft_request(draft_request or user_text, project)
        scholarship_draft = is_scholarship_draft_request(draft_request or user_text, project)
        scholarship_placeholder = is_scholarship_placeholder_request(draft_request or user_text, project)
        if scholarship_placeholder or grant_draft:
            # Rebuild only from bounded user messages and confirmed, clearly
            # matching personal materials, never from model-generated history.
            facts, conflicted = scholarship_student_facts(history, user_text, self.store.list_documents(project_id),
                                                         include_family_income=grant_draft, project_id=project_id)
            text = (grant_placeholder_draft(facts=facts, conflicted=conflicted) if grant_draft
                    else scholarship_placeholder_draft(user_text, facts=facts, conflicted=conflicted))
            if is_scholarship_preparation_request(user_text, project):
                text += "\n\n" + scholarship_preparation_reply()
            called = []
            if policy_reply is not None:
                text = f"【政策资料核查】\n{policy_reply}\n\n【写作内容】\n{text}"
                called.append("search_public_knowledge")
            self.store.add_message(project_id, "assistant", text)
            yield from self._answer(text, called, "evidence-only", stream)
            return
        if is_scholarship_preparation_request(user_text, project) and not scholarship_draft:
            text = scholarship_preparation_reply()
            called = []
            if policy_reply is not None:
                text = f"【政策资料核查】\n{policy_reply}\n\n{text}"
                called.append("search_public_knowledge")
            self.store.add_message(project_id, "assistant", text)
            yield from self._answer(text, called, "evidence-only", stream)
            return
        if policy_reply is not None and draft_request is None:
            if has_writing_intent(user_text):
                policy_reply += "\n\n你的写作请求还没有执行。请把具体写作要求单独发来，我会继续处理。"
            self.store.add_message(project_id, "assistant", policy_reply)
            yield from self._answer(policy_reply, ["search_public_knowledge"], "evidence-only", stream)
            return

        model_project = project
        if draft_request and policy_reply is not None:
            # A newly routed project's initial_request may contain the whole
            # mixed question; do not smuggle the policy clause back into the
            # writing model through saved setup fields.
            model_state = dict(project.get("state") or {})
            model_state.pop("initial_request", None)
            model_state.pop("template_answer", None)
            model_project = {**project, "state": model_state}
        messages = conversation_messages(self.agent, model_project, project_id, history, draft_request or user_text,
                                         original_user_text=user_text)
        if scholarship_draft:
            from .scholarship_writing import scholarship_writing_context
            facts, conflicted = scholarship_student_facts(
                history, user_text, self.store.list_documents(project_id), project_id=project_id,
            )
            messages[0]["content"] += scholarship_writing_context(history, user_text, facts, conflicted=conflicted)
        # Personal rewrites and questions about a student's own figures must be
        # checked before display. Other chats continue to stream normally.
        from .section_grounding import is_personal_skill
        from .skills import registry
        skill = registry.get(str((project.get("state") or {}).get("skill_id") or ""))
        from .project_writing import (is_explicit_project_draft, project_sources_allowed,
                                      explicit_public_lookup, project_draft_guidance)
        project_draft = is_explicit_project_draft(draft_request or user_text, skill)
        project_check = bool(skill and skill.get("category") in {"research", "competition", "practice"}
                             and (project_draft or has_writing_intent(user_text)))
        if project_draft:
            messages[0]["content"] += (
                "\n学生已明确要求写正文：先根据已提供的信息输出其要求的可编辑章节，"
                "不要以索要模板、联系方式、资料清单或等待目录确认为由替代正文。"
                "未知事实留【待补充】；学生未选定的技术、调研或商业方案只能明确作为可选建议，"
                "不能写成已经确定或已经取得的成果。"
            )
            messages[0]["content"] += project_draft_guidance(str((project.get("state") or {}).get("skill_id") or ""))
            messages[-1]["content"] += (
                "\n请先直接写我要求的正文，用 <WritingBlock variant=\"document\"> 包裹，"
                "以二级标题开头；缺少的事实写【待补充】，不要先列信息清单。"
            )
        personal_check = bool(skill and is_personal_skill(skill) and (
            draft_request or has_writing_intent(user_text)
            or re.search(r"润色|改写|修改|优化|纠错|校对|扩写|续写|起草|撰写|写正文|写申请书|整理.{0,8}(?:经历|材料|表现|成绩)", user_text)
            or (re.search(r"我|本人", user_text) and re.search(r"绩点|GPA|志愿|义工", user_text, re.I))
        ))
        if stream and (personal_check or project_check):
            yield {"type": "status", "message": "正在整理答复…"}
        router = ChatToolRouter(self.tools, project_id, project, user_text=user_text,
                                deadline=getattr(self.agent, "_execution_deadline", None))
        if scholarship_draft:
            # Profile/source filtering was done above. A directly requested
            # draft needs one authorized model response, not a search loop.
            router.schemas = []
            router.allowed.clear()
        called: list[str] = ["search_public_knowledge"] if policy_reply is not None else []
        if project_draft:
            # A direct request to write should not fan out into unrelated
            # searches or ask for the same state repeatedly. Confirmed source
            # materials remain available; public lookup stays available when
            # the student explicitly asks to search.
            source_available = any(
                doc.get("kind") == "source" and doc.get("confirmed") and doc.get("confirmation_origin") == "user"
                for doc in self.store.list_documents(project_id)
            ) and project_sources_allowed(history, user_text)
            explicit_lookup = explicit_public_lookup(user_text)
            permitted = {"search_project_materials"} if source_available else set()
            if explicit_lookup:
                permitted.update({"search_public_knowledge", "search_papers", "search_official_notices", "fetch_official_notice"})
            router.schemas = [schema for schema in router.schemas if schema["function"]["name"] in permitted]
            router.allowed.intersection_update(permitted)
            if not permitted:
                messages[0]["content"] += "\n本次直接起草无需检索工具，请利用已有信息完成正文。"
        if draft_request and policy_reply is not None:
            # The model receives only the isolated writing request. Policy facts
            # are displayed separately from deterministic, scoped retrieval.
            messages[0]["content"] += (
                "\n本轮只处理写作，不回答或推测任何资格、政策、评审条件、金额和截止日期；"
                "不要在草稿中叙述这些规则或编造相关依据。系统会另行展示已检索的政策资料。"
                "用户明确要求起草时，请直接给出符合写作要求的草稿；信息不足时用【待补充】占位，"
                "不要只列资料清单或要求用户补充后才开始写。"
            )
            messages[-1]["content"] += (
                "\n请先直接给出可编辑草稿；尚未提供或确认的个人事实用【待补充】占位。"
                "不要只列资料清单。"
            )
            disabled = {"get_project_state", "search_public_knowledge", "search_official_notices", "fetch_official_notice", "save_project_fact"}
            router.schemas = [s for s in router.schemas if s["function"]["name"] not in disabled]
            router.allowed.difference_update(disabled)
            if stream:
                yield {"type": "status", "message": "已核对相关依据，正在处理写作请求…"}
        saved_fact = False
        tool_calls_used = 0
        tool_cache: dict[str, Any] = {}
        limit_notice_added = False
        last_buffered_progress = monotonic()
        for _ in range(6):
            payload = {"model": self.agent.model, "messages": messages,
                       "tools": router.schemas if tool_calls_used < MAX_TOOL_CALLS_PER_TURN else [],
                       "options": {"temperature": 0.2}}
            if scholarship_draft:
                payload["response_profile"] = "scholarship_draft"
                payload["options"]["num_predict"] = 4096
            streamed_text = False
            message = None
            events = model_events(self.agent, project_id, payload, stream=stream)
            partial_pieces: list[str] = []
            partial_size = 0
            try:
                for event in events:
                    if event["type"] == "delta":
                        streamed_text = streamed_text or bool(event.get("text"))
                        if stream and project_draft and not draft_request and policy_reply is None:
                            piece = event.get("text") or ""
                            if partial_size + len(piece) <= 200_000:
                                partial_pieces.append(piece)
                                partial_size += len(piece)
                        if not draft_request and not personal_check and not project_check:
                            yield event
                        elif stream and event.get("text"):
                            # The draft is held back for factual checks, but a
                            # long, actively streaming model should not appear
                            # frozen. Never expose provisional text here.
                            now = monotonic()
                            if now - last_buffered_progress >= BUFFERED_PROGRESS_INTERVAL_SECONDS:
                                last_buffered_progress = now
                                yield {"type": "status", "message": "正在撰写并检查内容，请稍候…"}
                    elif event["type"] == "response":
                        message = event["message"]
            except ModelUnavailable:
                # An interrupted provider may already have returned complete
                # chapters. Keep only explicitly closed, recognizable blocks;
                # never turn a truncated answer into a complete document or
                # issue another model request automatically.
                recovered = _complete_project_blocks(project, "".join(partial_pieces), user_text) if partial_pieces else ""
                if not recovered:
                    raise
                source_history = [*history, {"role": "user", "content": user_text}]
                documents = (self.store.list_documents(project_id)
                             if project_sources_allowed(source_history, "") else [])
                issues = _project_issues(skill, project, source_history, documents, recovered)
                warning = (PROJECT_CLAIM_REVIEW_PREFIX + "、".join(issues)
                           + "），请检查并修改后，再选择保存。\n\n") if issues else ""
                text = (warning + "本次生成中断，以下是已收到的章节片段，整份材料尚未完成。"
                        "请先核对、保存已收到的内容，再继续补写；本次请求的费用状态可能仍需查看。\n\n"
                        + recovered)
                self.store.add_message(project_id, "assistant", text)
                yield {"type": "delta", "text": text}
                yield {"type": "done", "message": text, "tool_calls": called,
                       "model": self.agent.model, "incomplete": True}
                return
            finally:
                events.close()
            if message is None:
                raise ModelUnavailable("模型未能产生有效输出。")
            calls = message.get("tool_calls") or []
            if scholarship_draft and calls:
                # This path supplied no tools. Do not buy another model turn
                # merely to repair an invalid response to a writing request.
                raise ModelUnavailable("模型未返回完整申请书草稿，本次请求未完成；请先查看结果与费用状态，再决定是否重试。")
            if not calls:
                text = final_text(message.get("content"), saved_fact=saved_fact)
                if not text:
                    raise ModelUnavailable("模型未返回可用正文，本次请求未完成。")
                incomplete = scholarship_draft and message.get("finish_reason") in {"length", "max_tokens", "max_output_tokens"}
                if draft_request and policy_reply is not None:
                    text = fallback_scholarship_draft(text, draft_request, project)
                    text = without_policy_claims(text) or "写作结果含有未经核对的规则表述，已隐藏；请提供具体写作内容后继续。"
                    text = f"【政策资料核查】\n{policy_reply}\n\n【写作内容】\n{text}"
                if personal_check:
                    from .personal_claims import unsupported_personal_numbers
                    # A conversational model may describe the student in the
                    # second person, whereas chapter drafts use first person.
                    check_text = re.sub(r"你(?!们)", "我", text)
                    issues = unsupported_personal_numbers(
                        skill, project, [*history, {"role": "user", "content": user_text}],
                        self.store.list_documents(project_id) if project_sources_allowed(history, user_text) else [], check_text,
                    )
                    if issues:
                        # Keep the paid response visible for editing/copying,
                        # but don't offer it as an already-structured draft.
                        text = re.sub(r"</?WritingBlock\b[^<>]*>", "", text, flags=re.I).strip()
                        text = (PERSONAL_NUMBER_REVIEW_PREFIX + "、".join(issues)
                                + "），请先核对或删改；以下内容暂不能直接整理保存。\n\n" + text)
                if project_check:
                    source_history = [*history, {"role": "user", "content": user_text}]
                    documents = (self.store.list_documents(project_id)
                                 if project_sources_allowed(source_history, "") else [])
                    writing = text.rsplit("【写作内容】\n", 1)[-1] if draft_request and policy_reply is not None else text
                    issues = _project_issues(skill, project, source_history, documents, writing)
                    if issues:
                        text = (PROJECT_CLAIM_REVIEW_PREFIX + "、".join(issues)
                                + "），请检查并修改后，再选择保存。\n\n" + text)
                if incomplete:
                    text = re.sub(r"</?WritingBlock\b[^<>]*>", "", text, flags=re.I).strip()
                    text = (INCOMPLETE_DRAFT_PREFIX + "模型达到输出长度上限，以下是已收到的草稿片段，整份申请书尚未完成。"
                            "请先核对并复制内容，再决定是否继续补写；系统没有自动重试。\n\n" + text)
                self.store.add_message(project_id, "assistant", text)
                if stream and (draft_request or personal_check or project_check):
                    # Buffer the draft until validation; provisional text must
                    # not expose model-generated eligibility claims.
                    yield {"type": "delta", "text": text}
                yield {"type": "done", "message": text, "tool_calls": called, "model": self.agent.model,
                       **({"incomplete": True} if incomplete else {})}
                return

            # A model may emit provisional text before a tool call. Clear it
            # before the final answer so separate model steps do not concatenate.
            if stream and streamed_text and not draft_request and not personal_check and not project_check:
                yield {"type": "reset"}
            messages.append(message)
            for call in calls:
                if not isinstance(call, dict):
                    call = {}
                function = call.get("function") or {}
                name = str(function.get("name") or "") if isinstance(function, dict) else ""
                args = function.get("arguments", {}) if isinstance(function, dict) else {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = None
                cache_key = json.dumps([name, args], ensure_ascii=False, sort_keys=True) if isinstance(args, dict) else ""
                if name in READ_ONLY_CACHED_TOOLS and cache_key and cache_key in tool_cache:
                    result = tool_cache[cache_key]
                elif tool_calls_used >= MAX_TOOL_CALLS_PER_TURN:
                    result = {"error": "本轮工具调用已达到上限，请依据已有资料继续回答。"}
                else:
                    if stream:
                        yield {"type": "status", "message": TOOL_LABELS.get(name, "正在处理工具请求…")}
                    tool_calls_used += 1
                    from .execution_budget import ExecutionBudgetExceeded
                    try:
                        name, result = router.invoke(call)
                    except ExecutionBudgetExceeded as exc:
                        raise ModelUnavailable("本轮资料检索时间已用完，回复尚未完成。系统没有自动重试，请缩小检索范围后继续。") from exc
                    if name in READ_ONLY_CACHED_TOOLS and cache_key:
                        tool_cache[cache_key] = result
                if name == "save_project_fact" and isinstance(result, dict) and result.get("success"):
                    saved_fact = True
                    tool_cache.clear()
                called.append(name)
                messages.append({"role": "tool", "tool_name": name,
                                 **({"tool_call_id": call["id"]} if call.get("id") else {}),
                                 "content": json.dumps(result, ensure_ascii=False)})
                if stream and tool_calls_used < MAX_TOOL_CALLS_PER_TURN:
                    yield {"type": "status", "message": "正在组织答复…"}
            if tool_calls_used >= MAX_TOOL_CALLS_PER_TURN and not limit_notice_added:
                messages.append({"role": "system", "content": "本轮工具调用已达到上限，请基于已取得的信息直接回答；缺失内容请说明。"})
                limit_notice_added = True

        text = "我已达到本轮工具调用上限。请告诉我你想继续处理的章节，或稍后重试。"
        if draft_request and policy_reply is not None:
            text = f"【政策资料核查】\n{policy_reply}\n\n{text}"
        self.store.add_message(project_id, "assistant", text)
        yield {"type": "done", "message": text, "tool_calls": called, "model": self.agent.model}
