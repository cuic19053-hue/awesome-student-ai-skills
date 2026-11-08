"""Limited, non-authoritative suggestions for common student draft content.

These checks cannot establish truth, quality, eligibility or compliance with a
school template. They look only at saved, exportable section text, allowing
the student to combine suggested topics in a custom outline.
"""
from __future__ import annotations

import re
from typing import Any


_SUGGESTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "social-survey": (
        ("调研目标与对象", r"调研目标|调查目标|研究目标|调研对象|调查对象|研究对象|调研目的|调查目的|目标与对象"),
        ("调研方法", r"调研方法|调查方法|研究方法|调查设计|问卷|访谈|走访"),
        ("实施计划或日程", r"实施计划|实施安排|进度安排|日程安排|调研日程|实践日程|时间安排|阶段计划"),
        ("团队分工", r"团队(?:与|及)?分工|人员分工|团队成员|团队组成|成员职责|队员分工|队员职责"),
        ("安全保障", r"安全保障|安全措施|安全预案|应急预案|应急安排|安全防范"),
    ),
    "innovation-research": (
        ("研究问题与目标", r"研究问题|研究目标|选题背景|拟解决|要解决|研究目的"),
        ("研究方法或技术路线", r"研究方法|研究方案|技术路线|技术方案|实验方法"),
        ("实施计划", r"实施计划|实施安排|进度安排|研究进度|时间安排|阶段计划"),
    ),
    "challenge-cup": (
        ("选题背景或研究问题", r"选题背景|研究背景|调查背景|选题意义|研究问题|调查问题|拟解决|作品背景"),
        ("研究设计或制作方法", r"研究方法|研究设计|调查方法|调查设计|制作过程|设计方案|制作方法|技术路线|访谈|问卷"),
        ("进展、结果或后续计划", r"已有工作|研究结果|调查结果|项目进展|作品进展|阶段成果|后续计划|下一步|实施计划|测试验证"),
    ),
    "internet-plus": (
        ("目标用户与需求", r"目标用户|用户需求|服务对象|目标客户|客户需求|目标群体|用户痛点|需求分析|市场与用户|用户分析"),
        ("产品或解决方案", r"产品方案|产品或服务|核心产品|核心功能|服务方案|解决方案|技术方案|产品介绍"),
        ("运营或商业模式", r"商业模式|运营计划|运营方案|盈利模式|市场推广|销售渠道|获客渠道"),
        ("实施计划与团队", r"实施计划|进度安排|实施安排|团队(?:与|及)?分工|团队组成|团队成员|成员职责"),
    ),
    "internet-plus-red-tour": (
        ("服务地区与需求", r"服务地区|帮扶地区|实际需求|当地需求|目标群体|需求分析"),
        ("产品或服务方案", r"产品方案|服务方案|解决方案|产品或服务|核心产品|核心功能"),
        ("实施或后续安排", r"实践实施|实施计划|实施安排|后续计划|进度安排|阶段计划"),
        ("团队与分工", r"团队(?:与|及)?分工|人员分工|团队成员|团队组成|成员职责"),
    ),
    "graduate-recommendation": (
        ("学业或相关经历", r"学业|成绩|绩点|科研经历|研究经历|实践经历|学习情况"),
        ("申请动机与匹配", r"申请动机|申请原因|申请理由|专业匹配|研究兴趣|报考动机|选择原因"),
        ("后续学习或研究计划", r"学习计划|研究计划|未来规划|未来计划|读研计划|发展规划"),
    ),
}

_NOT_READY = re.compile(
    r"(?:尚未|暂未|还未|没有|暂无|尚无|还没|未|待)"
    r".{0,12}(?:确定|明确|制定|规划|安排|拟定|组建|分配|分工|计划|日程|目标|对象|方案|保障|方法|路线|结果|成果|进展|需求|动机|具体)"
    r"|(?:目标|对象|计划|日程|安排|分工|职责|组成|方案|保障|方法|路线|结果|成果|进展|需求|动机)"
    r".{0,12}(?:还没有|尚未|暂未|还未|没有|暂无|尚无|还没|未定|未确定|未明确|不确定|待定|待制定|待规划|待商议|有待|尚待|仍需|还需)"
    r"|尚不明确|尚不清楚|不确定|未确定|未明确|待商定|待确定|尚待确定|有待确定"
)
_POSTPONED = re.compile(
    r"(?:后续|之后|以后|将来|再).{0,12}(?:商量|商讨|商议|协商|讨论|研究|确定|规划|拟定|补充|完善)"
    r"|(?:还需|仍需|需要)(?:进一步)?(?:商量|商讨|商议|协商|讨论|研究|确定|规划|拟定|补充|完善)"
)
_FUTURE_EVIDENCE = {
    "实施计划或日程": re.compile(
        r"(?:第[一二三四五六七八九十\d]+(?:周|天|月|阶段)|(?:周|星期)[一二三四五六日天]|"
        r"每(?:天|周|月)|按(?:天|周|月)|前期|中期|后期|准备阶段|走访阶段|整理阶段)"
        r".{0,35}(?:开展|进行|完成|联系|访谈|调查|走访|发放|收集|整理|分析|实施|准备|安排)"
    ),
    "团队分工": re.compile(r"(?:组长|队长|负责人|队员|成员|同学).{0,24}(?:负责|承担|分工|记录|联系|沟通|访谈)"),
    "团队与分工": re.compile(r"(?:组长|队长|负责人|队员|成员|同学).{0,24}(?:负责|承担|分工|记录|联系|沟通|访谈)"),
    "实施计划与团队": re.compile(
        r"(?:第[一二三四五六七八九十\d]+(?:周|天|月|阶段)|(?:周|星期)[一二三四五六日天]|"
        r"每(?:天|周|月)|按(?:天|周|月)|前期|中期|后期).{0,35}(?:开展|进行|完成|联系|调查|走访|整理|实施)"
        r"|(?:组长|队长|负责人|队员|成员|同学).{0,24}(?:负责|承担|分工|记录|联系|沟通)"
    ),
}


def _topic_present(label: str, pattern: str, title: str, body: str) -> bool:
    """Avoid counting a section whose only mention says it is not planned."""
    parts = [part.strip() for part in re.split(
        r"[，,；;。！？!?\n]|但是|不过|但|(?=计划(?:第|在|按|于|由|采用|使用|通过|开展|进行))", body
    ) if part.strip()]
    useful = [part for part in parts if not _NOT_READY.search(part) and not _POSTPONED.search(part)]
    if any(re.search(pattern, part, re.I) for part in useful):
        return True
    if not re.search(pattern, title, re.I):
        return False
    if not any(_NOT_READY.search(part) or _POSTPONED.search(part) for part in parts):
        return True
    # “The date is not fixed, but week one is for interviews” and clear role
    # assignments can still be useful future plans rather than empty claims.
    evidence = _FUTURE_EVIDENCE.get(label)
    return bool(evidence and any(evidence.search(part) for part in useful))


def draft_content_suggestions(project: dict[str, Any]) -> list[str]:
    """Return broad missing-topic suggestions, independent of section IDs.

    Heading matches count only with nontrivial body text. Body matches let a
    combined or school-specific section satisfy multiple topics. Placeholder
    text alone never counts as substantive material.
    """
    state = project.get("state") or {}
    rules = _SUGGESTIONS.get(str(state.get("skill_id") or ""))
    if not rules:
        return []
    sections = project.get("sections") or {}
    visible: list[tuple[str, str]] = []
    for item in project.get("outline") or []:
        if not isinstance(item, dict):
            continue
        body = str(sections.get(item.get("id", "")) or "").strip()
        # Placeholders are not evidence of material, even when they mention a
        # desired topic. Tiny fragments should not make a topic look finished.
        body = re.sub(r"【[^】]*(?:待补充|待填写|未填写)[^】]*】|\{\{[^{}]+\}\}", "", body)
        if len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", body)) < 12:
            continue
        visible.append((str(item.get("title") or ""), body))
    return [label for label, pattern in rules if not any(
        _topic_present(label, pattern, title, body) for title, body in visible
    )]
