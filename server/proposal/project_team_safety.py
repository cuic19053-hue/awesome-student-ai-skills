"""Narrow evidence matching for team identity and project implementation claims.

A missing match means a statement needs the student's attention, not that it
is false. This deliberately does not claim to verify the complete document.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


_TEAM = re.compile(r"团队|项目组|小组|队员|成员|负责人|组长|队长|申请人|我们|本人|我(?:们)?")
_GROUP = re.compile(r"团队|项目组|小组|队员|成员|我们|均|全部|所有人|各自|分别")
_FUTURE = re.compile(r"建议|可考虑|可以考虑|考虑|不妨|尝试|(?<!模)拟(?!合|真)|计划|打算|准备|将来|未来|预计|预期|目标是|希望|尚待|有待|将(?:要|会|来)?")
_QUESTION = re.compile(r"[？?]|是否|是不是|有没有|能否|可否|何时|哪些|为什么|怎么|如何|吗(?:$|[，,；;。！？!])")
_EXAMPLE = re.compile(r"示例|例如|举例|比如|假设|虚构|范文|样例|其他(?:团队|项目)|别人的|竞品")
_NEGATION = re.compile(r"(?:没有|尚未|还未|从未|未曾|并未|并非|不是|未|无|不曾|不要|(?<!分)别).{0,18}(?:来自|就读|所属|学校|大学|学院|负责|分工|开发|研发|上线|原型|样机|完成|实现|监测|推送)")
_POLICY = re.compile(r"学校通知|官方通知|政策|评审规则|申报条件|参赛条件|申请资格|资格要求|按照.{0,12}通知|(?:须|必须|应当|要求).{0,14}(?:来自|就读|所属)")
_SCHOOL_NAME = r"(?:[A-Za-z]{1,12}|[\u4e00-\u9fffA-Za-z·]{2,22})(?:大学|学院)"
_SCHOOL = re.compile(
    r"(?:来自|就读于?|隶属于?|所属(?:学校)?(?:是|为|[：:])?|所在(?:学校)?(?:是|为|[：:])?)\s*(" + _SCHOOL_NAME + r")"
    r"|(?:团队学校|团队所属院校|所在院校|学校)\s*(?:是|为|[：:])\s*(" + _SCHOOL_NAME + r")",
    re.I,
)
_DENIED_SCHOOL = re.compile(r"(?:不来自|并非来自|不是|不属于|并非)(?:来自|属于|在)?\s*(" + _SCHOOL_NAME + r")", re.I)
_ROLES = {
    "硬件": re.compile(r"硬件|传感器|电路|嵌入式"),
    "软件": re.compile(r"软件|编程|程序|算法|客户端|平台开发|(?:技术|开发)团队.{0,12}(?:开发|维护)"),
    "市场": re.compile(r"市场|营销|推广|运营|品牌"),
    "调研": re.compile(r"调研|调查|访谈|研究"),
    "统筹": re.compile(r"统筹|组织协调|项目管理"),
    "材料": re.compile(r"文案|材料撰写|写作|文档"),
}
_ASSIGNMENT = re.compile(r"负责|分工|承担|分配|担任|分为.{0,6}(?:组|方向)")
_PERSON = re.compile(r"([\u4e00-\u9fff]{2,4}|[A-Za-z]{2,12})(?:主要|分别)?负责")
_GENERIC_PERSON = {"团队", "成员", "队员", "大家", "我们", "分别", "主要", "同学", "小组", "项目组"}
_DEVELOPED = re.compile(
    r"(?:已|已经|成功|完成).{0,8}(?:开发|研发|搭建|建立|构建|制作|实现)"
    r"|(?:开发了|研发了|搭建了|建设了|构建了|开发完成|研发完成|已开发|已研发)"
)
_PROTOTYPE = re.compile(r"(?:已|已经|成功|完成|拥有|已有|现有).{0,12}(?:原型机|原型|样机|可用产品|成品)|(?:原型机|原型|样机|可用产品|成品).{0,8}(?:已完成|已建成|已开发|已制作|已形成)")
_LIVE = re.compile(r"(?:已|已经|成功|完成|正式).{0,10}(?:上线|发布|投入使用|投入运行|部署运行)|(?:上线|发布|投入使用|投入运行)(?:了|完成)")
_FUNCTION = re.compile(r"实时监测|实时采集|自动监测|自动采集|自动(?:向.{0,8})?(?:发送|推送)|(?:实时|自动).{0,12}(?:发送|推送)|已实现.{0,14}(?:监测|采集|提示|推送|功能)")
_DENIED_IMPLEMENTATION = {
    "开发": re.compile(r"(?:尚未|还未|没有|没|未|并未).{0,12}(?:开发|研发|搭建|建立|构建|制作)|(?:开发|研发).{0,8}(?:尚未|还未|没有|没|未|并未).{0,5}(?:完成)?"),
    "原型": re.compile(r"(?:尚未|还未|没有|没|未|并未).{0,12}(?:原型|样机|成品)|(?:原型|样机|成品).{0,8}(?:尚未|还未|没有|没|未|并未)"),
    "上线": re.compile(r"(?:尚未|还未|没有|没|未|并未).{0,12}(?:上线|发布|投入使用|投入运行)|(?:上线|发布).{0,8}(?:尚未|还未|没有|没|未|并未)"),
    "功能": re.compile(r"(?:尚未|还未|没有|没|未|并未).{0,12}(?:实现|实时监测|自动监测|自动推送|功能)"),
}
_SPLIT = re.compile(r"[，,；;。！？!?\n]|但是|不过|但(?=是|我们|团队|项目|已|目|实|同时)")

# Only flag a few concrete implementation decisions seen in real outputs.
# "将采用" is a definite project plan even if it refers to the future;
# explicit suggestions, questions and examples remain suggestions.
_PLAN_SUGGESTION = re.compile(r"建议|考虑|不妨|可选|供参考|尚未确定|待确定|待讨论|待补充")
_PLAN_NEGATION = re.compile(r"(?:不|不要|没有|尚未|未|无需|不再|不会|不打算|不计划).{0,8}(?:采用|使用|引入|收取|抽佣|合作|定位|收费)")
_PLAN_PATTERNS = {
    "定位方案": re.compile(r"\bLBS\b|地理定位|定位技术|位置服务|实时定位", re.I),
    "收费方案": re.compile(r"抽佣|佣金|交易手续费|收取.{0,8}(?:服务费|手续费|费用)"),
    "安全效果": re.compile(r"(?:确保|保证|完全保障|绝对保障).{0,18}(?:交易|用户|学生|个人|信息|财产|双方).{0,6}安全"),
}
_COOPERATION = re.compile(r"合作|伙伴|联合推广")
_PARTNERS = {
    "校园组织": re.compile(r"社团|学生会"),
    "商家": re.compile(r"商家|商户"),
    "广告公司": re.compile(r"广告公司"),
}


def _plans(text: str) -> set[str]:
    result: set[str] = set()
    for match in re.finditer(r"[^。！？!?\n]+[。！？!?]?", text):
        sentence = match.group()
        if sentence.endswith(("?", "？")) or _QUESTION.search(sentence) or _EXAMPLE.search(sentence):
            continue
        for clause in _SPLIT.split(sentence):
            if _PLAN_NEGATION.search(clause) or _PLAN_SUGGESTION.search(clause):
                continue
            for label, pattern in _PLAN_PATTERNS.items():
                if pattern.search(clause):
                    result.add(label)
        if any(_COOPERATION.search(clause) and not _PLAN_NEGATION.search(clause) and not _PLAN_SUGGESTION.search(clause)
               for clause in _SPLIT.split(sentence)):
            result.update("合作安排:" + name for name, pattern in _PARTNERS.items() if pattern.search(sentence))
    return result


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).casefold())


def _placeholder_school(value: str) -> bool:
    return bool(re.search(r"^(?:x+|某+|待补充|未知|[x某]+)(?:大学|学院)$", _normalize(value), re.I))


def _clauses(text: str):
    for match in re.finditer(r"[^。！？!?\n]+[。！？!?]?", text):
        sentence = match.group()
        if sentence.endswith(("?", "？")):
            continue
        if not sentence or _EXAMPLE.search(sentence):
            continue
        team_context = bool(_TEAM.search(sentence))
        group_context = bool(_GROUP.search(sentence))
        for clause in _SPLIT.split(sentence):
            if not clause.strip() or _QUESTION.search(clause) or _NEGATION.search(clause) or _FUTURE.search(clause):
                continue
            yield clause.strip(), team_context, group_context


def _schools(text: str) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for clause, team_context, group_context in _clauses(text):
        if _POLICY.search(clause):
            continue
        for match in _SCHOOL.finditer(clause):
            name = _normalize(match.group(1) or match.group(2))
            if team_context or match.group(2):
                result.add((name, "group" if group_context else "individual"))
    return result


def _person(clause: str) -> str | None:
    titled = re.search(r"(组长|队长|负责人)(?:主要)?负责", clause)
    if titled:
        return titled.group(1)
    match = _PERSON.search(clause)
    if not match:
        return None
    name = match.group(1)
    for prefix in ("团队成员", "团队", "成员", "队员", "同学", "由"):
        if name.startswith(prefix) and len(name) > len(prefix) + 1:
            name = name[len(prefix):]
            break
    if name in _GENERIC_PERSON or len(name) < 2:
        return None
    return _normalize(name)


def _assignments(text: str) -> set[tuple[str, str | None]]:
    result: set[tuple[str, str | None]] = set()
    for clause, team_context, _ in _clauses(text):
        person = _person(clause)
        if (not team_context and person is None) or not _ASSIGNMENT.search(clause) or _POLICY.search(clause):
            continue
        for label, pattern in _ROLES.items():
            if pattern.search(clause):
                result.add((label, person))
    return result


def _implementation(text: str) -> set[str]:
    result: set[str] = set()
    for clause, _, _ in _clauses(text):
        if _POLICY.search(clause):
            continue
        if _DEVELOPED.search(clause):
            result.add("开发")
        if _PROTOTYPE.search(clause):
            result.add("原型")
        if _LIVE.search(clause):
            result.add("上线")
        if _FUNCTION.search(clause):
            result.add("功能")
    return result


def _non_policy_evidence(text: str) -> str:
    """Do not turn a notice's eligibility text into the team's own identity.

    A notice may contain commas between its heading and a requirement, so
    removing only the heading clause would leave a misleading positive claim.
    This filter applies only to evidence, not to the student's model output.
    """
    return "\n".join(sentence for sentence in re.split(r"(?<=[。！？!?])|\n", text)
                     if not _POLICY.search(sentence))


def _sources(project: dict[str, Any], documents: list[dict[str, Any]]) -> list[str]:
    sources: list[str] = []
    facts = (project.get("state") or {}).get("confirmed_facts") or {}
    if isinstance(facts, dict):
        for key in ("team_school", "team_university", "team_institution"):
            if isinstance(facts.get(key), str):
                sources.append("团队学校：" + facts[key])
        for key in ("team_roles", "team_assignments", "team_members"):
            if isinstance(facts.get(key), str):
                sources.append("团队分工：" + facts[key])
        for key in ("prototype_status", "project_status", "development_status", "product_stage"):
            if isinstance(facts.get(key), str):
                sources.append("项目" + facts[key])
    project_id = project.get("id")
    for document in documents:
        if (not project_id or document.get("project_id") != project_id or document.get("kind") != "source"
                or document.get("confirmed") not in (1, True) or document.get("confirmation_origin") != "user"
                or document.get("low_confidence_count")
                or re.search(r"未能识别|读取组件不可用|仅提取|低置信度|替换字符|乱码", str(document.get("extraction_warning") or ""))):
            continue
        text = document.get("extracted_text")
        if isinstance(text, str) and len(text) <= 100_000:
            sources.append(text)
    return sources


def unsupported_project_team_claims(
    skill: dict[str, Any], project: dict[str, Any], history: list[dict[str, Any]],
    documents: list[dict[str, Any]], content: str,
) -> list[str]:
    """Return labels of narrow affirmative claims lacking matching context."""
    if skill.get("category") not in {"research", "competition", "practice"} or not isinstance(content, str):
        return []
    schools = _schools(content)
    assignments = _assignments(content)
    implementation = _implementation(content)
    plans = _plans(content)
    if not (schools or assignments or implementation or plans):
        return []
    source_schools: set[tuple[str, str]] = set()
    source_assignments: set[tuple[str, str | None]] = set()
    source_implementation: set[str] = set()
    source_plans: set[str] = set()
    for source in _sources(project, documents):
        source = _non_policy_evidence(source)
        source_schools.update(_schools(source))
        source_assignments.update(_assignments(source))
        source_implementation.update(_implementation(source))
        source_plans.update(_plans(source))
    # Preserve ambiguity until the student explicitly corrects it. A later
    # correction supersedes prior values for that particular claim type.
    for item in history:
        if item.get("role") != "user" or not isinstance(item.get("content"), str):
            continue
        text = _non_policy_evidence(item["content"])
        school_values = _schools(text)
        assignment_values = _assignments(text)
        correction = bool(re.search(r"更正|纠正|改为|改成|应为|实际上|准确说", text))
        if not _QUESTION.search(text) and not _EXAMPLE.search(text):
            denied_schools = {_normalize(match.group(1)) for match in _DENIED_SCHOOL.finditer(text)}
            source_schools = {(school, role) for school, role in source_schools if school not in denied_schools}
        if correction and school_values:
            roles = {role for _, role in school_values}
            source_schools = {(school, role) for school, role in source_schools if role not in roles}
        if correction and assignment_values:
            roles = {role for role, _ in assignment_values}
            source_assignments = {(role, person) for role, person in source_assignments if role not in roles}
        source_schools.update(school_values)
        source_assignments.update(assignment_values)
        implementation_values = _implementation(text)
        for label, pattern in _DENIED_IMPLEMENTATION.items():
            clauses = _SPLIT.split(text)
            if any(pattern.search(clause) and not _QUESTION.search(clause) and not _EXAMPLE.search(clause)
                   for clause in clauses):
                source_implementation.discard(label)
                implementation_values.discard(label)
        source_implementation.update(implementation_values)
        # A later explicit denial retracts a previously mentioned plan.
        for clause in _SPLIT.split(text):
            if _PLAN_NEGATION.search(clause):
                source_plans.difference_update(label for label, pattern in _PLAN_PATTERNS.items() if pattern.search(clause))
        source_plans.update(_plans(text))

    issues: list[str] = []
    if any(_placeholder_school(name) or (name, role) not in source_schools
           or len({school for school, other_role in source_schools if other_role == role}) > 1
           for name, role in schools):
        issues.append("团队学校")
    if any((role, person) not in source_assignments and not (
        person is None and any(source_role == role for source_role, _ in source_assignments)
    ) for role, person in assignments):
        issues.append("团队分工")
    if implementation.intersection({"开发", "原型", "上线"}) - source_implementation:
        issues.append("开发状态")
    if "功能" in implementation and "功能" not in source_implementation:
        issues.append("项目功能")
    missing_plans = plans - source_plans
    if "定位方案" in missing_plans:
        issues.append("定位方案")
    if "收费方案" in missing_plans:
        issues.append("收费方案")
    if "安全效果" in missing_plans:
        issues.append("安全效果")
    if any(label.startswith("合作安排:") for label in missing_plans):
        issues.append("合作安排")
    return issues
