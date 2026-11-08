"""A conservative, editable starter for explicitly requested graduate materials."""
from __future__ import annotations

import re
from typing import Any

from .chat_context import (
    _outstanding_clauses,
    _outstanding_omission_fields,
    _outstanding_truthfulness_instruction,
    outstanding_student_omissions,
    scholarship_student_facts,
)


def is_graduate_draft_request(
    text: str, project: dict[str, Any], *, documents: list[dict[str, Any]] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> bool:
    """Catch explicit writing requests, not questions about how to apply."""
    if (project.get("state") or {}).get("skill_id") != "graduate-recommendation" or not isinstance(text, str):
        return False
    if re.search(r"怎么写|怎样写|如何写|写作(?:建议|思路|方法)|申请(?:条件|资格|政策|流程).{0,5}(?:是|什么|哪些|如何)", text):
        return False
    if re.search(r"(?:不要|别|不必|先别|无需|不用|暂时不|不需要)(?:帮我|给我|再|先|直接)?(?:写|生成|起草|撰写).{0,12}(?:申请书|个人陈述|正文|草稿)", text):
        return False
    # A bounded starter cannot faithfully summarize arbitrary uploads. If the
    # student explicitly asks to use confirmed material, preserve the normal
    # retrieval/model path, which applies the personal-source identity filter.
    wants_material = bool(re.search(
        r"(?:根据|依据|结合|参考|按照|利用|阅读|读取|查看|读一下|使用|从).{0,20}(?:资料|材料|附件|文档|文件|简历|成绩单|通知)"
        r"|(?:资料|材料|附件|文档|文件|简历|成绩单|通知).{0,10}(?:来|帮我|为我)?(?:写|起草|撰写|生成|整理)", text))
    if wants_material:
        from .project_writing import project_sources_allowed
        project_id = str(project.get("id") or "")
        usable = any(doc.get("kind") in {"source", "official"} and doc.get("confirmed")
                     and doc.get("confirmation_origin") == "user"
                     and (not project_id or doc.get("project_id") == project_id)
                     for doc in (documents or []))
        if usable and project_sources_allowed(history or [], text):
            return False
    # An instruction not to write grades or names does not cancel a separate
    # request to write the rest of the letter.
    clauses = _outstanding_clauses(text)
    intent = "。".join(part for part in clauses if not _outstanding_omission_fields(part)
                      and not _outstanding_truthfulness_instruction(part))
    verb = r"(?:写|起草|撰写|生成|编写)"
    subject = r"(?:保研|推免|个人陈述|申请书|自荐信|申请材料|正文|草稿)"
    return bool(re.search(verb + r".{0,30}" + subject + "|" + subject + r".{0,24}" + verb, intent)
                or any(re.fullmatch(r"\s*(?:请|麻烦)?(?:帮我|替我|给我)?(?:直接|重新|再)?(?:写|生成|起草)(?:一份|一篇|一下)?\s*", part) for part in clauses))


def _graduate_extra_facts(history: list[dict[str, Any]], user_text: str) -> tuple[dict[str, str], bool]:
    """Copy only narrowly labelled target school and language results."""
    values: dict[str, str] = {}
    conflicts: set[str] = set()
    patterns = {
        "目标院校": r"(?:我的|本人的)?(?:目标院校|目标学校|申请院校|申请学校)\s*(?:改为|改成|更新为|是|为|[：:=])\s*([\u4e00-\u9fffA-Za-z0-9·（）()]{2,25}?(?:大学|学院|研究院))(?=\s*(?:[，,；;。！？!?\n]|$))",
        "英语成绩": r"(?:我的|本人的)?(六级|四级|CET-?6|CET-?4|雅思|托福)(?:成绩|得分)?\s*(?:改为|改成|更新为|是|为|[：:=])?\s*(\d{1,4}(?:\.\d{1,2})?)\s*(?:分)?",
    }
    for item in [*history, {"role": "user", "content": user_text}]:
        text = item.get("content")
        if item.get("role") != "user" or not isinstance(text, str):
            continue
        if re.search(r"示例|举例|例如|比如|假设|虚构|朋友|同学|他人|别人|他的|她的", text):
            continue
        if re.search(r"(?:不要|别|禁止|不可|不能)(?:使用|填写|写入|引用|展示|透露).{0,8}(?:我的|本人|个人)?(?:资料|信息)", text):
            values.clear(); conflicts.clear()
            continue
        for clause in re.split(r"[，,；;。！？!?\n]", text):
            if re.search(r"(?:不要|别|禁止|不可|不能|不必|无需|不用)(?:写|填写|写入|使用|展示|透露|提及).{0,12}(?:目标院校|目标学校|英语|六级|四级|雅思|托福)", clause):
                continue
            for label, pattern in patterns.items():
                matches = list(re.finditer(pattern, clause, re.I))
                candidates = {("".join(m.groups()) if label == "英语成绩" else m.group(1)) for m in matches}
                if len(candidates) > 1:
                    values.pop(label, None); conflicts.add(label)
                elif candidates:
                    value = next(iter(candidates))
                    if re.search(r"更正|纠正|改为|改成|更新为", clause):
                        values[label] = value; conflicts.discard(label)
                    elif label in conflicts:
                        continue
                    elif label in values and values[label] != value:
                        values.pop(label, None); conflicts.add(label)
                    else:
                        values[label] = value
    return values, bool(conflicts)


def _graduate_narrative_facts(history: list[dict[str, Any]], user_text: str) -> tuple[dict[str, str], bool, set[str]]:
    """Keep short, explicitly labelled student statements without embellishment.

    Free-form uploads, examples, other people and ambiguous revisions are not
    summarized here. The ordinary retrieval path remains available for those.
    """
    labels = {
        "经历": r"(?:相关经历|项目经历|课程项目经历|实践经历|科研经历)",
        "方向": r"(?:目标方向|申请方向|研究方向|学术兴趣)",
        "动机": r"(?:申请动机|申请理由|选择原因)",
        "计划": r"(?:研究生计划|研究计划|学习计划|未来计划)",
    }
    values: dict[str, str] = {}
    conflicts: set[str] = set()
    omitted: set[str] = set()
    blocked = False
    for item in [*history, {"role": "user", "content": user_text}]:
        text = item.get("content")
        if item.get("role") != "user" or not isinstance(text, str):
            continue
        for clause in re.split(r"[，,；;。！？!?\n]", text):
            if re.search(r"(?:不要|别|禁止|不可|不能|不许|不用)(?:使用|填写|写入|引用|展示|透露).{0,8}(?:我的|本人|个人)?(?:资料|信息)", clause):
                values.clear()
                conflicts.clear()
                blocked = True
                continue
            if re.search(r"(?:可以|允许|同意|恢复).{0,8}(?:使用|填写|写入|引用).{0,8}(?:我的|本人|个人)?(?:资料|信息)", clause):
                blocked = False
                continue
            if not _outstanding_truthfulness_instruction(clause):
                deny = re.search(r"(?:不要|别|禁止|不可|不能|不必|无需|不用|不需要|暂不|不(?=写|提|填|用)).{0,8}(?:写|提|填|用|展示|引用|出现)", clause)
                allow = re.search(r"(?:可以|允许|同意|恢复).{0,10}(?:写|提|填|用|展示|引用)", clause)
                for label, pattern in labels.items():
                    if re.search(pattern, clause):
                        if deny:
                            omitted.add(label)
                        elif allow:
                            omitted.discard(label)
                if deny or allow:
                    continue
            if blocked or re.search(r"示例|举例|例如|比如|假设|虚构|朋友|同学|他人|别人|他的|她的|不要|不写|别写|禁止|不必|无需|不用|请(?:帮我|给我|直接)?(?:写|生成|起草)", clause):
                continue
            for label, pattern in labels.items():
                match = re.fullmatch(
                    rf"\s*(?:(?:更正|纠正)\s*[：:]?\s*)?(?:(?:我|我的|本人|本人的)\s*)?{pattern}"
                    r"\s*(?:改为|改成|更新为|是|为|[：:])\s*([^<>\[\]【】\n]{2,100})\s*", clause)
                if not match:
                    continue
                value = match.group(1).strip()
                if re.fullmatch(r"(?:无|没有|暂无|不详|不确定|待补充|不知道)", value):
                    continue
                if re.search(r"更正|纠正|改为|改成|更新为", clause):
                    values[label] = value
                    conflicts.discard(label)
                elif label in conflicts:
                    continue
                elif label in values and values[label] != value:
                    values.pop(label, None)
                    conflicts.add(label)
                else:
                    values[label] = value
    return values, bool(conflicts), omitted


def _personal_profile_anchor(text: str) -> str:
    """Recognize a labelled name only in an explicit self-application request.

    This conversion is only used by the in-memory fact parser. It does not
    alter the stored conversation or infer the identity of another applicant.
    """
    if (re.search(r"示例|举例|例如|比如|假设|虚构|朋友|同学|他人|别人|第三人|替人|代人|帮人|对方|他的|她的|他们|她们", text)
            or not re.search(r"我(?:准备|打算|计划|想要|想|要)?(?:申请|报考)(?:保研|推免|研究生)"
                             r"|(?:帮我|替我|为我|给我)(?:直接|重新|再)?(?:写|起草|撰写|生成)(?:一份|一篇)?(?:我的)?(?:保研|推免|个人陈述|申请书|自荐信)", text)):
        return text
    pattern = r"(^|[，,；;。！？!?\n])\s*姓名\s*[：:=]\s*([\u4e00-\u9fffA-Za-z· ]{2,30})(?=\s*(?:[，,；;。！？!?\n]|$))"
    return re.sub(pattern, lambda match: match.group(1) + "我叫" + match.group(2).strip(), text)


def graduate_placeholder_draft(
    history: list[dict[str, Any]], user_text: str, documents: list[dict[str, Any]], *, project_id: str,
) -> str:
    """Compose a starter without deciding eligibility or inventing experiences."""
    profile_history = [({**item, "content": _personal_profile_anchor(item["content"])}
                        if item.get("role") == "user" and isinstance(item.get("content"), str) else item)
                       for item in history]
    facts, conflicted = scholarship_student_facts(
        profile_history, _personal_profile_anchor(user_text), documents, project_id=project_id, field_level_grade_omission=True,
    )
    extras, extra_conflict = _graduate_extra_facts(history, user_text)
    narrative, narrative_conflict, narrative_omissions = _graduate_narrative_facts(history, user_text)
    omissions = outstanding_student_omissions(history, user_text)
    # Honor explicit omission for extra fields until a later affirmative use.
    skip_extras: set[str] = set()
    for item in [*history, {"role": "user", "content": user_text}]:
        text = item.get("content")
        if item.get("role") != "user" or not isinstance(text, str):
            continue
        for clause in re.split(r"[，,；;。！？!?\n]", text):
            deny = re.search(r"(?:不要|别|禁止|不可|不能|不必|无需|不用)(?:写|填写|写入|使用|展示|透露|提及)", clause)
            allow = re.search(r"(?:可以|允许|同意|恢复).{0,8}(?:写|填写|提|使用)", clause)
            if re.search(r"目标院校|目标学校|申请院校|申请学校", clause):
                if deny: skip_extras.add("目标院校")
                elif allow: skip_extras.discard("目标院校")
            if re.search(r"英语|六级|四级|CET|雅思|托福", clause, re.I):
                if deny: skip_extras.add("英语成绩")
                elif allow: skip_extras.discard("英语成绩")
    field = lambda label: facts.get(label, f"【{label}待补充】")
    profile = []
    if "姓名" not in omissions: profile.append(f"我叫{field('姓名')}")
    if "学院" not in omissions: profile.append(f"现就读于{field('学院')}")
    if "专业" not in omissions: profile.append(f"所学专业为{field('专业')}")
    study = []
    if "绩点" not in omissions: study.append(f"绩点为{field('绩点')}")
    if "排名" not in omissions: study.append(f"排名为{field('排名')}")
    if "英语成绩" not in skip_extras:
        study.append(f"英语成绩为{extras.get('英语成绩', '【英语成绩待补充】')}")
    recent = next((item["content"] for item in reversed([*history, {"role": "user", "content": user_text}])
                   if item.get("role") == "user" and isinstance(item.get("content"), str)
                   and re.search(r"个人陈述|申请书|自荐信", item["content"])), user_text)
    title = "推免申请书" if "申请书" in recent and "个人陈述" not in recent else "保研个人陈述"
    target = (f"申请院校：{extras.get('目标院校', '【目标院校待补充】')}。\n\n"
              if "目标院校" not in skip_extras else "")
    # Avoid putting a hidden grade back into a free-text award description.
    award = facts.get("获奖", "")
    if ({"绩点", "排名"} & omissions) and re.search(r"绩点|GPA|成绩|分数|排名|名次", award, re.I):
        award = ""
    if any(label in omissions and facts.get(label) and facts[label] in award for label in ("绩点", "排名")):
        award = ""
    achievements = (f"我的获奖情况：{award}。\n\n" if award and "获奖" not in omissions else "")
    if "科研" not in omissions and facts.get("科研经历") == "无":
        achievements = "目前我暂无科研经历。\n\n" + achievements
    # Free-form statements may themselves contain a hidden name, grade or
    # school. Do not reintroduce excluded facts through those statements.
    if omissions or skip_extras:
        narrative = {}
    narrative = {key: value for key, value in narrative.items() if key not in narrative_omissions}
    experience = (f"我的相关经历：{narrative['经历']}。\n\n" if narrative.get("经历")
                  else "" if "经历" in narrative_omissions
                  else "【科研、课程项目或实践经历待补充】\n\n")
    intent = []
    if narrative.get("方向"):
        intent.append(f"我的申请方向是{narrative['方向']}")
    if narrative.get("动机"):
        intent.append(f"我的申请动机是{narrative['动机']}")
    intent_text = ("；".join(intent) + "。\n\n" if intent else
                   "" if {"动机", "方向"} <= narrative_omissions else
                   "【目标方向待补充】\n\n" if "动机" in narrative_omissions else
                   "【申请动机待补充】\n\n" if "方向" in narrative_omissions else
                   "【申请动机与目标方向待补充】\n\n")
    if len(intent) == 1:
        missing = "动机" if narrative.get("方向") else "方向"
        if missing not in narrative_omissions:
            intent_text += "【申请动机待补充】\n\n" if missing == "动机" else "【目标方向待补充】\n\n"
    plan = (f"我的学习与研究计划：{narrative['计划']}。\n\n" if narrative.get("计划")
            else "" if "计划" in narrative_omissions
            else "【未来学习与研究计划待补充】\n\n")
    note = "请补充【待补充】的内容，完成后可以在工作台保存草稿。"
    if title == "推免申请书":
        note += "这是一份陈述初稿；申请表、推荐信和附件请按目标院校要求另行准备。"
    if conflicted or extra_conflict or narrative_conflict:
        note += "部分信息有不同说法，请告诉我应使用哪一项。"
    return (f'<WritingBlock variant="document">\n## {title}\n\n尊敬的老师：\n\n'
            + ("，".join(profile) + "。\n\n" if profile else "")
            + ("我的" + "，".join(study) + "。\n\n" if study else "")
            + target + achievements + experience + intent_text + plan
            + "恳请老师审阅。\n\n此致\n敬礼！\n\n"
            + (f"申请人：{field('姓名')}\n" if "姓名" not in omissions else "")
            + "日期：【待补充】\n</WritingBlock>\n\n" + note)
