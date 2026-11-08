"""Construct the bounded context and presentation of a conversation turn."""
from __future__ import annotations

import json
import re
from typing import Any

from .agent import _system_prompt


def ambiguous_confirmation(history: list[dict[str, Any]], user_text: str) -> bool:
    normalized = user_text.strip().lower().strip("。.!！?？ ")
    affirmations = {"确认", "我确认", "确认无误", "是", "是的", "对", "没错", "正确", "可以", "确定"}
    previous = next((item["content"] for item in reversed(history) if item["role"] == "assistant"), "")
    return normalized in affirmations and any(
        marker in previous for marker in ("还是", "或者", "请选择", "哪个", "哪一个", "具体选择", "二选一")
    )


def conversation_messages(agent: Any, project: dict[str, Any], project_id: str,
                          history: list[dict[str, Any]], user_text: str, *,
                          original_user_text: str | None = None) -> list[dict[str, Any]]:
    from .project_writing import project_sources_allowed
    context = agent._compact_project(project)
    # Mixed policy/writing requests can be trimmed before reaching the model.
    # Keep the original text only for local identity/privacy decisions, never
    # add it to the model messages.
    identity_text = original_user_text if isinstance(original_user_text, str) else user_text
    documents = agent.store.list_documents(project_id) if project_sources_allowed(history, identity_text) else []
    if documents:
        from .chat_tools import is_personal_writing_request
        if is_personal_writing_request(identity_text):
            from .personal_source_filter import filter_personal_evidence
            from .skills import registry
            skill = registry.get(str((project.get("state") or {}).get("skill_id") or ""))
            if skill:
                identity_history = [*history, {"role": "user", "content": identity_text}]
                # Separate explicit self-introduction and privacy clauses for
                # identity matching when the same sentence also asks about
                # policy. Do not do this for examples or other people's data.
                if not re.search(r"示例|举例|例如|比如|假设|虚构|朋友|同学|他人|别人|第三人|替人|代人|帮人|对方|他的|她的", identity_text):
                    for clause in re.split(r"[，,；;。！？!?\n]", identity_text):
                        if re.search(r"我叫|我名叫|我的名字|我的姓名|本人(?:叫|名叫)|(?:不要|别|禁止|不能|不可)(?:使用|填写|写入|引用|展示|透露)", clause):
                            identity_history.append({"role": "user", "content": clause})
                _, excluded = filter_personal_evidence(
                    skill, project, identity_history, documents, {"results": []},
                )
                excluded_ids = set(excluded)
                documents = [item for item in documents if str(item.get("id") or "") not in excluded_ids]
    context["uploaded_materials"] = [
        {"filename": item["original_name"], "kind": item["kind"],
         "confirmed": bool(item["confirmed"]), "extraction_status": item["extraction_status"]}
        for item in documents
    ]
    return [
        {"role": "system", "content": _system_prompt(project)
         + "\n当前项目状态（只作为已保存设定；不代表已确认所有事实）：\n"
         + json.dumps(context, ensure_ascii=False)},
        *[{**item, "content": item["content"][-3500:]} for item in history[-9:]],
        {"role": "user", "content": user_text},
    ]


def final_text(content: Any, *, saved_fact: bool) -> str:
    text = str(content or "").strip()
    if not saved_fact:
        text = re.sub(r"(?:现在我将|我将|我会|正在|已经|已)(?:为你)?保存(?:这个|该)?事实",
                      "建议你确认后保存该事实", text, flags=re.IGNORECASE)
        text = re.sub(r"(?:事实|信息)(?:已|已经)保存", "事实尚未保存；请先确认后再保存", text)
    return text


def without_policy_claims(text: str) -> str:
    """Fail closed on policy-like claims in a model-generated mixed reply.

    The authoritative policy segment is assembled separately from retrieval.
    This filter is a fallback, not verification of any other factual claim.
    """
    topic = r"(?:政策|规则|规定|资格|条件|门槛|截止|排名要求|评审标准|资助标准|奖学金金额|学校要求)"
    personal = r"(?:年级|本科生|大二|大三|二年级|三年级|挂科|排名|绩点|分数|名额|百分比|奖学金|助学金|申请人)"
    blocked = re.compile(
        rf"{topic}"
        rf"|(?:必须|须|至少|不得|不低于|不超过|达到|只有).{{0,22}}{personal}"
        rf"|(?:{personal}).{{0,22}}(?:必须|须为|至少|不低于|不超过|前\s*\d+)"
        r"|(?:符合|具备|有资格|可以|不能|不可|有权|满足).{0,18}(?:申请|申报|报名)"
        r"|(?:申请|申报|报名).{0,18}(?:可以|不能|符合|无资格)"
        r"|(?:奖学金|助学金|补助).{0,18}(?:\d+\s*(?:元|万)|金额|额度)"
        r"|(?:已|已经|均已|经|经过).{0,8}(?:核实|核验|验证|证实|确认).{0,10}(?:事实|信息|内容|经历|资料|无误)"
        r"|(?:事实|信息|内容|经历|资料).{0,8}(?:已|已经|均已|经过).{0,8}(?:核实|核验|验证|证实|确认)"
        r"|(?:根据|依据|按照).{0,20}(?:通知|政策|规定|文件|标准)", re.IGNORECASE,
    )
    pieces = re.split(r"(?<=[。！？!?；;\n])", text)
    kept = [piece for piece in pieces if not blocked.search(piece)]
    return "".join(kept).strip()


def _is_personal_draft_request(draft_request: str, subject: str) -> bool:
    # "收入不要写，请重新写申请书" omits one field; it does not decline
    # the separate, explicit request to draft the document.
    intent_text = "。".join(part for part in re.split(r"[，,；;。！？!?\n]", draft_request)
                           if not _income_omission_requested(part))
    if re.search(r"润色|改写|修改|优化|纠错|校对|怎么写|怎样写|如何写|大纲|提纲|结构|思路|框架|(?:不要|不必|先别|无需|不用|暂时不|不需要)(?:帮我|给我|再|先|现在|直接|马上|为我)?(?:写|生成|起草|撰写)", intent_text):
        return False
    bare_draft = r"\s*(?:请|麻烦)?(?:帮我|替我|给我)?(?:直接|重新|再)?(?:写|生成|起草)(?:一份|一篇|一下)?\s*"
    return bool(re.search(r"(?:写|起草|撰写|生成).{0,24}申请书|(?:直接|请|帮我|给我|重新|再).{0,10}(?:写|起草|生成|给).{0,8}(?:正文|草稿|申请书)|" + subject + r".{0,24}(?:帮我|请|替我)(?:写|起草|撰写|生成)", intent_text)
                or any(re.fullmatch(bare_draft, part) for part in re.split(r"[，,；;。！？!?\n]", intent_text)))


def is_scholarship_draft_request(draft_request: str, project: dict[str, Any]) -> bool:
    return ((project.get("state") or {}).get("skill_id") == "national-scholarship"
            and _is_personal_draft_request(draft_request, r"(?:国家奖学金|国奖)"))


def is_grant_draft_request(draft_request: str, project: dict[str, Any]) -> bool:
    return ((project.get("state") or {}).get("skill_id") == "grant-application"
            and _is_personal_draft_request(draft_request, r"(?:国家助学金|助学金)"))


OUTSTANDING_CLARIFICATION = "你想申请优秀学生（三好学生），还是优秀团员？告诉我具体类型，我就按对应内容起草。"
_OUTSTANDING_FIELDS = {
    "姓名": r"(?:姓名|名字)", "学院": r"学院", "专业": r"专业",
    "绩点": r"(?:绩点|GPA|(?:学习|学业)?成绩)", "排名": r"(?:排名|(?:学习|学业)?成绩)", "科研": r"(?:科研|研究经历)",
    "获奖": r"(?:获奖|奖项|奖励)", "思想": r"(?:政治面貌|思想表现|思想情况|政治身份)",
    "工作": r"(?:学生工作|学生干部|团务工作|团组织活动)", "生活": r"(?:生活表现|生活情况)",
}


_OUTSTANDING_CLAUSE_SEPARATOR = r"[，,；;。！？!?\n]|(?:但是|但|不过|并且|同时|并|也)(?=(?:请|帮|给|我|再|重新|不要|别|不|可以|允许|同意|恢复))"


def _outstanding_clauses(text: str) -> list[str]:
    # Preserve a positive writing request on either side of a field omission.
    return re.split(_OUTSTANDING_CLAUSE_SEPARATOR, text)


def _outstanding_truthfulness_instruction(clause: str) -> bool:
    # "不要编造成绩" asks for accurate facts, not omission of real grades.
    return bool(re.search(r"(?:不要|别|禁止|不可|不能|不许|不准)\s*(?:编造|虚构|杜撰|捏造|伪造|"
                          r"(?:写|填写|提供|添加).{0,5}(?:虚假|编造|虚构|杜撰|捏造|伪造|无依据|无根据|没有依据))", clause))


def _outstanding_omission_fields(text: str) -> set[str]:
    omitted = set()
    for clause in _outstanding_clauses(text):
        if _outstanding_truthfulness_instruction(clause):
            continue
        denial = re.search(r"不要|别|禁止|不可|不能|不必|无需|不用|不需要|暂不|不(?=写|提|填|用|放)", clause)
        if not denial:
            continue
        if not re.search(r"写|提|填|用|放|展示|透露|引用|出现", clause):
            continue
        suffix = clause[denial.start():]
        selected = {key for key, pattern in _OUTSTANDING_FIELDS.items() if re.search(pattern, suffix, re.IGNORECASE)}
        # Also support inverted instructions such as “绩点不要写”.
        omitted.update(selected or {key for key, pattern in _OUTSTANDING_FIELDS.items() if re.search(pattern, clause, re.IGNORECASE)})
    return omitted


def outstanding_student_omissions(history: list[dict[str, Any]], user_text: str) -> set[str]:
    """Keep explicit per-field omissions until the student permits them again."""
    omitted: set[str] = set()
    for item in [*history, {"role": "user", "content": user_text}]:
        if item.get("role") != "user" or not isinstance(item.get("content"), str):
            continue
        for clause in _outstanding_clauses(item["content"]):
            denied = _outstanding_omission_fields(clause)
            if denied:
                omitted.update(denied)
                continue
            if _outstanding_truthfulness_instruction(clause):
                continue
            if not re.search(r"(?:可以|允许|同意|恢复).{0,20}(?:写|提|填|用|展示|引用|出现)", clause):
                continue
            omitted.difference_update(key for key, pattern in _OUTSTANDING_FIELDS.items()
                                      if re.search(pattern, clause, re.IGNORECASE))
    return omitted


def is_outstanding_draft_request(draft_request: str, project: dict[str, Any], previous_assistant: str = "") -> bool:
    """Recognize a draft or a direct answer to our two-type clarification."""
    if (project.get("state") or {}).get("skill_id") != "outstanding-student":
        return False
    if previous_assistant == OUTSTANDING_CLARIFICATION:
        reply = draft_request.strip().strip("。！! \n")
        if reply in {"优秀学生", "三好学生", "优秀团员"}:
            return True
    # A field-level omission is not a refusal to draft the whole document.
    intent_text = "。".join(part for part in _outstanding_clauses(draft_request)
                           if not _outstanding_omission_fields(part) and not _outstanding_truthfulness_instruction(part))
    return _is_personal_draft_request(intent_text, r"(?:优秀学生|三好学生|优秀团员)")


def outstanding_student_category(history: list[dict[str, Any]], user_text: str) -> str | None:
    """Use only a student's explicit type, never infer membership or eligibility."""
    for item in reversed([*history, {"role": "user", "content": user_text}]):
        if item.get("role") != "user" or not isinstance(item.get("content"), str):
            continue
        text = item["content"]
        student = bool(re.search(r"优秀学生|三好学生", text))
        league = "优秀团员" in text
        if student and league:
            return None  # Ask instead of guessing when both are mentioned.
        if student or league:
            return "优秀团员" if league else "三好学生" if "三好学生" in text else "优秀学生"
    return None


def outstanding_student_draft(category: str, facts: dict[str, str], *, conflicted: bool = False,
                              omitted: set[str] | None = None) -> str:
    """Compose the Skill's five areas from explicit fields and placeholders."""
    if category not in {"优秀学生", "三好学生", "优秀团员"}:
        raise ValueError("未知评优类别")
    omitted = omitted or set()
    field = lambda label: facts.get(label, f"【{label}待补充】")
    profile_parts = []
    if "姓名" not in omitted: profile_parts.append(f"我叫{field('姓名')}")
    if "学院" not in omitted: profile_parts.append(f"现就读于{field('学院')}")
    if "专业" not in omitted: profile_parts.append(f"所学专业为{field('专业')}")
    profile = "，".join(profile_parts) + "。" if profile_parts else ""
    study_parts = []
    if "绩点" not in omitted: study_parts.append(f"绩点为{field('绩点')}")
    if "排名" not in omitted: study_parts.append(f"排名为{field('排名')}")
    study = "我的" + "，".join(study_parts) + "。" if study_parts else ""
    # A source's award field may contain grades as free text; do not let it
    # reintroduce a field that the student explicitly asked us to omit.
    award = facts.get("获奖", "")
    hidden_grade_patterns = []
    if "绩点" in omitted:
        hidden_grade_patterns.append(r"绩点|GPA|成绩|分数|得分|平均分")
    if "排名" in omitted:
        hidden_grade_patterns.append(r"排名|名次|成绩")
    for label in ("绩点", "排名"):
        if label in omitted and facts.get(label):
            hidden_grade_patterns.append(r"(?<!\d)" + re.escape(facts[label]) + r"(?!\d)")
    if hidden_grade_patterns and re.search("|".join(hidden_grade_patterns), award, re.IGNORECASE):
        award = ""
    # No unnamed awards, political identity or service hours are inferred.
    if "获奖" not in omitted and award:
        experience = f"我的获奖情况：{award}。"
    elif "科研" in omitted and "获奖" in omitted:
        experience = "【本学年实践经历待补充】"
    elif "科研" in omitted:
        experience = "【本学年实践或获奖情况待补充】"
    elif "获奖" in omitted:
        experience = "【本学年科研或实践情况待补充】"
    else:
        experience = "【本学年科研、实践或获奖情况待补充】"
    if "科研" not in omitted and facts.get("科研经历") == "无":
        experience = "目前我暂无科研经历。\n\n" + experience
    work = "【本学年团务工作和团组织活动待补充】" if category == "优秀团员" else "【本学年学生工作与服务情况待补充】"
    note = "请补充【待补充】的内容，完成后可以在工作台保存草稿。"
    if conflicted:
        note += "部分信息有不同说法，请告诉我应使用哪一项。"
    return (
        '<WritingBlock variant="document">\n'
        f"## {category}申请书\n\n"
        "尊敬的评审老师：\n\n"
        f"我申请【申请学年待补充】{category}，现将本人情况说明如下。\n\n"
        + (f"{profile}\n\n" if profile else "")
        + ("【本学年思想表现待补充】\n\n" if "思想" not in omitted else "")
        + (f"{study}\n\n" if study else "") + f"{experience}\n\n"
        + (f"{work}\n\n" if "工作" not in omitted else "")
        + ("【本学年生活表现待补充】\n\n" if "生活" not in omitted else "")
        + "恳请老师审阅。\n\n此致\n敬礼！\n\n"
        + (f"申请人：{field('姓名')}\n" if "姓名" not in omitted else "") + "日期：【待补充】\n"
        "</WritingBlock>\n\n" + note
    )


def is_scholarship_preparation_request(user_text: str, project: dict[str, Any]) -> bool:
    if (project.get("state") or {}).get("skill_id") != "national-scholarship":
        return False
    # Do not silently replace a requested edit with a generic checklist.
    if re.search(r"润色|改写|修改|优化|纠错|校对", user_text):
        return False
    return bool(re.search(r"(?:怎么|怎样|如何|应该如何|应该怎么|如何开始|怎样开始).{0,8}(?:准备|开始|着手)|(?:准备|着手).{0,5}(?:步骤|流程|什么)", user_text))


def scholarship_preparation_reply() -> str:
    return ("可以先从这几步开始：\n\n"
            "1. 找到学校和学院当年的通知，确认适用对象、提交方式与时间。\n"
            "2. 整理成绩单、专业排名证明和已有获奖、科研或实践材料。\n"
            "3. 按学校模板填写信息，再准备申请书，重点写自己的学习与成长经历。\n"
            "4. 对照通知检查材料清单、证明附件和签字要求，按学校安排提交。\n\n"
            "你可以告诉我学校、年级和已有材料，我可以和你一起整理申请书。")


_INCOME_TOPIC = r"(?:家庭年收入|家庭收入|家庭经济|年收入|(?:我家|家里|家中|家庭)(?:的)?收入|收入)"
_INCOME_ACTION = r"(?:使用|填写|写入|写|引用|展示|透露|提及|提到|提|放|说|体现|包含|出现)"
_INCOME_DENIAL = r"(?:不要|别|禁止|不可|不能|不可以|不允许|不希望|不想|不必|无需|不用|不需要|暂不|不(?=写|提|填|用|放))"


def _income_omission_requested(text: str) -> bool:
    """Recognize a student's instruction to omit income, in either word order."""
    for clause in re.split(r"[，,；;。！？!?\n]", text):
        if (re.search(_INCOME_DENIAL + rf"(?=.{{0,35}}{_INCOME_TOPIC})(?=.{{0,35}}{_INCOME_ACTION})", clause)
                or re.search(_INCOME_TOPIC + rf".{{0,20}}{_INCOME_DENIAL}.{{0,12}}{_INCOME_ACTION}", clause)):
            return True
    return False


def _income_use_requested(text: str) -> bool:
    """Only an explicit later permission can undo an earlier omission request."""
    if _income_omission_requested(text):
        return False
    for clause in re.split(r"[，,；;。！？!?\n]", text):
        if re.search(r"(?:可以|允许|同意|请|恢复)" + rf"(?=.{{0,35}}{_INCOME_TOPIC})(?=.{{0,35}}{_INCOME_ACTION})", clause):
            return True
    return False


def current_turn_student_facts(user_text: str, *, include_family_income: bool = False) -> dict[str, str]:
    """Copy narrowly recognized self-reported facts from this turn.

    A student can write “我的资料：姓名：…；学院：…；专业：…；绩点：…；排名：…”.
    These are self-reports, not verified facts or persistent project state.
    Never extract from history, policy documents, examples or model output.
    """
    if re.search(r"示例|举例|例如|比如|假设|虚构|(?:不要|别|不|禁止|不可|不能)(?:使用|填写|写入|引用|展示|透露)", user_text):
        return {}
    markers = list(re.finditer(r"(?:^|[。！？!?\n])\s*(?:我的资料|本人资料)\s*[：:]", user_text))
    if len(markers) > 1:
        return {}
    validators = {
        "姓名": r"[\u4e00-\u9fffA-Za-z· ]{2,30}",
        "学院": r"[\u4e00-\u9fffA-Za-z0-9·（）() \-]{2,40}",
        "专业": r"[\u4e00-\u9fffA-Za-z0-9·（）() \-]{2,40}",
        "绩点": r"\d{1,3}(?:\.\d{1,3})?(?:\s*/\s*\d{1,3}(?:\.\d{1,3})?)?",
        "排名": r"(?:第\s*\d{1,5}\s*名|\d{1,5}\s*/\s*\d{1,5})",
    }
    if include_family_income:
        validators["家庭年收入"] = r"(?:约|大约|近)?\s*\d{1,9}(?:\.\d{1,2})?\s*(?:万元|万|元)"
    facts: dict[str, str] = {}
    seen: set[str] = set()

    def remember(label: str, value: str) -> None:
        label = "绩点" if label.upper() == "GPA" else label
        if label in seen:
            facts.pop(label, None)
            return
        seen.add(label)
        if (re.search(r"示例|例如|假设|虚构|他人|同学|待补充", value)
                or re.search(r"我的|本人|我叫|我学|我是|我在|绩点|排名|GPA|申请书", value, re.IGNORECASE)
                or (label == "姓名" and (re.search(r"我|专业|学院|来自|就读", value)
                                         or ("学" in value and len(value) > 4)))
                or not re.fullmatch(validators[label], value)):
            return
        facts[label] = value

    if markers:
        tail = user_text[markers[0].end():]
        for part in re.split(r"[；;，,。\n]", tail):
            if re.search(r"[\x00-\x1f\x7f]", part):
                continue
            labels = "姓名|学院|专业|绩点|GPA|排名" + ("|家庭年收入" if include_family_income else "")
            match = re.fullmatch(rf"\s*({labels})\s*[：:=]\s*(.*?)\s*", part, re.IGNORECASE)
            if match:
                remember(*match.groups())
        return facts

    # A bare “绩点 3.8” is only attached to a first-person statement in the
    # same uninterrupted sentence. Sentences referring to someone else or to a
    # notice/rule are not treated as the student's facts.
    natural_patterns = (
        ("姓名", r"(?:我叫|我名叫|我的名字(?:叫|是|为)|我的姓名(?:叫|是|为)|本人(?:叫|名叫))(.+)", True),
        ("学院", r"(?:我的|本人的)学院(?:是|为|：|:)(.+)", True),
        ("学院", r"(?:我在|我就读于|本人在)(.+学院)", True),
        ("专业", r"(?:我的|本人的)专业(?:是|为|：|:)(.+)", True),
        ("专业", r"(?:我|本人)(?:学|读)(.+?)专业", True),
        ("专业", r"专业(?:是|为|：|:)(.+)", False),
        ("专业", r"(?:学|读)(.+?)专业", False),
        ("专业", r"([\u4e00-\u9fffA-Za-z0-9·（）() \-]{2,40})专业", False),
        ("绩点", r"(?:我的|本人的)(?:绩点|GPA)(?:更正为|改成|改为|更新为|是|为|：|:|=)?\s*(.+)", True),
        ("绩点", r"(?:绩点|GPA)(?:是|为|：|:|=)?\s*(.+)", False),
        ("排名", r"(?:我的|本人的)(?:专业排名|排名)(?:更正为|改成|改为|更新为|是|为|：|:|=)?\s*(.+)", True),
        ("排名", r"(?:专业排名|排名)(?:是|为|：|:|=)?\s*(.+)", False),
    )
    if include_family_income:
        natural_patterns += (
            ("家庭年收入", r"(?:我家|我家的|我的家庭|本人的家庭|本人家庭)(?:的)?(?:家庭)?年收入(?:更正为|改成|改为|更新为|是|为|：|:|=)?\s*(.+)", True),
            ("家庭年收入", r"(?:家庭|家里)年收入(?:更正为|改成|改为|更新为|是|为|：|:|=)?\s*(.+)", False),
        )
    if re.search(r"(?:朋友|同学|别人|他人|其他人|第三人|替人|代人|帮人|对方|他的|她的|他们|她们)", user_text):
        return {}
    for sentence in re.split(r"[。！？!?\n]", user_text):
        if re.search(r"[\x00-\x1f\x7f]|(?:通知|政策|规定|学校要求|评审条件|申请条件|资格条件)", sentence):
            continue
        anchored = False
        for part in re.split(r"[；;，,]", sentence):
            part = part.strip()
            if re.fullmatch(r"(?:更正|纠正|修正)", part):
                anchored = True
                continue
            found = next(((label, match.group(1).strip(), explicit)
                          for label, pattern, explicit in natural_patterns
                          if (match := re.fullmatch(pattern, part, re.IGNORECASE))), None)
            if not found:
                if anchored:
                    break
                continue
            label, value, explicit = found
            if not explicit and not anchored:
                continue
            anchored = anchored or explicit
            remember(label, value)
    return facts


def scholarship_student_facts(history: list[dict[str, Any]], user_text: str,
                              documents: list[dict[str, Any]], *,
                              include_family_income: bool = False, project_id: str = "",
                              field_level_grade_omission: bool = False) -> tuple[dict[str, str], bool]:
    """Collect bounded, unambiguous profile fields without trusting model output.

    Only user messages contribute. A confirmed source document can supplement
    the same student when its labelled name matches an explicitly stated name.
    Conflicting values are left out unless the student explicitly corrects one.
    """
    facts: dict[str, str] = {}
    conflicted: set[str] = set()
    corrected: set[str] = set()
    no_awards = False
    no_research = False
    use_documents = True
    use_family_income = True
    hidden_family_income: str | None = None
    hidden_income_conflict = False
    hidden_income_corrected = False
    student_id: str | None = None
    student_id_conflict = False

    def merge(values: dict[str, str], *, correction: bool = False) -> None:
        for label, value in values.items():
            if correction:
                facts[label] = value
                conflicted.discard(label)
                corrected.add(label)
            elif label in conflicted:
                continue
            elif label in facts and facts[label] != value:
                facts.pop(label, None)
                conflicted.add(label)
            else:
                facts[label] = value

    for item in [*history, {"role": "user", "content": user_text}]:
        if item.get("role") != "user" or not isinstance(item.get("content"), str):
            continue
        text = item["content"]
        privacy_subject = r"(?:资料|信息|姓名)" if field_level_grade_omission else r"(?:资料|信息|姓名|成绩)"
        if re.search(r"(?:不要|别|禁止|不可|不能)(?:使用|填写|写入|引用|展示|透露).{0,8}(?:我的|本人|个人)?" + privacy_subject, text):
            facts.clear()
            conflicted.clear()
            corrected.clear()
            no_awards = False
            no_research = False
            use_documents = False
            if include_family_income:
                use_family_income = False
                hidden_family_income = None
                hidden_income_conflict = False
                hidden_income_corrected = False
            student_id = None
            student_id_conflict = False
            continue
        # Use a clearly self-stated student number only as an in-memory
        # disambiguator; never copy it into the generated application.
        # Other people's numbers and examples are not student identity.
        if not re.search(r"示例|举例|例如|比如|假设|虚构|朋友|同学|他人|别人", text):
            id_pattern = r"(?:我的|本人(?:的)?)学号\s*(?:改为|改成|更新为|是|为|[：:=])\s*([A-Za-z0-9]{4,30})(?![A-Za-z0-9])"
            identifiers = {value.casefold() for value in re.findall(id_pattern, text)}
            if re.search(r"我叫|我名叫|本人姓名", text):
                identifiers.update(value.casefold() for value in re.findall(
                    r"(?:^|[，,；;。\s])学号\s*(?:改为|改成|更新为|是|为|[：:=])\s*([A-Za-z0-9]{4,30})(?![A-Za-z0-9])", text,
                ))
            if len(identifiers) > 1:
                student_id = None
                student_id_conflict = True
            elif identifiers:
                value = next(iter(identifiers))
                if re.search(r"更正|纠正|改为|改成|更新为", text):
                    student_id, student_id_conflict = value, False
                elif student_id_conflict:
                    pass
                elif student_id is not None and student_id != value:
                    student_id, student_id_conflict = None, True
                else:
                    student_id = value
        if re.search(r"(?:不要|别|禁止|不可|不能)(?:使用|引用|读取).{0,8}(?:附件|材料|文档)", text):
            use_documents = False
        if include_family_income and _income_omission_requested(text):
            if use_family_income:
                hidden_family_income = facts.get("家庭年收入")
                hidden_income_conflict = "家庭年收入" in conflicted
                hidden_income_corrected = "家庭年收入" in corrected
            use_family_income = False
            facts.pop("家庭年收入", None)
            corrected.discard("家庭年收入")
            conflicted.discard("家庭年收入")
        elif include_family_income and not use_family_income and _income_use_requested(text):
            use_family_income = True
            if hidden_family_income is not None:
                facts["家庭年收入"] = hidden_family_income
            if hidden_income_conflict:
                conflicted.add("家庭年收入")
            if hidden_income_corrected:
                corrected.add("家庭年收入")
        if re.search(r"(?:我|本人)?(?:没有|没|未有|无|未获得|没获得|没有获得).{0,8}(?:获奖|奖项|奖励|奖状)", text):
            no_awards = True
            facts.pop("获奖", None)
        if re.search(r"(?:我|本人)?(?:没有|暂无|尚无|无)(?:任何)?科研(?:项目|经历|成果)", text) and not re.search(r"(?:没有|暂无|尚无|无).{0,10}科研.{0,5}(?:吗|么|[？?])", text):
            no_research = True
        elif re.search(r"(?:我|本人)(?:曾|也|已经|已)?(?:参与|参加|做过|完成).{0,12}科研", text):
            no_research = False
        # A clause declining income use must not prevent extracting an
        # explicitly supplied name or major in the same message.
        extraction_text = text
        if include_family_income and _income_omission_requested(text):
            extraction_text = "，".join(part for part in re.split(r"[，,；;。！？!?\n]", text)
                                       if not _income_omission_requested(part))
        if field_level_grade_omission:
            # A grade-only denial must not hide unrelated self-reported facts
            # from the same message. Preserve any first-person prefix, while
            # never extracting claims from the denial itself.
            parts = re.split("(" + _OUTSTANDING_CLAUSE_SEPARATOR + ")", extraction_text)
            # Treat conjunctions as clause separators for the fact parser;
            # preserve sentence punctuation so first-person scope cannot leak.
            for index in range(1, len(parts), 2):
                if parts[index] not in "，,；;。！？!?\n":
                    parts[index] = "，"
            for index in range(0, len(parts), 2):
                clause = parts[index]
                if _outstanding_omission_fields(clause) & {"绩点", "排名"}:
                    denial = re.search(r"不要|别|禁止|不可|不能|不必|无需|不用|不需要|暂不|不(?=写|提|填|用|放)", clause)
                    parts[index] = clause[:denial.start()] if denial else ""
            extraction_text = "".join(parts)
        parsed = current_turn_student_facts(extraction_text, include_family_income=include_family_income)
        if not use_family_income:
            parsed.pop("家庭年收入", None)
        # If one message supplies two contradictory values for the same
        # field, the parser discards them. Do not silently fall back to an
        # older value for that field.
        aliases = {"姓名": r"我叫|我名叫|姓名\s*[：:=]", "学院": r"(?:我的学院(?:是|为)|学院\s*[：:=])",
                   "专业": r"(?:我的专业(?:是|为)|专业\s*[：:=])",
                   "绩点": r"(?:绩点|GPA)\s*(?:是|为|[：:=])?\s*\d",
                   "排名": r"排名\s*(?:是|为|[：:=])?\s*(?:第\s*)?\d"}
        if include_family_income:
            aliases["家庭年收入"] = r"(?:家庭|我家|家里)(?:的)?(?:家庭)?年收入\s*(?:是|为|[：:=])?\s*\d"
        for label, pattern in aliases.items():
            if label not in parsed and len(re.findall(pattern, text, re.IGNORECASE)) > 1:
                facts.pop(label, None)
                corrected.discard(label)
                conflicted.add(label)
        merge(parsed, correction=bool(re.search(r"更正|纠正|改为|改成|更新为", text)))

    name = facts.get("姓名")
    document_identity_conflict = student_id_conflict
    if name and use_documents and project_id:
        from .personal_materials import confirmed_personal_material_fields
        records: list[tuple[dict[str, str], dict[str, str]]] = []
        observed_identity: dict[str, str] = {}
        for doc in documents:
            identity: dict[str, str] = {}
            values = confirmed_personal_material_fields(
                doc, name, project_id=project_id, include_family_income=include_family_income,
                identity_out=identity,
            )
            if not values:
                continue
            records.append((values, identity))
            if student_id and identity.get("学号") and identity["学号"].casefold() != student_id:
                document_identity_conflict = True
            for label, value in identity.items():
                if label in observed_identity and observed_identity[label] != value:
                    document_identity_conflict = True
                observed_identity[label] = value
        # Same names do not identify a person when the documents themselves
        # provide conflicting identifiers. Keep the student's own explicit
        # statements, but do not choose or combine any of those documents.
        if document_identity_conflict:
            records = []
        for values, _ in records:
            for label in ("学院", "专业", "绩点", "排名", "家庭年收入"):
                if label in values and label not in corrected and (label != "家庭年收入" or use_family_income):
                    merge({label: values[label]})
            if not no_awards and values.get("获奖"):
                merge({"获奖": values["获奖"]})
    if no_research:
        facts["科研经历"] = "无"
    if include_family_income and not use_family_income:
        facts["不写家庭收入"] = "是"
    return facts, bool(conflicted) or document_identity_conflict


def scholarship_placeholder_draft(user_text: str = "", *, facts: dict[str, str] | None = None,
                                  conflicted: bool = False) -> str:
    if facts is None:
        facts = current_turn_student_facts(user_text)
    field = lambda label: facts.get(label, f"【{label}待补充】")
    profile = f"我叫{field('姓名')}，现就读于{field('学院')}，所学专业为{field('专业')}。"
    study = f"我的绩点为{field('绩点')}，排名为{field('排名')}。"
    note = "请补充【待补充】的内容，完成后可以在工作台保存草稿。"
    if conflicted:
        note += "部分信息有不同说法，请告诉我应使用哪一项。"
    return "".join((
        "<WritingBlock variant=\"document\">\n"
        "## 国家奖学金申请书\n\n"
        "尊敬的评审老师：\n\n"
        "我申请【申请学年待补充】国家奖学金，现将有关情况汇报如下。\n\n",
        f"{profile}\n\n" if facts else "【个人基本情况待补充】\n\n",
        f"{study}\n\n" if facts else "【学习情况待补充】\n\n",
        "目前我暂无科研经历。\n\n" if facts.get("科研经历") == "无" else "",
        f"我的获奖情况：{facts['获奖']}。\n\n" if facts.get("获奖") else (
            "【竞赛或实践经历待补充】\n\n" if facts.get("科研经历") == "无" else "【科研、竞赛或实践经历待补充】\n\n"),
        "【其他个人表现待补充】\n\n"
        "恳请老师审阅。\n\n"
        "此致\n敬礼！\n\n",
        f"申请人：{facts.get('姓名', '【姓名待补充】')}\n日期：【待补充】\n",
        "</WritingBlock>\n\n",
        note,
    ))


def grant_placeholder_draft(*, facts: dict[str, str], conflicted: bool = False) -> str:
    """Build a grant application without inventing family or school history."""
    field = lambda label: facts.get(label, f"【{label}待补充】")
    note = "请补充【待补充】的内容，完成后可以在工作台保存草稿。"
    if conflicted:
        note += "部分信息有不同说法，请告诉我应使用哪一项。"
    return "".join((
        '<WritingBlock variant="document">\n'
        "## 国家助学金申请书\n\n"
        "尊敬的评审老师：\n\n"
        "我申请【申请学年待补充】国家助学金，现将本人情况说明如下。\n\n",
        f"我叫{field('姓名')}，现就读于{field('学院')}，所学专业为{field('专业')}。\n\n",
        "" if facts.get("不写家庭收入") else f"我的家庭年收入为{field('家庭年收入')}。\n\n",
        "【家庭成员、经济情况及实际困难待补充】\n\n"
        "【在校学习和生活情况待补充】\n\n"
        "【申请理由及今后的计划待补充】\n\n"
        "恳请老师审阅。\n\n"
        "此致\n敬礼！\n\n",
        f"申请人：{field('姓名')}\n日期：【待补充】\n",
        "</WritingBlock>\n\n", note,
    ))


def fallback_scholarship_draft(text: str, draft_request: str, project: dict[str, Any]) -> str:
    """Repair one narrowly identifiable failure: a draft request answered only by a checklist."""
    if not is_scholarship_draft_request(draft_request, project):
        return text
    if re.search(r"<WritingBlock\b|(?:^|\n)\s*(?:尊敬的|敬爱的).{0,30}[：:]|(?:本人|我)(?:郑重|现|自愿|特此|拟)?申请", text):
        return text
    numbered = re.findall(r"(?m)^\s*(?:\d+[.、）)]|[（(]\d+[）)])\s*", text)
    if len(numbered) < 3 or not re.search(r"请(?:先)?(?:逐项)?提供|请填写|采集.{0,8}信息|需要.{0,8}信息", text):
        return text
    return scholarship_placeholder_draft()
