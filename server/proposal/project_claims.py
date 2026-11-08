"""Conservative checks for quantified project claims in generated drafts.

This covers a small set of high-impact commercial and survey figures; it does
not verify sources, other claims, or the accuracy of the student's information.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


_TOPICS = {
    "市场数据": re.compile(r"市场规模|市场容量|市场机会|市场潜力|市场总量|可及市场|目标市场规模|市场约|市场|\b(?:TAM|SAM|SOM)\b", re.I),
    "收入与利润": re.compile(r"营业收入|营收|销售额|销售收入|收入|利润|盈利|成交额|交易额"),
    "价格": re.compile(r"定价|售价|价格|单价|客单价|收费|每亩.{0,8}元"),
    "融资与股权": re.compile(r"融资|股权|估值|投资额|投资金额|出让|资金需求"),
    "用户与客户": re.compile(r"用户(?:数|量|规模)?|客户(?:数|量|规模)?|服务(?:人数|用户|农户)|付费(?:用户|客户)|覆盖(?:用户|人数|农户)?"),
    "专利与成果": re.compile(r"专利|软著|软件著作权|论文|获奖|奖项"),
    "问卷数量": re.compile(r"问卷"),
    "访谈数量": re.compile(r"访谈|采访|走访记录"),
    "宣讲场次": re.compile(r"宣讲|讲座|培训场次"),
    "调研覆盖范围": re.compile(r"行政村|村庄|社区|受访者|受访户|调查对象|抽取"),
    "效果与统计比例": re.compile(r"覆盖率|参与率|回收率|响应率|准确率|成功率|满意度|居民参与|"
                             r"调查(?:显示|结果|表明)|调研(?:显示|结果|表明)|"
                             r"问卷(?:显示|结果|表明)|受访者中|的人支持"),
}
_CHINESE_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                   "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CHINESE_NUMERAL = r"[零〇一二两三四五六七八九十百千万亿]+(?:点[零〇一二两三四五六七八九]+)?"
_CHINESE_APPROX = r"(?:十几|几十|几百|几千|数十|数百|数千|上百|上千)"
_VALUE = rf"(?:\d+(?:\.\d+)?|{_CHINESE_APPROX}|{_CHINESE_NUMERAL})"
_NUMBER = re.compile(
    rf"(?<![\d.零〇一二两三四五六七八九十百千万亿点])({_VALUE})\s*(亿元|万元|亿人|万人|万名|万位|万户|万家|"
    r"个行政村|行政村|个村庄|村庄|个社区|社区|元|亿|万|%|％|人|名|位|户|家|项|件|篇|份|场|次)(?![A-Za-z\d])"
)
_CHINESE_PERCENT = re.compile(rf"百分之\s*({_VALUE})")
_EXAMPLE = re.compile(r"示例|举例|例如|比如|假设|虚构|样例|范文")
_DENIAL = re.compile(r"(?:没有|尚未|未曾|从未|未|无|不是|不要|不应|不能|禁止).{0,20}(?:市场|收入|营收|利润|定价|价格|融资|股权|用户|客户|专利|获奖|论文|问卷|访谈|采访|走访|宣讲|调查|调研)")
_UNCERTAIN_SOURCE = re.compile(r"[？?]|是不是|是否|能否|能不能|多少|几何|吗(?:$|[，,。；;！!])|"
                               r"可能|也许|或许|大概|估计|预计|待确认|不清楚|不确定|未核实|尚不清楚")
_FACT_TOPICS = {
    "market_size": "市场规模", "market_potential": "市场潜力", "revenue": "营业收入",
    "annual_revenue": "营业收入", "price": "价格", "pricing": "定价", "funding": "融资",
    "funding_amount": "融资", "equity": "股权", "users": "用户数量", "user_count": "用户数量",
    "patents": "专利", "patent_count": "专利",
}


def _chinese_integer(raw: str) -> int | None:
    """Parse explicit standard Chinese cardinal numbers; ambiguous forms fail closed."""
    if not raw:
        return None
    if all(char in _CHINESE_DIGITS for char in raw):
        # "二三户" commonly means a range, not 23 households. Zero-bearing
        # digit sequences such as 二〇二六 are explicit positional numbers.
        if len(raw) > 1 and not any(char in {"零", "〇"} for char in raw):
            return None
        return int("".join(str(_CHINESE_DIGITS[char]) for char in raw))
    total = section = digit = 0
    previous_small = 10_000
    previous_large = 100_000_000_0000
    pending_digit = False
    last_unit = 0
    zero_after_unit = False
    for char in raw:
        if char in _CHINESE_DIGITS:
            value = _CHINESE_DIGITS[char]
            if value == 0:
                if pending_digit:
                    return None
                zero_after_unit = True
            else:
                if pending_digit:
                    return None
                digit = value
                pending_digit = True
            continue
        if char in {"十", "百", "千"}:
            unit = {"十": 10, "百": 100, "千": 1000}[char]
            if unit >= previous_small:
                return None
            if not pending_digit:
                if char != "十" or section != 0:
                    return None
                digit = 1
            section += digit * unit
            digit = 0
            pending_digit = False
            previous_small = unit
            last_unit = unit
            zero_after_unit = False
            continue
        if char in {"万", "亿"}:
            unit = {"万": 10_000, "亿": 100_000_000}[char]
            if unit >= previous_large:
                return None
            section += digit
            if section == 0:
                return None
            total += section * unit
            section = digit = 0
            pending_digit = False
            previous_small = 10_000
            previous_large = unit
            last_unit = unit
            zero_after_unit = False
            continue
        return None
    # 一百二 / 一万二 can mean 102/120 or 10002/12000. Do not silently
    # normalize these colloquial forms to one specific number.
    if pending_digit and last_unit >= 100 and not zero_after_unit:
        return None
    return total + section + digit


def _numeric_value(raw: str) -> Decimal | None:
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return Decimal(raw).normalize()
    pieces = raw.split("点")
    if len(pieces) > 2:
        return None
    whole = _chinese_integer(pieces[0])
    if whole is None:
        return None
    if len(pieces) == 1:
        return Decimal(whole)
    if not pieces[1] or any(char not in _CHINESE_DIGITS for char in pieces[1]):
        return None
    decimal = "".join(str(_CHINESE_DIGITS[char]) for char in pieces[1])
    return Decimal(f"{whole}.{decimal}").normalize()


def _normalized_number(raw: str, unit: str) -> tuple[Decimal, str] | None:
    try:
        value = _numeric_value(raw)
    except InvalidOperation:
        return None
    if value is None:
        # Keep an exact textual marker so an ambiguous numeral is never
        # dropped or equated to an invented precise value.
        return Decimal(-1), f"ambiguous:{raw}:{unit}"
    if unit in {"亿", "亿元", "万", "万元", "元"}:
        factor = Decimal(100_000_000) if unit.startswith("亿") else Decimal(10_000) if unit.startswith("万") else Decimal(1)
        return value * factor, "currency"
    if unit in {"%", "％"}:
        return value, "percent"
    if unit in {"亿人", "万人", "万名", "万位", "万户", "万家"}:
        factor = Decimal(100_000_000) if unit.startswith("亿") else Decimal(10_000)
        return value * factor, "人" if unit[-1] in {"人", "名", "位"} else unit[-1]
    if unit in {"名", "位"}:
        return value, "人"
    if unit in {"个行政村", "行政村"}:
        return value, "行政村"
    if unit in {"个村庄", "村庄"}:
        return value, "村庄"
    if unit in {"个社区", "社区"}:
        return value, "社区"
    return value, unit


def _claims(text: str, *, source: bool) -> dict[str, set[tuple[Decimal, str]]]:
    claims: dict[str, set[tuple[Decimal, str]]] = {}
    for line in re.split(r"[\n。；;！？!?]", text):
        if not line.strip() or (source and (_EXAMPLE.search(line) or _DENIAL.search(line) or _UNCERTAIN_SOURCE.search(line))):
            continue
        mentions = [(match.start(), match.end(), category)
                    for category, pattern in _TOPICS.items() for match in pattern.finditer(line)]
        amounts = [(match.start(), match.end(), match.group(1), match.group(2)) for match in _NUMBER.finditer(line)]
        amounts.extend((match.start(), match.end(), match.group(1), "%") for match in _CHINESE_PERCENT.finditer(line))
        for start, end, raw, unit in sorted(amounts):
            # The closest preceding indicator determines which claim the
            # number belongs to; do not let a team size justify a price.
            preceding = [item for item in mentions if item[1] <= start and start - item[1] <= 45]
            if unit in {"个行政村", "行政村", "个村庄", "村庄", "个社区", "社区"}:
                category = "调研覆盖范围"
            elif preceding:
                category = max(preceding, key=lambda item: item[1])[2]
            else:
                following = [item for item in mentions if item[0] >= end and item[0] - end <= 12]
                if not following:
                    continue
                category = min(following, key=lambda item: item[0])[2]
            normalized = _normalized_number(raw, unit)
            if normalized is not None:
                claims.setdefault(category, set()).add(normalized)
    return claims


def unsupported_project_numbers(
    skill: dict[str, Any], project: dict[str, Any], history: list[dict[str, Any]],
    documents: list[dict[str, Any]], content: str,
) -> list[str]:
    """Return labels for generated figures not found in relevant user input.

    Only explicit user turns, user-confirmed project facts and matching,
    user-confirmed source documents are used. This matching is deliberately
    conservative, and never turns a user's figure into an externally checked fact.
    """
    if (skill.get("category") not in {"competition", "research", "practice"}
            or not isinstance(content, str)):
        return []
    generated = _claims(content, source=False)
    if not generated:
        return []
    sources = [str(item.get("content") or "") for item in history if item.get("role") == "user"]
    facts = (project.get("state") or {}).get("confirmed_facts") or {}
    if isinstance(facts, dict):
        for key, label in _FACT_TOPICS.items():
            if isinstance(facts.get(key), (str, int, float)):
                sources.append(label + "：" + str(facts[key]))
    for document in documents:
        if (document.get("project_id") == project.get("id") and document.get("kind") == "source"
                and document.get("confirmed") in (True, 1) and document.get("confirmation_origin") == "user"
                and not document.get("low_confidence_count") and isinstance(document.get("extracted_text"), str)
                and not re.search(r"未能识别|读取组件不可用|仅提取|低置信度|替换字符|乱码",
                                  str(document.get("extraction_warning") or ""))):
            sources.append(document["extracted_text"][:100_000])
    supported: dict[str, set[tuple[Decimal, str]]] = {}
    for text in sources:
        for category, amounts in _claims(text, source=True).items():
            supported.setdefault(category, set()).update(amounts)
    return [category for category, amounts in generated.items()
            if not amounts <= supported.get(category, set()) or len(supported.get(category, set())) > 1]
