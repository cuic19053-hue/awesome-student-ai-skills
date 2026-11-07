#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_flavor_check.py — 申报书「AI 味 / 机器腔」检测与改写建议

为什么需要这个模块
------------------
用户反馈（2026-11-08）：「skill ai 味太浓了」。现有质检链路只覆盖
字数（build.py）、结构（SKILL.md 文字规定）、查重（plagiarism_checker）、
排版（layout_audit），**没有任何一环检测文风**。子 skill 里甚至同时存在
「禁用套话」条款与「金句模板（可直接套用）」，规则与模板互相打架，
导致模型稳定产出排比腔、空话腔。

本模块把「AI 味」拆成 6 个可量化维度，给出 0~100 分与逐条定位，
让文风从「只能靠人眼感觉」变成「可以跑测试、可以回归」。

6 个检测维度
------------
1. EMPTY_PHRASE   空话套话密度：命中禁用短语表（分通用 / 党政 / 申报三类）
2. PARALLELISM    排比对仗密度：连续 3 句以上同构句式
3. ABSTRACT_NOUN  抽象名词堆砌：连续抽象名词/大词，无具体指涉
4. SPECIFICITY    具体性不足：数字、专有名词、时间、地点密度过低
5. UNIFORMITY     句长均匀度：句长方差过小 = 机器腔
6. BOILERPLATE    模板化首尾：开头/结尾命中通用套式

设计约束
--------
- 纯函数、零第三方依赖、可离线单测
- 不修改输入文本，只报告
- 对「引用政策原文」场景有豁免参数（政策原文允许庄重书面语）

用法
----
    from utils.ai_flavor_check import check_ai_flavor, format_report

    report = check_ai_flavor(text)
    print(report.score)            # 0~100，越高越像人写
    print(report.hits)             # 逐条命中
    print(format_report(report))   # 人类可读报告

CLI：
    python3 utils/ai_flavor_check.py --file draft.txt
    python3 utils/ai_flavor_check.py --file draft.txt --json
    python3 utils/ai_flavor_check.py --file draft.txt --min-score 75
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 词表：空话套话
# ---------------------------------------------------------------------------
# 说明：这些短语本身并非错误，但在一篇 1500~2500 字的申报书里高频出现，
# 且几乎不携带可核查信息，就是典型的「AI 味」。判定看密度而非单次命中。

EMPTY_PHRASES_COMMON: Tuple[str, ...] = (
    # 万能拔高
    "具有重要意义",
    "具有重大意义",
    "具有深远意义",
    "意义重大",
    "影响深远",
    "作用显著",
    "效果显著",
    "成效显著",
    "成绩斐然",
    "成果丰硕",
    # 万能动作
    "高度重视",
    "充分重视",
    "切实增强",
    "切实提升",
    "不断提升",
    "持续提升",
    "进一步加强",
    "进一步完善",
    "进一步深化",
    "不断深化",
    "深入推进",
    "全面推进",
    "扎实开展",
    "稳步推进",
    "着力打造",
    "全力推动",
    # 万能评价
    "取得良好效果",
    "取得显著成效",
    "获得一致好评",
    "受到广泛好评",
    "得到充分肯定",
    "获得高度评价",
    # 万能衔接
    "与此同时",
    "在此基础上",
    "综上所述",
    "总而言之",
    "值得一提的是",
    "不难看出",
    "由此可见",
    "众所周知",
    # 万能努力
    "不懈努力",
    "刻苦钻研",
    "勤奋刻苦",
    "锐意进取",
    "开拓创新",
    "勇于探索",
    "敢于突破",
)

EMPTY_PHRASES_POLITICAL: Tuple[str, ...] = (
    "迈上新台阶",
    "开创新局面",
    "谱写新篇章",
    "踏上新征程",
    "展现新作为",
    "彰显新担当",
    "焕发新气象",
    "达到新高度",
    "进入新阶段",
    "实现新突破",
    "树立新标杆",
    "贡献青春力量",
    "绽放青春光彩",
    "书写青春华章",
    "以青春之我",
    "把青春献给",
    "坚定理想信念",
    "厚植家国情怀",
    "锤炼过硬本领",
    "砥砺意志品质",
)

EMPTY_PHRASES_APPLICATION: Tuple[str, ...] = (
    "综合素质突出",
    "全面发展",
    "品学兼优",
    "德智体美劳",
    "起到了模范带头作用",
    "发挥了示范引领作用",
    "树立了良好榜样",
    "在同学中树立了",
    "得到了师生的一致认可",
    "深受老师和同学的好评",
    "为集体作出了积极贡献",
    "为团队贡献了自己的力量",
    "奠定了坚实的基础",
    "打下了坚实的基础",
    "提供了有力支撑",
    "注入了强劲动力",
    "开辟了新的途径",
    "探索了新的模式",
)

ALL_EMPTY_PHRASES: Tuple[str, ...] = (
    EMPTY_PHRASES_COMMON + EMPTY_PHRASES_POLITICAL + EMPTY_PHRASES_APPLICATION
)

# ---------------------------------------------------------------------------
# 词表：抽象大词（无具体指涉时算堆砌）
# ---------------------------------------------------------------------------
ABSTRACT_NOUNS: Tuple[str, ...] = (
    "格局",
    "境界",
    "高度",
    "深度",
    "广度",
    "维度",
    "层面",
    "体系",
    "机制",
    "路径",
    "抓手",
    "载体",
    "平台",
    "生态",
    "闭环",
    "赋能",
    "助力",
    "引领",
    "驱动",
    "融合",
    "协同",
    "联动",
    "统筹",
    "闭环思维",
    "底层逻辑",
    "顶层设计",
    "系统性思维",
    "全局视野",
    "战略高度",
    "核心素养",
    "综合能力",
    "内生动力",
    "长效机制",
)

# ---------------------------------------------------------------------------
# 模板化首尾
# ---------------------------------------------------------------------------
BOILERPLATE_OPENINGS: Tuple[str, ...] = (
    "本人自入学以来",
    "自入学以来",
    "时光荏苒",
    "光阴似箭",
    "岁月如梭",
    "转眼间",
    "回首过去",
    "回顾过去的一年",
    "在过去的一年里",
    "一路走来",
)

BOILERPLATE_CLOSINGS: Tuple[str, ...] = (
    "特此申请",
    "恳请批准",
    "望批准",
    "请组织考验我",
    "请党组织考验我",
    "如有不足之处",
    "恳请老师和同学批评指正",
    "以上是我的申请",
    "在此郑重申请",
)

# ---------------------------------------------------------------------------
# 正则
# ---------------------------------------------------------------------------
# 切句：只用句末标点（。！？）与换行。
# 不用分号（；）——中文里分号用于并列列举，属正常书面语，
# 切开后每段结构相同会被误判为「排比对仗」。
_SENT_SPLIT = re.compile(r"(?<=[。！？\n])")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_NUMBERISH = re.compile(
    r"\d+(?:\.\d+)?%?"          # 123 / 12.5 / 30%
    r"|第[一二三四五六七八九十百千]+"  # 第三
    r"|[一二三四五六七八九十百千]+(?:项|个|次|篇|名|人|所|届|年|月|日|小时|分|元|万元)"
)
_PROPER_NOUN_HINT = re.compile(
    r"[A-Za-z]{2,}"             # 英文缩写 / 专有名词
    r"|《[^》]{1,40}》"          # 书名号引用
    r"|[\u4e00-\u9fff]{2,}(?:大学|学院|中学|小学|研究院|研究所|公司|集团|基金|协会|学会|杯|赛|项目|课程|实验|系统|模型|算法)"
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class FlavorHit:
    """单条命中。"""

    dimension: str          # 维度 key
    label: str              # 维度中文名
    detail: str             # 具体说明
    evidence: str           # 命中原文片段
    position: int           # 在原文中的字符偏移
    severity: str           # "high" | "medium" | "low"
    advice: str             # 改写建议

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class FlavorReport:
    """检测报告。"""

    score: float                       # 0~100，越高越像人写
    grade: str                         # "自然" / "轻微机器腔" / "明显 AI 味" / "重度 AI 味"
    text_length: int
    sentence_count: int
    hits: List[FlavorHit] = field(default_factory=list)
    dimensions: Dict[str, float] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    summary: str = ""

    @property
    def passed(self) -> bool:
        return self.score >= 75.0

    def to_dict(self) -> Dict[str, object]:
        return {
            "score": round(self.score, 2),
            "grade": self.grade,
            "passed": self.passed,
            "text_length": self.text_length,
            "sentence_count": self.sentence_count,
            "dimensions": {k: round(v, 2) for k, v in self.dimensions.items()},
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "hit_count": len(self.hits),
            "hits": [h.to_dict() for h in self.hits],
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def _split_sentences(text: str) -> List[str]:
    """按句末标点切句，保留原文，过滤空串。"""
    if not text:
        return []
    parts = [p.strip() for p in _SENT_SPLIT.split(text)]
    return [p for p in parts if p]


def _cjk_len(text: str) -> int:
    """中文字符数（不含标点/空白/英文）。"""
    return len(_CJK.findall(text))


def _count_occurrences(text: str, phrases: Iterable[str]) -> List[Tuple[str, int]]:
    """返回 (phrase, count) 列表，count>0 才保留。"""
    out: List[Tuple[str, int]] = []
    for p in phrases:
        c = text.count(p)
        if c > 0:
            out.append((p, c))
    return out


def _find_first_position(text: str, phrase: str) -> int:
    idx = text.find(phrase)
    return idx if idx >= 0 else -1


def _sent_len_profile(sentences: Sequence[str]) -> Tuple[float, float, float]:
    """返回 (平均句长, 标准差, 变异系数CV)。句长按中文字符计。"""
    lens = [_cjk_len(s) for s in sentences]
    lens = [n for n in lens if n > 0]
    if not lens:
        return 0.0, 0.0, 0.0
    mean = sum(lens) / len(lens)
    if len(lens) == 1:
        return mean, 0.0, 0.0
    var = sum((n - mean) ** 2 for n in lens) / len(lens)
    sd = math.sqrt(var)
    cv = sd / mean if mean else 0.0
    return mean, sd, cv


# ---------------------------------------------------------------------------
# 各维度检测
# ---------------------------------------------------------------------------
def _check_empty_phrases(text: str, cjk_total: int) -> Tuple[List[FlavorHit], float, Dict[str, float]]:
    """维度 1：空话套话密度。返回 (hits, 扣分, metrics)。"""
    hits: List[FlavorHit] = []
    total = 0
    detail_map: List[Tuple[str, Tuple[str, ...], str]] = [
        ("通用套话", EMPTY_PHRASES_COMMON, "medium"),
        ("党政套话", EMPTY_PHRASES_POLITICAL, "high"),
        ("申报套话", EMPTY_PHRASES_APPLICATION, "medium"),
    ]
    for label, table, sev in detail_map:
        for phrase, count in _count_occurrences(text, table):
            total += count
            hits.append(
                FlavorHit(
                    dimension="EMPTY_PHRASE",
                    label="空话套话",
                    detail=f"{label}「{phrase}」出现 {count} 次",
                    evidence=phrase,
                    position=_find_first_position(text, phrase),
                    severity=sev,
                    advice=f"删除或替换「{phrase}」，改写为可核查的具体事实（做了什么 / 得到什么结果 / 用什么数据证明）",
                )
            )

    # 密度：每千中文字命中次数
    density = (total / cjk_total * 1000) if cjk_total else 0.0
    # 阈值：≤3‰ 不扣分；3~8‰ 线性扣；≥8‰ 扣满
    if density <= 3:
        penalty = 0.0
    elif density >= 8:
        penalty = 25.0
    else:
        penalty = (density - 3) / 5 * 25.0
    return hits, penalty, {"empty_phrase_count": total, "empty_phrase_per_kchar": density}


def _strip_code_blocks(text: str) -> str:
    """移除「非散文」的围栏代码块，但保留代码块内的散文内容。

    背景：部分 skill 把范文正文包在 ``` 里（便于复制），这类内容仍应参与
    文风评分；而 ASCII 框图、代码、对话脚本则不应参与。

    判定：代码块内若中文占比足够高、且**不含框图字符**，视为散文，保留内容
    （去掉围栏）；否则整块移除。
    """
    BOX_RE = re.compile(r"[┌┐└┘├┤┬┴┼─│╔╗╚╝║═↓↑→←]")

    def _repl(m: re.Match) -> str:
        body = m.group(1)
        cjk = len(_CJK.findall(body))
        # 代码块内或紧邻的框图字符都算框图
        has_box = bool(BOX_RE.search(body)) or bool(BOX_RE.search(m.group(0)))
        if cjk >= 15 and cjk / max(len(body), 1) >= 0.15 and not has_box:
            return "\n" + body + "\n"
        return "\n"

    return re.sub(r"```[a-zA-Z0-9_-]*\n(.*?)```", _repl, text, flags=re.S)


def _is_structural_line(text: str) -> bool:
    """判断一段文本是否为 Markdown 结构行（表格 / 列表 / 引用 / 代码围栏 / 制表符框图）。

    这些行的「结构相同」是格式要求，不是 AI 腔，不能计入排比。
    """
    s = text.strip()
    if not s:
        return True
    # 表格行：以 | 开头，或包含 | 分隔且形如 | a | b |
    if s.startswith("|") or s.count("|") >= 2:
        return True
    # 表格分隔线：|---|---|
    if re.fullmatch(r"[\s|:\-]+", s):
        return True
    # 列表项：- / * / + / 1. / 1) / （1）
    if re.match(r"^([-*+]\s+|\d+[.)]\s+|\(\d+\)\s*|（\d+）\s*)", s):
        return True
    # 引用与代码围栏
    if s.startswith(">") or s.startswith("```"):
        return True
    # 表格单元格碎片（以 | 结尾）
    if s.endswith("|"):
        return True
    # 制表符/框图字符（ASCII 框图、树形结构）
    if re.search(r"[┌┐└┘├┤┬┴┼─│╔╗╚╝║═↓↑→←]", s):
        return True
    # 纯符号行
    if not _CJK.search(s) and not re.search(r"[A-Za-z]{2,}", s):
        return True
    # 参数/档位说明行：以加粗标签开头，如「**短版（约 360 字）**：…」
    # 这类是规范说明而非正文，其结构相同属正常
    if re.match(r"^\*\*[^*]{1,30}\*\*\s*[：:]", s):
        return True
    # 以编号/字母开头的定义行，如「H1: …」「阶段 1：…」
    if re.match(r"^[A-Z]\d+\s*[：:]", s) or re.match(r"^阶段\s*\d+", s):
        return True
    return False


def _check_parallelism(sentences: Sequence[str]) -> Tuple[List[FlavorHit], float, Dict[str, float]]:
    """维度 2：排比对仗密度。

    判定：连续 3 句以上，句首 2 字相同，或句长相近(±2字)且句首结构相似。

    重要：Markdown 表格行、列表项、引用块的结构相同属于格式要求，
    不计入排比（否则会大量误报格式说明类内容）。
    """
    hits: List[FlavorHit] = []
    runs: List[Tuple[int, int]] = []  # (start_idx, length)
    n = len(sentences)
    i = 0
    while i < n:
        # 结构行不参与排比判定，直接跳过
        if _is_structural_line(sentences[i]):
            i += 1
            continue
        j = i + 1
        while j < n:
            if _is_structural_line(sentences[j]):
                break
            a, b = sentences[j - 1], sentences[j]
            la, lb = _cjk_len(a), _cjk_len(b)
            same_prefix = len(a) >= 2 and len(b) >= 2 and a[:2] == b[:2]
            similar_len = la > 0 and lb > 0 and abs(la - lb) <= 2 and la >= 8
            if same_prefix or similar_len:
                j += 1
            else:
                break
        run_len = j - i
        if run_len >= 3:
            runs.append((i, run_len))
        i = j if j > i + 1 else i + 1

    parallel_sentences = 0
    for start, length in runs:
        parallel_sentences += length
        snippet = "".join(sentences[start:start + min(length, 3)])
        hits.append(
            FlavorHit(
                dimension="PARALLELISM",
                label="排比对仗",
                detail=f"第 {start + 1} 句起连续 {length} 句结构雷同",
                evidence=snippet[:120],
                position=-1,
                severity="high" if length >= 4 else "medium",
                advice="打散排比：把其中至少一句改写成含具体数字/时间/对象的事实句，并改变句长",
            )
        )

    ratio = (parallel_sentences / len(sentences)) if sentences else 0.0
    if ratio <= 0.10:
        penalty = 0.0
    elif ratio >= 0.35:
        penalty = 20.0
    else:
        penalty = (ratio - 0.10) / 0.25 * 20.0
    return hits, penalty, {"parallel_run_count": len(runs), "parallel_sentence_ratio": ratio}


def _check_abstract_nouns(text: str, cjk_total: int) -> Tuple[List[FlavorHit], float, Dict[str, float]]:
    """维度 3：抽象名词堆砌。"""
    hits: List[FlavorHit] = []
    total = 0
    for noun, count in _count_occurrences(text, ABSTRACT_NOUNS):
        total += count
        if count >= 2:
            hits.append(
                FlavorHit(
                    dimension="ABSTRACT_NOUN",
                    label="抽象名词堆砌",
                    detail=f"抽象大词「{noun}」出现 {count} 次",
                    evidence=noun,
                    position=_find_first_position(text, noun),
                    severity="medium",
                    advice=f"把「{noun}」落到具体对象：写清是什么机制/哪个平台/解决了谁的什么问题",
                )
            )

    density = (total / cjk_total * 1000) if cjk_total else 0.0
    if density <= 4:
        penalty = 0.0
    elif density >= 12:
        penalty = 15.0
    else:
        penalty = (density - 4) / 8 * 15.0
    return hits, penalty, {"abstract_noun_count": total, "abstract_noun_per_kchar": density}


def _check_specificity(text: str, cjk_total: int) -> Tuple[List[FlavorHit], float, Dict[str, float]]:
    """维度 4：具体性（数字 / 专有名词 / 时间）密度。"""
    hits: List[FlavorHit] = []
    numbers = _NUMBERISH.findall(text)
    proper = _PROPER_NOUN_HINT.findall(text)
    evidence_total = len(numbers) + len(proper)
    density = (evidence_total / cjk_total * 1000) if cjk_total else 0.0

    # 每千字至少 8 个具体锚点才算合格（1500 字约 12 个）
    if density < 4:
        hits.append(
            FlavorHit(
                dimension="SPECIFICITY",
                label="具体性不足",
                detail=f"全文仅 {evidence_total} 处数字/专名锚点，密度 {density:.1f}/千字（建议 ≥8）",
                evidence="",
                position=-1,
                severity="high",
                advice="补充可核查细节：具体时间、人数、名次、金额、课程名、项目名、机构名、量化结果",
            )
        )
        # 零锚点（通篇没有任何可核查事实）比「锚点偏少」严重得多，
        # 扣分需足以把它压到及格线以下，否则会漏判纯空洞文本。
        penalty = 35.0 if evidence_total == 0 else 28.0
    elif density < 8:
        hits.append(
            FlavorHit(
                dimension="SPECIFICITY",
                label="具体性不足",
                detail=f"具体锚点密度 {density:.1f}/千字，偏低（建议 ≥8）",
                evidence="",
                position=-1,
                severity="medium",
                advice="在空泛段落补 1~2 个具体数字或专有名词",
            )
        )
        penalty = (8 - density) / 4 * 15.0
    else:
        penalty = 0.0

    return hits, penalty, {
        "evidence_anchor_count": evidence_total,
        "evidence_anchor_per_kchar": density,
        "number_count": len(numbers),
        "proper_noun_count": len(proper),
    }


def _check_uniformity(sentences: Sequence[str]) -> Tuple[List[FlavorHit], float, Dict[str, float]]:
    """维度 5：句长均匀度（CV 过小 = 机器腔）。

    只统计散文句，排除 Markdown 表格行 / 列表项，否则格式行会拉低变异系数。
    """
    hits: List[FlavorHit] = []
    prose = [s for s in sentences if not _is_structural_line(s)]
    mean, sd, cv = _sent_len_profile(prose)
    penalty = 0.0
    if len(prose) >= 8:
        if cv < 0.25:
            hits.append(
                FlavorHit(
                    dimension="UNIFORMITY",
                    label="句长过于均匀",
                    detail=f"平均句长 {mean:.1f} 字，标准差 {sd:.1f}，变异系数 {cv:.2f}（建议 ≥0.35）",
                    evidence="",
                    position=-1,
                    severity="medium",
                    advice="长短句交替：插入 1 个 10 字以内的短句，或 1 个 60 字以上的长句承载细节",
                )
            )
            penalty = (0.35 - cv) / 0.35 * 15.0
        elif cv < 0.35:
            penalty = (0.35 - cv) / 0.35 * 10.0
    return hits, penalty, {"sentence_len_mean": mean, "sentence_len_sd": sd, "sentence_len_cv": cv}


def _check_boilerplate(text: str) -> Tuple[List[FlavorHit], float, Dict[str, float]]:
    """维度 6：模板化首尾。"""
    hits: List[FlavorHit] = []
    penalty = 0.0
    head = text[:200]
    tail = text[-300:]

    for phrase in BOILERPLATE_OPENINGS:
        if phrase in head:
            hits.append(
                FlavorHit(
                    dimension="BOILERPLATE",
                    label="模板化开头",
                    detail=f"开头命中「{phrase}」",
                    evidence=phrase,
                    position=_find_first_position(text, phrase),
                    severity="high",
                    advice="删掉时间感慨式开头，直接写一件具体的事（哪门课 / 哪个项目 / 哪个时间点的转折）",
                )
            )
            penalty += 8.0
            break

    for phrase in BOILERPLATE_CLOSINGS:
        if phrase in tail:
            hits.append(
                FlavorHit(
                    dimension="BOILERPLATE",
                    label="模板化结尾",
                    detail=f"结尾命中「{phrase}」",
                    evidence=phrase,
                    position=_find_first_position(text, phrase),
                    severity="low",
                    advice="「特此申请」属公文规范可保留；其余套式收尾建议替换为具体承诺或下一步计划",
                )
            )
            penalty += 4.0 if phrase != "特此申请" else 0.0
            break

    return hits, min(penalty, 12.0), {}


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def _grade(score: float) -> str:
    if score >= 85:
        return "自然"
    if score >= 75:
        return "轻微机器腔"
    if score >= 55:
        return "明显 AI 味"
    return "重度 AI 味"


def check_ai_flavor(
    text: str,
    *,
    allow_policy_quotes: bool = False,
    min_score: float = 75.0,
) -> FlavorReport:
    """检测文本的「AI 味」。

    Args:
        text: 待检测正文。
        allow_policy_quotes: 为 True 时，对「党政套话」维度的扣分减半
            （适用于大段引用政策原文/领导讲话的场景）。
        min_score: 及格线，仅用于 report.summary 的措辞，不影响 score 计算。

    Returns:
        FlavorReport
    """
    text = text or ""
    # 代码块（框图/示例数据）不参与文风评分：先剥离，避免把 ASCII 框图误判为排比
    text = _strip_code_blocks(text)
    sentences = _split_sentences(text)
    cjk_total = _cjk_len(text)

    if cjk_total == 0:
        # 剥离代码块后无散文可评（如纯框图 / 纯表格 / 空文本）。
        # 这不算「AI 味」，应视为不适用，passed=True 以免误伤格式内容。
        return FlavorReport(
            score=100.0,
            grade="无散文内容",
            text_length=0,
            sentence_count=0,
            hits=[],
            dimensions={},
            metrics={},
            summary="无散文正文可评（纯框图/表格/空文本），不计入 AI 味。",
        )

    hits: List[FlavorHit] = []
    penalties: Dict[str, float] = {}
    metrics: Dict[str, float] = {}

    for fn, key in (
        (lambda: _check_empty_phrases(text, cjk_total), "EMPTY_PHRASE"),
        (lambda: _check_parallelism(sentences), "PARALLELISM"),
        (lambda: _check_abstract_nouns(text, cjk_total), "ABSTRACT_NOUN"),
        (lambda: _check_specificity(text, cjk_total), "SPECIFICITY"),
        (lambda: _check_uniformity(sentences), "UNIFORMITY"),
        (lambda: _check_boilerplate(text), "BOILERPLATE"),
    ):
        h, p, m = fn()
        hits.extend(h)
        penalties[key] = p
        metrics.update(m)

    if allow_policy_quotes:
        penalties["EMPTY_PHRASE"] *= 0.5

    total_penalty = sum(penalties.values())
    score = max(0.0, min(100.0, 100.0 - total_penalty))
    grade = _grade(score)

    # 严重度排序：high 优先，其次按维度扣分
    sev_order = {"high": 0, "medium": 1, "low": 2}
    hits.sort(key=lambda h: (sev_order.get(h.severity, 3), -penalties.get(h.dimension, 0.0)))

    top_dims = sorted(penalties.items(), key=lambda kv: -kv[1])
    top_dims = [(k, v) for k, v in top_dims if v > 0][:3]
    if top_dims:
        dim_cn = {
            "EMPTY_PHRASE": "空话套话",
            "PARALLELISM": "排比对仗",
            "ABSTRACT_NOUN": "抽象名词堆砌",
            "SPECIFICITY": "具体性不足",
            "UNIFORMITY": "句长过于均匀",
            "BOILERPLATE": "模板化首尾",
        }
        parts = [f"{dim_cn.get(k, k)}（-{v:.1f}）" for k, v in top_dims]
        summary = f"{grade}：得分 {score:.1f}，主要失分项 {'、'.join(parts)}。"
    else:
        summary = f"{grade}：得分 {score:.1f}，未发现明显机器腔特征。"

    return FlavorReport(
        score=score,
        grade=grade,
        text_length=cjk_total,
        sentence_count=len(sentences),
        hits=hits,
        dimensions=penalties,
        metrics=metrics,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# 报告格式化
# ---------------------------------------------------------------------------
def format_report(report: FlavorReport, *, max_hits: int = 20) -> str:
    """把报告格式化为人类可读文本。"""
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("AI 味检测报告")
    lines.append("=" * 60)
    lines.append(f"得分      : {report.score:.1f} / 100")
    lines.append(f"评级      : {report.grade}")
    lines.append(f"中文字数  : {report.text_length}")
    lines.append(f"句数      : {report.sentence_count}")
    lines.append(f"命中条数  : {len(report.hits)}")
    lines.append("")
    lines.append("维度扣分：")
    dim_cn = {
        "EMPTY_PHRASE": "空话套话",
        "PARALLELISM": "排比对仗",
        "ABSTRACT_NOUN": "抽象名词堆砌",
        "SPECIFICITY": "具体性不足",
        "UNIFORMITY": "句长过于均匀",
        "BOILERPLATE": "模板化首尾",
    }
    for key, val in report.dimensions.items():
        lines.append(f"  - {dim_cn.get(key, key):<12} -{val:.1f}")
    lines.append("")
    if report.hits:
        lines.append(f"问题清单（前 {min(len(report.hits), max_hits)} 条）：")
        for i, h in enumerate(report.hits[:max_hits], 1):
            lines.append(f"  {i}. [{h.severity.upper()}] {h.label}：{h.detail}")
            if h.evidence:
                lines.append(f"     原文：{h.evidence[:80]}")
            lines.append(f"     建议：{h.advice}")
    else:
        lines.append("未发现明显 AI 味特征。")
    lines.append("")
    lines.append(f"结论：{report.summary}")
    lines.append("=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="申报书 AI 味 / 机器腔检测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例：
  python3 utils/ai_flavor_check.py --file draft.txt
  python3 utils/ai_flavor_check.py --file draft.txt --json
  python3 utils/ai_flavor_check.py --file draft.txt --min-score 80
  python3 utils/ai_flavor_check.py --text "本人自入学以来，始终高度重视..."
""",
    )
    p.add_argument("--text", help="待检测文本（与 --file 二选一）")
    p.add_argument("--file", help="待检测文本文件路径")
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="及格线；给出时，低于该分数以退出码 1 结束（用于 CI 门禁）",
    )
    p.add_argument(
        "--allow-policy-quotes",
        action="store_true",
        help="允许大段政策原文引用（空话维度扣分减半）",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = _build_arg_parser()
    args = ap.parse_args(argv)

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        ap.error("必须提供 --text 或 --file")

    report = check_ai_flavor(text, allow_policy_quotes=args.allow_policy_quotes)

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report(report))

    if args.min_score is not None and report.score < args.min_score:
        if not args.json:
            print(f"\n❌ 未达及格线 {args.min_score}（实际 {report.score:.1f}）")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
