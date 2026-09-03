#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plagiarism_checker.py — 大学生申报书查重预检模块

本模块用于检测学生填写的申报书文本与网络常见模板/党政原文的相似度，
防止抄袭导致的党支部查重不合格、评审扣分或一票否决。

主要功能：
    1. check_plagiarism(text, skill_name) — 主入口，返回完整查重报告
    2. ngram_similarity(text1, text2, n=3) — N-gram Jaccard 相似度
    3. find_longest_common_substring(text1, text2) — 最长公共子串
    4. highlight_plagiarism(text, threshold=0.3) — 高亮疑似抄袭段
    5. CLI 接口：python plagiarism_checker.py --text "xxx" --skill national_project_eval

内置 30+ 网络模板特征句库（按子 skill 分类）+ 党政原文金句库。

Author: T38 子智能体
Version: 1.0.0
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Set

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CRITERIA_PATH = os.path.join(THIS_DIR, "review_criteria.json")

# ---------------------------------------------------------------------------
# 预处理工具
# ---------------------------------------------------------------------------
_PUNCT_RE = re.compile(r"[，。；：！？、“”‘’（）《》【】「」()[]{},.;:!?\\\s]+")
_SPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """文本标准化：去除多余空白与标点，仅保留汉字/字母/数字。"""
    if not text:
        return ""
    text = text.replace("\r", "").replace("\n", "")
    text = _PUNCT_RE.sub("", text)
    return text.lower()


def _split_sentences(text: str) -> List[str]:
    """按句末标点切句（保留原文，仅去空白）。"""
    if not text:
        return []
    raw = re.split(r"(?<=[。！？；\n])", text)
    out = []
    for s in raw:
        s = s.strip()
        if len(s) >= 6:
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# 模板特征句库（按子 skill 分类，每类至少 3-5 条典型网络套话）
# ---------------------------------------------------------------------------
TEMPLATE_LIBRARY: Dict[str, List[str]] = {
    "national_project_eval": [
        "本人自入学以来，始终把学习放在第一位，努力提升综合素质",
        "在思想品德方面，本人积极向党组织靠拢，认真学习党的理论知识",
        "经过不懈努力，本人在学业上取得了优异成绩，综合排名位于专业前茅",
        "在课余时间，本人积极参加各类学科竞赛和社会实践活动",
        "本人深知荣誉属于过去，未来仍需继续努力，特此申请国家奖学金",
        "在导师的悉心指导下，本人参与了多项科研项目，并取得了一定成果",
        "本人在班级中担任班干部，积极协助辅导员完成各项工作",
    ],
    "motivation_scholarship": [
        "我家住在一个偏远的小山村，父母都是普通的农民，家庭经济条件十分困难",
        "为了减轻家庭负担，我在校期间积极参加勤工助学岗位",
        "虽然家庭经济困难，但我从未放弃对知识的渴望和对未来的追求",
        "我深知知识改变命运的道理，因此在学习上格外刻苦",
        "特此申请国家励志奖学金，希望能够帮助我顺利完成学业",
        "在生活上，我始终保持艰苦朴素的作风，从不与他人攀比",
    ],
    "university_scholarship": [
        "本学年我在学习上取得了较大进步，特此申请校级奖学金",
        "在校期间，我严格遵守学校各项规章制度，尊敬师长，团结同学",
        "本人在本学年参加了多项校园文化活动，丰富了课余生活",
        "经过一年的努力，我的学习成绩有了明显提高",
        "希望能够获得奖学金以资鼓励，今后我将继续努力",
    ],
    "enterprise_scholarship": [
        "我对贵公司所在的行业充满热情，立志未来从事相关工作",
        "在校期间，我选修了多门与贵公司业务相关的课程",
        "我希望通过贵公司的奖学金资助，能够更加专注于学业",
        "我的职业规划与贵公司的发展方向高度契合",
        "贵公司的企业文化深深吸引了我，我希望未来能加入贵公司",
    ],
    "single_scholarship": [
        "本人在XX方面表现突出，特此申请XX单项奖学金",
        "在过去一年中，我在XX方面取得了显著成绩",
        "本人在XX领域的成果得到了师生的一致认可",
        "希望通过此次申请，能够激励自己在XX方面继续深造",
    ],
    "innovation_research": [
        "本项目具有重要的理论意义和实践价值",
        "本项目的创新点在于提出了全新的研究方法",
        "本项目的研究内容填补了国内相关领域的空白",
        "本项目团队成员专业互补，分工明确，具有较强的研究能力",
        "本项目预期发表 SCI 论文 X 篇，申请专利 X 项",
        "在指导教师的悉心指导下，本项目按计划稳步推进",
    ],
    "entrepreneurship_training": [
        "本项目立足市场需求，致力于打造全新的商业模式",
        "经过深入的市场调研，我们发现了一个巨大的市场机会",
        "本项目的核心竞争力在于差异化的产品定位",
        "我们的团队由来自不同专业的同学组成，具有较强的执行力",
        "预计项目实施一年后可实现盈利",
    ],
    "entrepreneurship_practice": [
        "我公司自成立以来，秉承创新驱动的理念，取得了快速发展",
        "公司目前拥有员工 XX 人，年营收达到 XX 万元",
        "我们通过技术创新，成功解决了行业内的卡脖子问题",
        "公司已获得 XX 轮融资，估值达到 XX 万元",
        "在未来三年内，公司计划拓展至全国市场",
    ],
    "challenge_cup": [
        "本研究围绕 XX 问题展开，旨在探索 XX 的新方法",
        "本研究采用了 XX 方法，对 XX 进行了深入分析",
        "研究结果表明，本方法在 XX 方面具有显著优势",
        "本研究的创新性主要体现在 XX 方面",
        "本研究对 XX 领域具有一定的理论贡献和实践意义",
    ],
    "internet_plus": [
        "本项目积极响应国家'大众创业、万众创新'的号召",
        "本项目依托互联网技术，打造了全新的服务平台",
        "我们的项目已经获得了 XX 项专利和 XX 项软件著作权",
        "项目实施以来，已服务用户 XX 万人次，产生社会效益 XX",
        "本项目获得了 XX 投资机构的关注，正在进行 A 轮融资",
    ],
    "graduate_recommendation": [
        "本人在本科期间始终保持优异的学习成绩，综合排名位于专业前列",
        "在科研方面，本人参与了 XX 课题，并以第一作者身份发表了论文",
        "本人对 XX 方向具有浓厚兴趣，希望在研究生阶段继续深造",
        "本人的英语水平良好，已通过大学英语六级考试",
        "特此申请保研推免资格，希望能够进入贵校继续学习",
    ],
    "outstanding_graduate": [
        "大学四年，本人在思想、学习、工作、生活等方面都取得了长足进步",
        "在学习上，本人始终严格要求自己，GPA 位于专业前 XX%",
        "在科研方面，本人参与了多项课题，并取得了一定成果",
        "在社会实践方面，本人积极参加志愿服务和实习活动",
        "本人即将毕业，特此申请优秀毕业生称号",
    ],
    "youth_league_application": [
        "我志愿加入中国共产党，拥护党的纲领，遵守党的章程",
        "中国共产党是中国工人阶级的先锋队，同时是中国人民和中华民族的先锋队",
        "我深知，加入中国共产党是一种光荣，更是一种责任",
        "我将以党员的标准严格要求自己，努力在各方面发挥先锋模范作用",
        "请党组织在实践中考验我",
        "如果党组织批准我的申请，我将……如果党组织暂时没有批准，我也不会气馁",
        "我认真学习马克思列宁主义、毛泽东思想、邓小平理论、'三个代表'重要思想",
    ],
    "summary_report": [
        "敬爱的党组织：本季度我在思想、学习、工作等方面都取得了一定进步",
        "通过本季度的理论学习，我对 XX 有了更加深刻的认识",
        "在学习上，本季度我认真完成了各项学习任务，取得了较好成绩",
        "在思想上，我始终与党中央保持高度一致",
        "本季度我也存在一些不足，主要表现在 XX 方面",
        "下一步，我将以 XX 为重点，努力提升自己",
    ],
    "youth_league_application": [
        "在预备期内，我在思想、学习、工作等方面都取得了新的进步",
        "现将我一年来的预备期情况向党组织汇报如下",
        "在理论学习方面，我认真学习了党的最新理论成果",
        "在支部活动方面，我积极参加党组织开展的各项活动",
        "我深知自己还存在一些不足，主要表现在 XX 方面",
        "无论党组织是否批准我按期转正，我都将以党员标准严格要求自己",
    ],
    "college_research": [
        "本项目旨在探索 XX 问题，具有一定的学术价值",
        "本项目研究内容明确，技术路线清晰，具有较强的可行性",
        "在指导教师的指导下，本项目按计划稳步推进",
        "预期成果为论文 X 篇，调研报告 X 份",
    ],
    "university_research": [
        "本项目立足学科前沿，具有重要的研究价值",
        "本项目的创新性体现在研究方法和研究视角两个方面",
        "团队成员专业互补，指导教师具有丰富的研究经验",
        "本项目预期发表高水平论文 X 篇，申请专利 X 项",
    ],
    "social_survey": [
        "为了解 XX 现状，我们开展了本次社会调查",
        "本次调查采用问卷调查与深度访谈相结合的方法",
        "本次调查共发放问卷 XX 份，回收有效问卷 XX 份",
        "通过对调查数据的分析，我们得出以下结论",
        "基于上述结论，我们提出以下建议",
    ],
    "outstanding_student": [
        "本人在思想、学习、工作、身体等方面均取得了显著进步",
        "本学年，本人学习成绩位于班级前列，体育达标",
        "本人积极参加班级活动，与同学关系融洽",
        "特此申请优秀学生/三好学生称号",
    ],
    "civilized_student": [
        "本人在课堂纪律、宿舍卫生、网络文明等方面严格要求自己",
        "本人始终保持良好的学习习惯，课堂出勤率 100%",
        "在宿舍卫生方面，本人所在宿舍多次被评为优秀宿舍",
        "在网络空间，本人不传谣、不信谣，文明发言",
        "特此申请文明大学生称号",
    ],
    "outstanding_cadre": [
        "本人在担任 XX 期间，认真履行职责，积极组织开展各项活动",
        "在任职期间，我组织了 XX 等多项活动，受到师生好评",
        "作为学生干部，我始终以身作则，发挥模范带头作用",
        "在班级工作中，我积极协助辅导员完成各项任务",
    ],
    "youth_league_application": [
        "我志愿加入中国共产主义青年团",
        "中国共产主义青年团是中国共产党领导的先进青年的群团组织",
        "我将以团员的标准严格要求自己，努力学习",
        "请团组织在实践中考验我",
    ],
    "grant_application": [
        "我家住偏远农村，家庭经济条件十分困难",
        "父亲因病丧失劳动能力，母亲靠打零工维持家用",
        "为了减轻家庭负担，特申请国家助学金",
        "在校期间，我积极参加勤工助学岗位，努力减轻家庭负担",
    ],
    "western_plan": [
        "我志愿报名参加大学生志愿服务西部计划",
        "到祖国最需要的地方去，是我的青春誓言",
        "我愿意在西部这片热土上挥洒青春汗水",
        "我希望通过西部计划，为西部发展贡献自己的力量",
    ],
    "volunteer_teaching": [
        "我志愿报名参加研究生支教团",
        "用一年时间，做一件终生难忘的事",
        "我希望通过支教，将所学知识传递给西部的孩子",
        "我愿意在支教岗位上践行志愿精神",
    ],
    "tech_service": [
        "本项目旨在为 XX 企业/农村/社区提供技术服务",
        "通过本项目的实施，解决了 XX 技术难题",
        "项目成果得到了服务对象的充分肯定",
        "本项目取得了显著的经济效益和社会效益",
    ],
    "selected_graduate": [
        "我志愿报名参加选调生计划",
        "到基层去，到祖国最需要的地方去",
        "我希望通过选调生计划，在基层锻炼成长",
        "我愿意扎根基层，为地方发展贡献力量",
    ],
    "policy_lecture": [
        "本次政策宣讲活动围绕 XX 主题展开",
        "宣讲覆盖受众 XX 人，取得了良好效果",
        "通过宣讲，使广大干部群众对 XX 政策有了更深入的了解",
        "本次活动得到了当地政府的大力支持",
    ],
    "class_collective": [
        "我班共有学生 XX 人，班委成员 XX 人",
        "本学年，我班在思想、学习、活动等方面均取得了优异成绩",
        "我班整体 GPA 位于年级前列，过级率达 XX%",
        "本学年我班组织开展了多项主题班会与团日活动",
    ],
    "major_transfer": [
        "本人现就读于 XX 专业，希望能够转入 XX 专业",
        "经过一年的学习，我发现自己对 XX 专业更感兴趣",
        "我希望通过转专业，能够更好地发挥自己的特长",
        "我已经选修了 XX 专业的相关课程，并取得了较好成绩",
    ],
}

# ---------------------------------------------------------------------------
# 党政原文金句库（与申报书常见引用对照，长度 ≥ 30 字视为高危雷同）
# ---------------------------------------------------------------------------
PARTY_ORIGINAL_TEXTS: List[str] = [
    "中国共产党是中国工人阶级的先锋队，同时是中国人民和中华民族的先锋队，是中国特色社会主义事业的领导核心",
    "中国共产党以马克思列宁主义、毛泽东思想、邓小平理论、'三个代表'重要思想、科学发展观、习近平新时代中国特色社会主义思想作为自己的行动指南",
    "全心全意为人民服务是中国共产党的根本宗旨",
    "我国正处于并将长期处于社会主义初级阶段",
    "坚持社会主义道路、坚持人民民主专政、坚持中国共产党的领导、坚持马克思列宁主义毛泽东思想这四项基本原则",
    "两个确立：确立习近平同志党中央的核心、全党的核心地位，确立习近平新时代中国特色社会主义思想的指导地位",
    "两个维护：坚决维护习近平总书记党中央的核心、全党的核心地位，坚决维护党中央权威和集中统一领导",
    "四个意识：政治意识、大局意识、核心意识、看齐意识",
    "四个自信：道路自信、理论自信、制度自信、文化自信",
    "党的二十大主题：高举中国特色社会主义伟大旗帜，全面贯彻新时代中国特色社会主义思想",
]


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------
@dataclass
class PlagiarismHit:
    """单条疑似抄袭命中。"""
    source_type: str  # "template" / "party_original"
    skill_name: str
    matched_text: str
    similarity: float
    longest_common: str
    suggestion: str


@dataclass
class PlagiarismReport:
    """查重报告。"""
    skill_name: str
    text_length: int
    overall_similarity: float  # 0-1
    max_similarity: float
    hit_count: int
    hits: List[PlagiarismHit] = field(default_factory=list)
    suspected_segments: List[Dict] = field(default_factory=list)
    grade: str = ""  # A/B/C/D
    suggestions: List[str] = field(default_factory=list)
    passed: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


# ---------------------------------------------------------------------------
# 核心算法
# ---------------------------------------------------------------------------
def ngram_similarity(text1: str, text2: str, n: int = 3) -> float:
    """
    计算两段文本的 N-gram Jaccard 相似度。

    :param text1: 文本 1
    :param text2: 文本 2
    :param n: N-gram 长度，默认 3
    :return: 0-1 之间的浮点数，1 表示完全相同
    """
    s1 = _normalize(text1)
    s2 = _normalize(text2)
    if len(s1) < n or len(s2) < n:
        return 1.0 if s1 == s2 else 0.0
    set1: Set[str] = {s1[i:i + n] for i in range(len(s1) - n + 1)}
    set2: Set[str] = {s2[i:i + n] for i in range(len(s2) - n + 1)}
    if not set1 or not set2:
        return 0.0
    inter = len(set1 & set2)
    union = len(set1 | set2)
    return inter / union if union else 0.0


def find_longest_common_substring(text1: str, text2: str) -> Tuple[str, int]:
    """
    动态规划求两段文本的最长公共子串。

    :return: (公共子串, 长度)
    """
    s1 = _normalize(text1)
    s2 = _normalize(text2)
    if not s1 or not s2:
        return "", 0
    m, n = len(s1), len(s2)
    # DP 表压缩为一行
    dp = [0] * (n + 1)
    longest = 0
    end_idx = 0
    for i in range(1, m + 1):
        prev = 0
        for j in range(1, n + 1):
            tmp = dp[j]
            if s1[i - 1] == s2[j - 1]:
                dp[j] = prev + 1
                if dp[j] > longest:
                    longest = dp[j]
                    end_idx = i
            else:
                dp[j] = 0
            prev = tmp
    return s1[end_idx - longest:end_idx], longest


def _sentence_level_similarity(
    text: str, candidate: str, n: int = 3
) -> Tuple[float, str, int]:
    """对文本按句切分，逐句比对，返回最大相似度 + 最长公共子串。"""
    sentences = _split_sentences(text)
    max_sim = 0.0
    best_lcs = ""
    best_lcs_len = 0
    for sent in sentences:
        sim = ngram_similarity(sent, candidate, n=n)
        if sim > max_sim:
            max_sim = sim
        lcs, lcs_len = find_longest_common_substring(sent, candidate)
        if lcs_len > best_lcs_len:
            best_lcs = lcs
            best_lcs_len = lcs_len
    return max_sim, best_lcs, best_lcs_len


def _build_suggestion(hit: PlagiarismHit) -> str:
    """根据命中类型生成修改建议。"""
    if hit.source_type == "party_original":
        return (
            f"与党政原文连续雷同 ≥ {len(hit.longest_common)} 字，"
            "请改写为个人理解式表述，避免直接引用原文。"
        )
    if hit.similarity >= 0.7:
        return (
            "高度雷同网络模板，建议完全重写该段，"
            "加入具体人/事/数字等个人真实信息。"
        )
    if hit.similarity >= 0.4:
        return (
            "中度雷同网络模板，建议调整句式结构、替换关键词、"
            "补充个人具体经历。"
        )
    return "轻度雷同，建议替换部分表述以提升原创性。"


def highlight_plagiarism(text: str, threshold: float = 0.3) -> str:
    """
    高亮疑似抄袭段（返回带 <<...>> 标记的文本）。

    :param text: 原文
    :param threshold: 相似度阈值（0-1），超过则高亮
    :return: 标注后的文本
    """
    if not text:
        return ""
    sentences = _split_sentences(text)
    out_parts: List[str] = []
    # 收集所有候选模板
    candidates: List[Tuple[str, str]] = []
    for skill, templates in TEMPLATE_LIBRARY.items():
        for tpl in templates:
            candidates.append((tpl, skill))
    for tpl in PARTY_ORIGINAL_TEXTS:
        candidates.append((tpl, "_party_original"))

    for sent in sentences:
        max_sim = 0.0
        for tpl_text, _ in candidates:
            sim = ngram_similarity(sent, tpl_text, n=3)
            if sim > max_sim:
                max_sim = sim
        if max_sim >= threshold:
            out_parts.append(f"<<{sent}>>")
        else:
            out_parts.append(sent)
    return "".join(out_parts)


# ---------------------------------------------------------------------------
# 主查重函数
# ---------------------------------------------------------------------------
def check_plagiarism(
    text: str,
    skill_name: str,
    threshold: float = 0.3,
    party_check: bool = True,
) -> PlagiarismReport:
    """
    主查重函数：检测文本与网络模板/党政原文的相似度。

    :param text: 待检测文本
    :param skill_name: 子 skill 名称（如 national_project_eval）
    :param threshold: 相似度阈值（默认 0.3）
    :param party_check: 是否检查党政原文（默认 True）
    :return: PlagiarismReport
    """
    report = PlagiarismReport(
        skill_name=skill_name,
        text_length=len(text or ""),
        overall_similarity=0.0,
        max_similarity=0.0,
        hit_count=0,
    )

    if not text or not text.strip():
        report.suggestions.append("文本为空，无法查重。")
        return report

    # 加载该 skill 的模板
    candidates: List[Tuple[str, str, str]] = []  # (text, source_type, skill)
    skill_templates = TEMPLATE_LIBRARY.get(skill_name, [])
    for tpl in skill_templates:
        candidates.append((tpl, "template", skill_name))
    # 党政原文金句库
    if party_check:
        for orig in PARTY_ORIGINAL_TEXTS:
            candidates.append((orig, "party_original", "_party"))

    # 逐句比对
    sentences = _split_sentences(text)
    if not sentences:
        # 文本过短，整段比对
        sentences = [text.strip()]

    hits: List[PlagiarismHit] = []
    suspected: List[Dict] = []
    sum_sim = 0.0
    max_sim = 0.0

    for sent in sentences:
        sent_max_sim = 0.0
        sent_best_hit: Optional[PlagiarismHit] = None
        for tpl_text, src_type, src_skill in candidates:
            sim, lcs, lcs_len = _sentence_level_similarity(sent, tpl_text, n=3)
            if sim >= threshold and sim > sent_max_sim:
                sent_max_sim = sim
                sent_best_hit = PlagiarismHit(
                    source_type=src_type,
                    skill_name=src_skill,
                    matched_text=sent,
                    similarity=round(sim, 4),
                    longest_common=lcs,
                    suggestion="",
                )
            if sim > max_sim:
                max_sim = sim
        if sent_best_hit is not None:
            sent_best_hit.suggestion = _build_suggestion(sent_best_hit)
            hits.append(sent_best_hit)
            suspected.append({
                "segment": sent_best_hit.matched_text,
                "similarity": sent_best_hit.similarity,
                "source_type": sent_best_hit.source_type,
                "longest_common": sent_best_hit.longest_common,
                "suggestion": sent_best_hit.suggestion,
            })
            sum_sim += sent_best_hit.similarity

    # 综合相似度 = 命中句相似度之和 / 总句数
    overall = sum_sim / max(len(sentences), 1)
    report.overall_similarity = round(overall, 4)
    report.max_similarity = round(max_sim, 4)
    report.hits = hits
    report.hit_count = len(hits)
    report.suspected_segments = suspected

    # 等级判定
    if overall >= 0.5 or max_sim >= 0.8:
        report.grade = "D"
        report.passed = False
    elif overall >= 0.3 or max_sim >= 0.6:
        report.grade = "C"
        report.passed = False
    elif overall >= 0.15 or max_sim >= 0.4:
        report.grade = "B"
        report.passed = True
    else:
        report.grade = "A"
        report.passed = True

    # 党政原文连续 50 字直接 D
    for h in hits:
        if h.source_type == "party_original" and len(h.longest_common) >= 50:
            report.grade = "D"
            report.passed = False
            break

    # 综合建议
    report.suggestions = _build_overall_suggestions(report)
    return report


def _build_overall_suggestions(report: PlagiarismReport) -> List[str]:
    """根据报告生成总体修改建议。"""
    sug: List[str] = []
    if report.hit_count == 0:
        sug.append("未发现明显抄袭，文本原创性良好。")
        return sug
    if report.grade == "D":
        sug.append(
            f"【严重】整体相似度 {report.overall_similarity*100:.1f}%，"
            "超过 30% 一票否决线，必须重写后再提交。"
        )
    elif report.grade == "C":
        sug.append(
            f"【警告】整体相似度 {report.overall_similarity*100:.1f}%，"
            "接近一票否决线，建议大幅改写命中段落。"
        )
    elif report.grade == "B":
        sug.append(
            f"【提示】整体相似度 {report.overall_similarity*100:.1f}%，"
            "存在轻度雷同，建议优化命中段落表述。"
        )
    # 党政原文专项
    party_hits = [h for h in report.hits if h.source_type == "party_original"]
    if party_hits:
        longest_party = max((len(h.longest_common) for h in party_hits), default=0)
        if longest_party >= 50:
            sug.append(
                f"【党政原文】与党章/二十大原文连续雷同 {longest_party} 字，"
                "党支部查重会直接判定为抄袭，必须改写。"
            )
        else:
            sug.append(
                f"【党政原文】与党政原文连续雷同 {longest_party} 字，"
                "建议改写为个人理解式表述。"
            )
    # 命中段落定位
    if report.suspected_segments:
        sug.append(f"共发现 {report.hit_count} 处疑似雷同段落，详见 suspected_segments 字段。")
    # 改写策略
    sug.append("改写策略：1) 替换关键词；2) 调整句式结构；3) 加入个人真实经历/具体数字；4) 引用改为转述。")
    return sug


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="大学生申报书查重预检（vs 网络模板 + 党政原文）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例：
  python plagiarism_checker.py --text "我志愿加入中国共产党..." --skill youth_league_application
  python plagiarism_checker.py --file input.txt --skill national_project_eval
  python plagiarism_checker.py --file input.txt --skill youth_league_application --highlight
  python plagiarism_checker.py --list-skills
""",
    )
    p.add_argument("--text", help="待检测文本（与 --file 二选一）")
    p.add_argument("--file", help="待检测文本文件路径")
    p.add_argument(
        "--skill",
        default="national_project_eval",
        help="子 skill 名称（如 national_project_eval / youth_league_application）",
    )
    p.add_argument("--threshold", type=float, default=0.3, help="相似度阈值（默认 0.3）")
    p.add_argument("--no-party", action="store_true", help="跳过党政原文比对")
    p.add_argument("--highlight", action="store_true", help="输出高亮标注文本")
    p.add_argument("--json", action="store_true", help="以 JSON 格式输出完整报告")
    p.add_argument("--list-skills", action="store_true", help="列出所有支持的 skill")
    p.add_argument("--out", help="输出到文件")
    return p


def _list_skills() -> None:
    print("支持的子 skill（共 %d 个）：" % len(TEMPLATE_LIBRARY))
    for k in sorted(TEMPLATE_LIBRARY.keys()):
        print(f"  - {k}  ({len(TEMPLATE_LIBRARY[k])} 条模板)")
    print(f"\n党政原文金句库：{len(PARTY_ORIGINAL_TEXTS)} 条")


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_skills:
        _list_skills()
        return 0

    # 读取文本
    if args.file:
        if not os.path.exists(args.file):
            print(f"❌ 文件不存在: {args.file}", file=sys.stderr)
            return 2
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        parser.print_help()
        return 2

    # 高亮模式
    if args.highlight:
        highlighted = highlight_plagiarism(text, threshold=args.threshold)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(highlighted)
            print(f"✅ 高亮文本已写入: {args.out}")
        else:
            print(highlighted)
        return 0

    # 查重
    report = check_plagiarism(
        text=text,
        skill_name=args.skill,
        threshold=args.threshold,
        party_check=not args.no_party,
    )

    if args.json:
        output = report.to_json()
    else:
        output = _format_text_report(report)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ 查重报告已写入: {args.out}")
    else:
        print(output)
    return 0 if report.passed else 1


def _format_text_report(report: PlagiarismReport) -> str:
    """格式化文本报告。"""
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("📋 大学生申报书查重预检报告")
    lines.append("=" * 60)
    lines.append(f"子 skill       : {report.skill_name}")
    lines.append(f"文本长度       : {report.text_length} 字")
    lines.append(f"整体相似度     : {report.overall_similarity*100:.2f}%")
    lines.append(f"最高单段相似度 : {report.max_similarity*100:.2f}%")
    lines.append(f"命中段落数     : {report.hit_count}")
    grade_label = {"A": "优（原创）", "B": "良（轻度雷同）", "C": "中（中度雷同）", "D": "差（严重雷同）"}
    lines.append(f"查重等级       : {report.grade} - {grade_label.get(report.grade, '')}")
    lines.append(f"是否通过       : {'✅ 通过' if report.passed else '❌ 不通过（需重写）'}")
    lines.append("")
    if report.suspected_segments:
        lines.append("-" * 60)
        lines.append("🔍 疑似雷同段落定位：")
        lines.append("-" * 60)
        for i, seg in enumerate(report.suspected_segments, 1):
            lines.append(f"\n【段落 {i}】")
            lines.append(f"  原文片段 : {seg['segment'][:80]}...")
            lines.append(f"  相似度   : {seg['similarity']*100:.2f}%")
            lines.append(f"  来源类型 : {seg['source_type']}")
            lines.append(f"  最长公共 : {seg['longest_common'][:50]}")
            lines.append(f"  修改建议 : {seg['suggestion']}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("💡 总体修改建议：")
    lines.append("-" * 60)
    for s in report.suggestions:
        lines.append(f"  • {s}")
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
