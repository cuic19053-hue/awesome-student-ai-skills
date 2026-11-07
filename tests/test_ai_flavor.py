# -*- coding: utf-8 -*-
"""utils/ai_flavor_check.py 的单元测试。

覆盖：
1. 空文本 / 极短文本不崩
2. 套话样本必须低分（回归用户反馈的「AI 味太浓」）
3. 具体文本必须高分（防误报）
4. 各维度可单独触发
5. CLI 退出码语义（--min-score 门禁）
6. 报告可 JSON 序列化
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.ai_flavor_check import (  # noqa: E402
    ALL_EMPTY_PHRASES,
    ABSTRACT_NOUNS,
    FlavorReport,
    check_ai_flavor,
    format_report,
)

MODULE = ROOT / "utils" / "ai_flavor_check.py"

# --- 样本 ---

BOILERPLATE_SAMPLE = (
    "本人自入学以来，始终高度重视自身综合素质的提升，在学习上勤奋刻苦、锐意进取，"
    "在思想上积极向党组织靠拢，在工作上认真负责、勇于担当。\n"
    "在学业方面，我刻苦钻研专业知识，取得了优异成绩，综合排名位于专业前茅，"
    "获得了老师和同学的一致好评。\n"
    "在科研方面，我积极参与各类学科竞赛和科研项目，在导师的悉心指导下取得了显著成效，"
    "为团队贡献了自己的力量。\n"
    "在社会实践方面，我积极参加志愿服务活动，展现了新时代大学生的良好风貌，"
    "得到了充分肯定。\n"
    "在今后的学习和生活中，我将继续不懈努力，不断提升自我，为集体作出积极贡献，"
    "特此申请国家奖学金。"
)

CONCRETE_SAMPLE = (
    "大二上学期，我在《数据结构》课上第一次接触并查集，因为写错了一处路径压缩，"
    "OJ 上 12 个测试点只过了 5 个。\n"
    "那天晚上我在机房待到 11 点，把 2019 年 CSP-S 的第 3 题重写了三遍，"
    "第二遍才把时间复杂度从 O(n^2) 压到 O(n α(n))。\n"
    "后来我把这段推导整理成 8 页笔记，2024 年 3 月贴在学院学习角的公告栏上，"
    "被 3 个班的同学借去复印。\n"
    "去年 11 月，我带队参加中国大学生计算机设计大赛，作品是「基于 YOLOv8 的校园电动车违规停放识别」，"
    "我负责数据集标注和模型微调。\n"
    "我们标了 4200 张图，其中 900 张是雨天拍摄的，这个比例是我自己定的，因为保安说雨天违停最多。\n"
    "最终在省赛拿到二等奖，答辩时评委问了模型在低照度下的召回率，我们实测是 0.81，比基线高了 0.07。"
)


# --- 基础行为 ---

def test_empty_text_is_not_applicable_without_crash():
    """空文本视为「不适用」，不当作 AI 味（避免误伤纯格式内容）。"""
    report = check_ai_flavor("")
    assert isinstance(report, FlavorReport)
    assert report.text_length == 0
    assert report.hits == []
    assert report.grade == "无散文内容"
    assert report.passed is True


def test_whitespace_only_text_is_treated_as_empty():
    report = check_ai_flavor("   \n\t  \n ")
    assert report.text_length == 0
    assert report.grade == "无散文内容"


def test_short_text_does_not_crash():
    report = check_ai_flavor("我申请国家奖学金。")
    assert 0.0 <= report.score <= 100.0


# --- 核心区分度（回归用户反馈）---

def test_boilerplate_sample_scores_low():
    """用户反馈「AI 味太浓」的那类文本必须被判为低分。"""
    report = check_ai_flavor(BOILERPLATE_SAMPLE)
    assert report.score < 75.0, f"套话样本不应及格，实际 {report.score}"
    assert report.grade in ("明显 AI 味", "重度 AI 味")
    assert len(report.hits) > 0


def test_concrete_sample_scores_high():
    """具体、有细节的文本不能被误判。"""
    report = check_ai_flavor(CONCRETE_SAMPLE)
    assert report.score >= 85.0, f"具体样本不应低分，实际 {report.score}"
    assert report.grade == "自然"


def test_concrete_scores_much_higher_than_boilerplate():
    """区分度必须显著，否则检测器没有实用价值。"""
    gap = check_ai_flavor(CONCRETE_SAMPLE).score - check_ai_flavor(BOILERPLATE_SAMPLE).score
    assert gap >= 30.0, f"区分度不足：{gap}"


# --- 各维度单独触发 ---

def test_empty_phrase_dimension_triggers():
    text = "具有重要意义。具有重大意义。意义重大。影响深远。作用显著。效果显著。成效显著。成绩斐然。成果丰硕。" * 2
    report = check_ai_flavor(text)
    assert report.dimensions["EMPTY_PHRASE"] > 0
    assert any(h.dimension == "EMPTY_PHRASE" for h in report.hits)


def test_boilerplate_opening_triggers():
    report = check_ai_flavor("时光荏苒，转眼间一学年已经过去。" + CONCRETE_SAMPLE)
    assert any(h.dimension == "BOILERPLATE" for h in report.hits)


def test_specificity_dimension_triggers_on_vague_text():
    vague = (
        "我在学习和工作中认真负责，积极参加各项活动，努力提升自身能力。"
        "我热爱集体，关心同学，乐于助人，在各方面都严格要求自己。"
        "我将继续努力，不断进步，争取做得更好，为集体争光添彩。"
    )
    report = check_ai_flavor(vague)
    assert report.dimensions["SPECIFICITY"] > 0
    assert any(h.dimension == "SPECIFICITY" for h in report.hits)


def test_parallelism_dimension_triggers():
    parallel = (
        "在思想上，我积极上进，认真学习理论知识。"
        "在学习上，我勤奋刻苦，努力掌握专业知识。"
        "在工作上，我认真负责，主动承担各项任务。"
        "在生活上，我艰苦朴素，热心帮助身边同学。"
    )
    report = check_ai_flavor(parallel)
    assert report.dimensions["PARALLELISM"] > 0


def test_abstract_noun_dimension_triggers():
    text = "我们要构建长效机制，完善体系，打通路径，打造载体，形成闭环，实现赋能，助力引领驱动融合协同联动统筹。" * 3
    report = check_ai_flavor(text)
    assert report.dimensions["ABSTRACT_NOUN"] > 0


# --- 豁免与参数 ---

def test_allow_policy_quotes_halves_empty_phrase_penalty():
    text = BOILERPLATE_SAMPLE
    strict = check_ai_flavor(text)
    lenient = check_ai_flavor(text, allow_policy_quotes=True)
    assert lenient.score > strict.score
    assert lenient.dimensions["EMPTY_PHRASE"] == pytest.approx(strict.dimensions["EMPTY_PHRASE"] * 0.5)


# --- 报告结构 ---

def test_report_is_json_serializable():
    report = check_ai_flavor(BOILERPLATE_SAMPLE)
    payload = json.dumps(report.to_dict(), ensure_ascii=False)
    restored = json.loads(payload)
    assert restored["grade"] == report.grade
    assert restored["hit_count"] == len(report.hits)
    assert isinstance(restored["hits"], list)


def test_format_report_contains_key_sections():
    out = format_report(check_ai_flavor(BOILERPLATE_SAMPLE))
    assert "AI 味检测报告" in out
    assert "得分" in out
    assert "维度扣分" in out


def test_passed_property_matches_threshold():
    assert check_ai_flavor(CONCRETE_SAMPLE).passed is True
    assert check_ai_flavor(BOILERPLATE_SAMPLE).passed is False


# --- 词表健全性 ---

def test_phrase_tables_are_non_empty_and_unique():
    assert len(ALL_EMPTY_PHRASES) > 50
    assert len(ALL_EMPTY_PHRASES) == len(set(ALL_EMPTY_PHRASES)), "套话表存在重复项"
    assert len(ABSTRACT_NOUNS) == len(set(ABSTRACT_NOUNS)), "抽象名词表存在重复项"
    for phrase in ALL_EMPTY_PHRASES:
        assert phrase.strip(), "套话表含空串"


# --- CLI ---

def _run_cli(args, text=None):
    cmd = [sys.executable, str(MODULE)] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, input=text)


def test_cli_text_mode_runs():
    proc = _run_cli(["--text", "我在学习上勤奋刻苦，锐意进取。"])
    assert proc.returncode == 0, proc.stderr
    assert "AI 味检测报告" in proc.stdout


def test_cli_json_mode_is_valid_json():
    proc = _run_cli(["--text", BOILERPLATE_SAMPLE, "--json"])
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert "score" in payload
    assert "hits" in payload


def test_cli_min_score_gate_fails_on_boilerplate():
    proc = _run_cli(["--text", BOILERPLATE_SAMPLE, "--min-score", "75"])
    assert proc.returncode == 1


def test_cli_min_score_gate_passes_on_concrete():
    proc = _run_cli(["--text", CONCRETE_SAMPLE, "--min-score", "75"])
    assert proc.returncode == 0


def test_cli_requires_input():
    proc = _run_cli([])
    assert proc.returncode != 0


# ===========================================================================
# 误报防护（2026-11-08 修复）：格式内容不应被判为 AI 味
# ===========================================================================

def test_markdown_table_not_flagged_as_parallelism():
    """表格行的结构相同是格式要求，不是排比对仗。"""
    table = (
        "| 环节 | 时长 | 内容 |\n"
        "|------|------|------|\n"
        "| 开场 | 5 分钟 | 自我介绍 |\n"
        "| 主体 | 15 分钟 | 五大维度 |\n"
        "| 案例 | 10 分钟 | 本村案例 |\n"
        "| 互动 | 10 分钟 | 有奖问答 |\n"
        "| 结尾 | 5 分钟 | 总结号召 |\n"
    )
    report = check_ai_flavor(table)
    assert report.dimensions["PARALLELISM"] == 0, "表格被误判为排比"


def test_markdown_list_not_flagged_as_parallelism():
    """列表项结构相同是格式要求。"""
    items = (
        "- 宣讲场次：12 场\n"
        "- 覆盖人次：860 人次\n"
        "- 材料印制：手册 200 份\n"
        "- 媒体报道：5 篇\n"
        "- 问卷回收：420 份\n"
        "- 满意度：92%\n"
    )
    report = check_ai_flavor(items)
    assert report.dimensions["PARALLELISM"] == 0, "列表被误判为排比"


def test_ascii_diagram_not_flagged():
    """ASCII 框图不参与文风评分。"""
    diagram = (
        "```\n"
        "┌─────────────┐\n"
        "│ 阶段 1：准备 │\n"
        "├─────────────┤\n"
        "│ 文献综述     │\n"
        "│ 方案设计     │\n"
        "└──────┬──────┘\n"
        "       ↓\n"
        "┌─────────────┐\n"
        "│ 阶段 2：试点 │\n"
        "└─────────────┘\n"
        "```\n"
    )
    report = check_ai_flavor(diagram)
    assert report.score >= 75.0, f"框图被误判，得分 {report.score}"


def test_semicolon_enumeration_not_flagged():
    """分号列举属正常书面语，切开后不应判为排比。"""
    text = (
        "本课题技术路线分 4 阶段：准备阶段（2025.04）完成文献综述与方案设计；"
        "试点阶段（2025.05-07）在本院 3 年级 6 班 200 人中开展 4 周干预；"
        "分析阶段（2025.08-09）进行 SPSS 统计分析与 Amos 中介效应分析；"
        "跟踪阶段（2025.09）开展 2 个月跟踪测与深度访谈。"
    )
    report = check_ai_flavor(text)
    assert report.dimensions["PARALLELISM"] == 0, "分号列举被误判为排比"
    assert report.score >= 75.0


def test_bold_label_spec_lines_not_flagged():
    """「**短版**：…」这类档位参数说明不算正文排比。"""
    text = (
        "**短版（约 360 字）**：4 维度各精简至 80~95 字，列 QS 排名 + 1 门课程 + 1 位导师。\n"
        "**标准版（约 500 字）**：4 维度各 110~130 字，列 QS 排名 + 2 门课程 + 2 位导师。\n"
        "**长版（约 625 字）**：4 维度详尽展开，含 QS 排名 + 2 门课程 + 1 个实验室。\n"
    )
    report = check_ai_flavor(text)
    assert report.dimensions["PARALLELISM"] == 0, "档位说明被误判为排比"


def test_prose_inside_code_fence_still_scored():
    """包在 ``` 里的范文正文仍应参与评分（不能被整体丢弃）。"""
    text = (
        "```\n"
        "（一）国内研究现状\n\n"
        "课堂手机使用行为研究方面，张华等（2022）对 5 所高校 1200 名大学生调查发现"
        "课堂手机使用率达 75.8% [1]，但仅描述现象未提出干预方案。李明等（2023）"
        "扩展样本至 8 所高校 2000 人，使用率达 78.3% [2]，仍停留在现象描述层面。\n"
        "```\n"
    )
    report = check_ai_flavor(text)
    assert report.text_length > 50, "代码块内散文被整体丢弃"


# --- 真阳性不能因放宽误报而丢失 ---

def test_pure_parallelism_still_caught():
    text = (
        "在思想上，我积极上进，认真学习理论知识。"
        "在学习上，我勤奋刻苦，努力掌握专业知识。"
        "在工作上，我认真负责，主动承担各项任务。"
        "在生活上，我艰苦朴素，热心帮助身边同学。"
        "在实践上，我勇于探索，积极参加社会活动。"
    )
    report = check_ai_flavor(text)
    assert report.score < 75.0, "纯排比未被抓到"


def test_hollow_text_without_any_evidence_caught():
    """通篇零具体锚点的空洞文本必须不及格。"""
    text = (
        "我热爱集体，关心同学，乐于助人，在各方面都严格要求自己。"
        "我将继续努力，不断进步，争取做得更好，为集体争光添彩。"
        "我深知任重道远，定当不负期望，砥砺前行。"
    )
    report = check_ai_flavor(text)
    assert report.score < 75.0, f"空洞文本未抓到，得分 {report.score}"
    assert report.dimensions["SPECIFICITY"] > 0


def test_all_repo_sample_passages_pass():
    """仓库现有范文段落不应出现误报（回归 2026-11-08 的误报修复）。"""
    import re as _re

    subskills = ROOT / "subskills"
    failures = []
    for md in sorted(subskills.glob("*/SKILL.md")):
        lines = md.read_text(encoding="utf-8").splitlines()
        in_sec, buf = False, []
        for line in lines:
            if _re.match(r"^#{2,4}\s.*(完整示例|完整范文|完整范例|范文|示例)", line):
                in_sec, buf = True, []
                continue
            if in_sec and _re.match(r"^#{2,4}\s", line):
                para = "\n".join(buf).strip()
                if len(_re.findall(r"[\u4e00-\u9fff]", para)) >= 150:
                    score = check_ai_flavor(para).score
                    if score < 75:
                        failures.append(f"{md.parent.name}: {score:.1f}")
                in_sec, buf = False, []
            elif in_sec:
                buf.append(line)
        para = "\n".join(buf).strip()
        if in_sec and len(_re.findall(r"[\u4e00-\u9fff]", para)) >= 150:
            score = check_ai_flavor(para).score
            if score < 75:
                failures.append(f"{md.parent.name}: {score:.1f}")
    assert not failures, "范文误报：" + "；".join(failures)
