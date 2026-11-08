"""Detect a narrow set of direct contradictions in project drafts.

The absence of a warning does not verify a project claim. Only explicit,
recognizable statements are checked; proposed future work remains a proposal.
"""
from __future__ import annotations

import re
from typing import Any


_EXAMPLE = re.compile(r"示例|举例|例如|比如|假设|虚构|范文|样例|其他(?:团队|项目)|别人的|竞品(?:的)?")
_FUTURE = re.compile(r"(?:计划|(?<!模)拟(?!合|真)|打算|希望|准备|将来|未来|预计|预期|目标|争取|建议|可考虑|考虑|假设|如果|一旦|尚待|有待|尚需|将(?:要|会|来)?)(?![已获])")
_UNCERTAIN = re.compile(r"(?:是否|能否|有没有|有无|是不是).{0,15}(?:营收|收入|调研|调查|原型|样机|专利|实验|测试|试验)")
_SPLIT = re.compile(r"[，,；;。！？!?\n]|但是|但(?=目前|现在|尚|我们|我|已经|已|没有|未|还)|不过|(?:并且|并|同时|而且)(?=计划|拟|打算|准备|预计|未来|已|没有|尚未)")
_NO = r"(?:没有|没(?:有)?|尚未|还未|从未|未曾|不曾|暂无|尚无|未|无)"

_RULES = {
    "营收": {
        "denied": re.compile(rf"{_NO}.{{0,10}}(?:营收|营业收入|营业额|销售收入|销售额|流水|付费用户)(?!预测|预期|计划|目标)|(?:营收|营业收入|营业额|销售收入|销售额|流水)(?:目前|现在|尚)?(?:为|是|[：:=])?(?:零|0(?:\.0+)?)(?:元|万|万元)?(?![.\d])|(?:营收|营业收入|营业额|销售收入|销售额|流水)(?:目前|现在)?(?:还)?(?:没有|暂无|尚无)"),
        "affirmed": re.compile(r"(?:已有|已经|已|实际|现有|获得|取得|实现|产生|累计|达到|达成).{0,14}(?:营收|营业收入|营业额|销售收入|销售额|流水|付费用户)|(?:营收|营业收入|营业额|销售收入|销售额|流水).{0,8}(?:已达|达到|超过|为|是|[：:=])\s*[1-9一二两三四五六七八九]|(?:营收|营业收入|营业额|销售收入|销售额|流水)(?:已经|已)(?:实现|产生|超过|达到|有)"),
    },
    "市场调研": {
        "denied": re.compile(rf"{_NO}.{{0,12}}(?:市场调研|市场调查|用户调研|用户调查|问卷调查)|(?:市场调研|市场调查|用户调研|用户调查|问卷调查).{{0,4}}{_NO}.{{0,5}}(?:做|开展|进行|完成|实施)"),
        "affirmed": re.compile(r"(?:已经|已|完成了?|开展了|进行过|做过|做了|实施了|组织了).{0,12}(?:市场调研|市场调查|用户调研|用户调查|问卷调查)(?!方案|计划|设计|方法|流程|规划)|(?:市场调研|市场调查|用户调研|用户调查|问卷调查)(?:已经|已)(?:完成|开展|进行)|(?:市场调研|市场调查|用户调研|用户调查|问卷调查)(?:结果|数据)(?:显示|表明)|(?:问卷调查|市场调研|用户调研).{0,8}(?:回收|收集了|覆盖了)"),
    },
    "原型": {
        "denied": re.compile(rf"{_NO}.{{0,12}}(?:原型|样机|原型机|可用产品|成品)(?!计划|目标)|(?:原型|样机|原型机|可用产品|成品).{{0,5}}{_NO}.{{0,6}}(?:完成|搭建|建成|制作|开发|做出|形成)?"),
        "affirmed": re.compile(r"(?:已经|已|成功|完成了|开发了|做出了|制作了|搭建了|建成了|拥有|已有|现有).{0,12}(?:原型机|原型|样机|可用产品|成品)(?!方案|计划|设计|方法|流程|规划)|(?:原型机|原型|样机|可用产品|成品)(?:已经|已)(?:完成|搭建|建成|开发|制成|制作|形成|投入运行)"),
    },
    "专利": {
        "denied": re.compile(rf"{_NO}.{{0,12}}(?:专利|发明专利|实用新型)(?!计划|目标)|(?:专利|发明专利|实用新型).{{0,5}}{_NO}.{{0,6}}(?:申请|获得|授权|提交)?"),
        "affirmed": re.compile(r"(?:已经|已|成功|申请了|获得了|拥有|持有|取得了|获批了).{0,12}(?:发明专利|专利|实用新型)(?!方案|计划|设计|方法|流程|规划)|(?:发明专利|专利|实用新型)(?:已经|已)(?:申请|获得|授权|提交|获批)"),
    },
    "实验或测试": {
        "denied": re.compile(rf"{_NO}.{{0,12}}(?:实验|试验|测试|实测|验证)(?!计划|方案|目标)|(?:实验|试验|测试|实测|验证).{{0,4}}{_NO}.{{0,6}}(?:做|开展|进行|完成|实施)?"),
        "affirmed": re.compile(r"(?:已经|已|成功|完成了|开展了|进行了|做过|做了|实施了|通过了).{0,12}(?:实验|试验|测试|实测|验证)(?!方案|计划|设计|方法|流程|规划)|(?:实验|试验|测试|实测|验证)(?:已经|已)(?:完成|开展|进行|通过)|(?:实验|试验|测试|实测)(?:结果|数据)(?:显示|表明|证明)|(?:经过|通过)(?:实验|试验|测试|实测)(?:验证|证明|发现)"),
    },
}

_FACT_KEYS = {
    "revenue": "营收", "sales_revenue": "营收", "revenue_status": "营收",
    "market_research": "市场调研", "market_research_status": "市场调研",
    "prototype": "原型", "prototype_status": "原型", "has_prototype": "原型",
    "patent": "专利", "patents": "专利", "patent_status": "专利", "patent_count": "专利",
    "experiment": "实验或测试", "experiments": "实验或测试", "test_status": "实验或测试",
}


def _clauses(text: str) -> list[str]:
    return [clause.strip() for clause in _SPLIT.split(text) if clause.strip()]


def _events(text: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    # An example applies to its own sentence, not unrelated later statements.
    # Keeping the sentence intact here avoids interpreting the continuation of
    # "例如，..." as a separate real claim.
    for sentence in re.split(r"[。！？!?\n]", text):
        if _EXAMPLE.search(sentence):
            continue
        for clause in _clauses(sentence):
            if _UNCERTAIN.search(clause):
                continue
            for label, rule in _RULES.items():
                denied = bool(rule["denied"].search(clause))
                if denied:
                    result.setdefault(label, set()).add("denied")
                # A proposal or a denial is not a completed achievement.
                if not denied and not _FUTURE.search(clause) and rule["affirmed"].search(clause):
                    result.setdefault(label, set()).add("affirmed")
    return result


def _confirmed_sources(project: dict[str, Any], documents: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    facts = (project.get("state") or {}).get("confirmed_facts") or {}
    if isinstance(facts, dict):
        for key, value in facts.items():
            label = _FACT_KEYS.get(key)
            if label and (value is False or str(value).strip().lower() in {"无", "没有", "未完成", "否", "false", "0"}):
                result.append(f"没有{label}")
            elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
                result.append(str(value))
    project_id = str(project.get("id") or "")
    for document in documents:
        if (not project_id or document.get("project_id") != project_id or document.get("kind") != "source"
                or document.get("confirmed") not in (1, True) or document.get("confirmation_origin") != "user"
                or document.get("low_confidence_count") or re.search(r"未能识别|读取组件不可用|仅提取|低置信度|替换字符|乱码", str(document.get("extraction_warning") or ""))):
            continue
        text = document.get("extracted_text")
        if isinstance(text, str) and len(text) <= 100_000:
            result.append(text)
    return result


def project_fact_contradictions(
    skill: dict[str, Any], project: dict[str, Any], history: list[dict[str, Any]],
    documents: list[dict[str, Any]], content: str,
) -> list[str]:
    """Return topics where a completed claim conflicts with a stated absence.

    Confirmed source material establishes initial context. Explicit later user
    statements can revise it. If a single statement contains contradictory
    claims without a clear correction, err toward keeping the stated absence.
    """
    if skill.get("category") not in {"research", "competition", "practice"} or not isinstance(content, str):
        return []
    state: dict[str, str] = {}
    for source in _confirmed_sources(project, documents):
        for label, values in _events(source).items():
            if "denied" in values:
                state[label] = "denied"
            elif label not in state and "affirmed" in values:
                state[label] = "affirmed"
    for message in history:
        if message.get("role") != "user" or not isinstance(message.get("content"), str):
            continue
        for label, values in _events(message["content"]).items():
            state[label] = "denied" if "denied" in values else "affirmed"
    output = _events(content)
    return [label for label in _RULES if state.get(label) == "denied" and "affirmed" in output.get(label, set())]
