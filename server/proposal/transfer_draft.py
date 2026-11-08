"""A bounded first draft for a student's explicit major-transfer request.

This builds only from narrowly recognized self-statements. It is a starter
rather than an eligibility decision or a substitute for the school's notice.
"""
from __future__ import annotations

import re
from typing import Any

from .chat_context import _is_personal_draft_request


def is_transfer_draft_request(text: str, project: dict[str, Any]) -> bool:
    if (project.get("state") or {}).get("skill_id") != "major-transfer":
        return False
    if re.search(r"(?:不要|不想|不必|先别|无需|不用|暂时不|不需要)(?:帮我|再|先|现在|直接)?(?:写|生成|起草|撰写).{0,12}(?:申请书|正文|草稿)", text):
        return False
    # Omitting one field does not cancel a separate request for the draft.
    clauses = re.split(r"[，,；;。！？!?\n]", text)
    intent = "。".join(part for part in clauses if not (
        re.search(r"(?:不要|别|禁止|不可|不能|无需|不必)(?:写|填写|写入|提|展示|透露|使用).{0,8}(?:姓名|名字|专业)", part)
        and not re.search(r"申请书|正文|草稿", part)
    ))
    return _is_personal_draft_request(intent, r"(?:转专业|专业调整|转系)")


_STOP = r"(?:专业|[，,。；;！!？?\n]|(?=想转|希望转|准备转|申请转|因为|由于)|$)"
_PATTERNS = {
    "姓名": re.compile(r"(?:我叫|我名叫|(?:我的)?姓名\s*[：:=])\s*([\u4e00-\u9fffA-Za-z·]{2,12}?)(?=[，,。；;！!？?\n]|(?:并|现在|目前|现学|我|是|专业)|$)"),
    "原专业": re.compile(r"(?:(?:现|目前|现在)(?:在)?(?:学习|学|就读于|读)|原专业(?:是|为|改为|改成|[：:=])|目前专业(?:是|为|改为|改成|[：:=])|现专业(?:是|为|改为|改成|[：:=]))\s*([\u4e00-\u9fffA-Za-z0-9·]{2,24}?)" + _STOP),
    "目标专业": re.compile(r"(?:(?:想|希望|准备|申请|拟|要)?转(?:到|入)?(?:读)?|目标专业(?:是|为|改为|改成|[：:=]))\s*([\u4e00-\u9fffA-Za-z0-9·]{2,24}?)" + _STOP),
}
_BAD = re.compile(r"(?:示例|举例|例如|比如|假设|虚构|朋友|同学|他人|别人)")


def _fields(text: str) -> dict[str, str]:
    if _BAD.search(text):
        return {}
    found: dict[str, str] = {}
    for label, pattern in _PATTERNS.items():
        values = {m.group(1).strip() for m in pattern.finditer(text)}
        values = {v for v in values if v not in {"专业", "专业申请书", "申请书", "现在的专业", "目标专业"}}
        if len(values) == 1:
            found[label] = values.pop()
        elif len(values) > 1:
            found[label] = ""
    for clause in re.split(r"[，,；;。！？!?\n]", text):
        if (not re.search(r"不|没|无|未|并非|并不", clause)
                and re.search(r"(?:对[^，。；;！？!?\n]{1,15}(?:感兴趣|有兴趣)|喜欢(?:编程|计算机)|热爱(?:编程|计算机))", clause)):
            found["兴趣"] = "是"
    return found


def transfer_student_facts(history: list[dict[str, Any]], user_text: str) -> tuple[dict[str, str], bool, set[str]]:
    facts: dict[str, str] = {}
    conflicts: set[str] = set()
    omitted: set[str] = set()
    for item in [*history, {"role": "user", "content": user_text}]:
        if item.get("role") != "user" or not isinstance(item.get("content"), str):
            continue
        text = item["content"]
        if re.search(r"(?:不要|别|禁止|不可|不能)(?:再)?(?:使用|写|填写|写入|引用|展示|透露).{0,8}(?:我的|本人|个人)?(?:资料|信息)", text):
            facts.clear()
            conflicts.clear()
            omitted.update({"姓名", "原专业", "目标专业", "兴趣"})
            continue
        if re.search(r"(?:可以|允许|同意|恢复)(?:再|重新|继续)?(?:使用|填写|写入|引用).{0,8}(?:我的|本人|个人)?(?:资料|信息)", text):
            omitted.difference_update({"姓名", "原专业", "目标专业", "兴趣"})
        for clause in re.split(r"[，,；;。！？!?\n]", text):
            if re.search(r"(?:不要|别|禁止|不可|不能|无需|不必)(?:再)?(?:写|填写|写入|提|展示|透露|使用)", clause):
                if re.search(r"姓名|名字", clause):
                    omitted.add("姓名")
                if re.search(r"专业", clause) and not re.search(r"申请书|草稿|正文", clause):
                    omitted.update({"原专业", "目标专业"})
            elif re.search(r"(?:可以|允许|同意|恢复).{0,8}(?:写|填写|提|使用)", clause):
                if re.search(r"姓名|名字", clause):
                    omitted.discard("姓名")
                if re.search(r"专业", clause):
                    omitted.difference_update({"原专业", "目标专业"})
        values = _fields(text)
        correction = bool(re.search(r"更正|纠正|改为|改成|更新为", text))
        for label, value in values.items():
            if not value:
                facts.pop(label, None)
                conflicts.add(label)
            elif correction:
                facts[label] = value
                conflicts.discard(label)
            elif label in conflicts:
                continue
            elif label in facts and facts[label] != value:
                facts.pop(label, None)
                conflicts.add(label)
            else:
                facts[label] = value
    return facts, bool(conflicts), omitted


def transfer_draft(facts: dict[str, str], *, conflicted: bool = False, omitted: set[str] | None = None) -> str:
    omitted = omitted or set()
    field = lambda label: facts.get(label, f"【{label}待补充】")
    origin = "" if "原专业" in omitted else f"我目前学习{field('原专业')}专业。"
    target = "申请转专业" if "目标专业" in omitted else f"申请转入{field('目标专业')}专业"
    reason = "我对目标方向感兴趣，希望进一步学习相关知识。" if facts.get("兴趣") and "兴趣" not in omitted else "【转专业的具体原因待补充】"
    closing_name = "" if "姓名" in omitted else f"申请人：{field('姓名')}\n"
    note = "请补充【待补充】的内容，完成后可以在工作台保存草稿。学校具体要求请以本校通知为准。"
    if conflicted:
        note += "部分信息有不同说法，请告诉我应使用哪一项。"
    return (f'<WritingBlock variant="document">\n## 转专业申请书\n\n尊敬的老师：\n\n'
            f'{origin}我希望{target}，现向老师提出申请。\n\n'
            f'【现专业学习情况待补充】\n\n{reason}\n\n【对目标专业课程和培养方向的认识待补充】\n\n'
            f'【转入后的学习计划待补充】\n\n恳请老师审阅。\n\n此致\n敬礼！\n\n{closing_name}'
            f'日期：【待补充】\n</WritingBlock>\n\n{note}')
