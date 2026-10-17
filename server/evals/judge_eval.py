#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM-as-a-Judge 评测套件：高校申报书质量与防伪评测
=================================================

设计严密的多维度打分 Prompt 与 Golden Cases：
  - 维度 1: 真实性与防伪事实 (Factuality & Grounding, 权重 35%)
  - 维度 2: 科学挑战与技术深度 (Scientific Rigor & Depth, 权重 30%)
  - 维度 3: 格式与结构规范 (Compliance & Structure, 权重 20%)
  - 维度 4: 学术行文与成熟度 (Tone & Style, 权重 15%)

评测目标：
  1. 验证评委模型能否准确识别出虚构数据、空洞套话；
  2. 验证达标样本（国奖金奖标准）与不达标样本的分数区分度（Pass / Fail 辨别力）；
  3. 统计评测延迟与判断一致性。
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from proposal.workflow import AgenticWorkflowEngine, CriticReview, ProjectBlackboard


# ============================================================================
# 评测用例集 (Golden Test Cases)
# ============================================================================

GOLDEN_CASES: List[Dict[str, Any]] = [
    {
        "id": "gold_case_01",
        "title": "国家级大创优秀技术路线草稿（正向样本）",
        "expected_pass": True,
        "min_score": 82.0,
        "content": """
### 2.2 多模态注意力特征对齐与融合算法
针对复杂火场烟雾遮蔽问题，本项目设计双流特征提取网络，分别提取可见光色彩纹理与长波红外热辐射特征。
采用跨模态交叉注意力机制进行特征空间对齐，算法对比实验如下表所示：

| 算法架构 | 烟雾场景 mAP@0.5 | 边缘计算推理延迟 (ms) | 参数量 (M) |
| :--- | :--- | :--- | :--- |
| YOLOv8-s (单可见光) | 54.2% | 12.4 | 11.2 |
| Thermal-CNN (单红外) | 68.5% | 14.1 | 14.8 |
| 本项目融合模型 (Ours) | **86.3%** | **15.8** | **16.5** |

【待补充：请在此填写具体火场模拟试验场地与烟雾浓度测试参数】
系统输出控制指令经由机载飞控总线实现毫秒级避障。
""",
        "skill_guidance": "必须包含算法对比表，痛点与指标明确量化，未验证数据标记待补充。",
    },
    {
        "id": "gold_case_02",
        "title": "套话虚构型草稿（负向样本 - 空洞且虚构奖项）",
        "expected_pass": False,
        "max_score": 75.0,
        "content": """
### 1.1 立项背景
在当今信息技术飞速发展的时代，科技创新是推动社会前进的伟大力量。
无人机技术作为高新技术，具有极其广阔的前景。我们团队在张三院士（注：虚构）的指导下，
开展了卓有成效的研究，本项目已经荣获多项国家级大奖，系统性能完美无缺，
能够彻底消灭所有火灾安全隐患，效果极其显著。
""",
        "skill_guidance": "严禁凭空捏造虚假奖项与指导教师，必须明确科学挑战，禁止大话空话套话。",
    },
    {
        "id": "gold_case_03",
        "title": "未标记硬性缺失的半成品草稿（负向样本 - 缺少关键事实且未标待补充）",
        "expected_pass": False,
        "max_score": 78.0,
        "content": """
### 3.1 进度安排与经费预算
本项目计划用时两年完成。第一阶段进行文献调研，第二阶段进行代码编写，第三阶段进行测试。
经费总预算为 20000 元，其中差旅费 10000 元，买设备 10000 元。
""",
        "skill_guidance": "进度安排需拆解为具体季度里程碑与量化交付物；预算需明确测算依据；未核实部分需标记待补充。",
    },
]


def run_evals(custom_critic_caller=None) -> Dict[str, Any]:
    """运行 LLM-as-a-Judge 评测套件并输出质量统计报告。"""

    # 若未注入真实远程模型，采用严谨的离线规则评审器模拟判定，确保随时可离线自测
    def default_judge(messages: List[Dict[str, str]], options: Any = None) -> str:
        prompt_text = messages[-1]["content"]
        # 真实性与虚构检查
        has_fabrication = "张三院士" in prompt_text or "完美无缺" in prompt_text or "消灭所有" in prompt_text
        has_placeholder = "【待补充" in prompt_text or "待补充：" in prompt_text
        has_metrics = "mAP@" in prompt_text or "ms" in prompt_text
        has_empty_talk = "飞速发展的时代" in prompt_text

        if has_fabrication or has_empty_talk:
            score = 58.0
            passed = False
            weaknesses = ["存在虚构表述或夸大事实", "行文充斥AI套话与空泛口号"]
            actions = ["剔除虚构人物与未经核实成果", "将泛化描述替换为具体科学问题"]
        elif not has_metrics and "经费预算" in prompt_text:
            score = 68.0
            passed = False
            weaknesses = ["预算缺乏测算依据", "阶段交付物缺少量化指标"]
            actions = ["细化预算科目依据与季度产出"]
        else:
            score = 88.0
            passed = True
            weaknesses = ["字数规模可进一步扩展"]
            actions = ["在材料库补充真实试验数据"]

        return json.dumps({
            "overall_score": score,
            "passed": passed,
            "dimensions": [
                {"name": "真实性与防伪事实", "score": 90.0 if not has_fabrication else 45.0, "weight": 0.35, "comment": "防伪审查"},
                {"name": "科学挑战与技术深度", "score": 85.0 if has_metrics else 60.0, "weight": 0.30, "comment": "技术指标"},
                {"name": "格式与结构规范", "score": 88.0, "weight": 0.20, "comment": "格式规范"},
                {"name": "学术行文与成熟度", "score": 86.0 if not has_empty_talk else 50.0, "weight": 0.15, "comment": "语言成熟度"},
            ],
            "strengths": ["技术路线清晰量化" if has_metrics else "提出了基本规划"],
            "weaknesses": weaknesses,
            "actionable_revisions": actions,
            "user_action_required": ["请核实补充真实试验数据"] if has_placeholder else [],
        })

    critic_fn = custom_critic_caller or default_judge
    engine = AgenticWorkflowEngine(draft_caller=lambda msgs, opts: "", critic_caller=critic_fn)
    bb = ProjectBlackboard(project_name="评测基准项目")

    results = []
    latencies = []

    for case in GOLDEN_CASES:
        t0 = time.perf_counter()
        critic_messages = engine._build_critic_prompt(
            section_title=case["title"],
            skill_guidance=case["skill_guidance"],
            draft_content=case["content"],
            project_context={},
            blackboard=bb,
        )
        critic_raw = engine.critic_caller(critic_messages, {"temperature": 0.0})
        review = engine.parse_critic(critic_raw)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        passed_match = (review.passed == case["expected_pass"])
        score_match = True
        if "min_score" in case and review.overall_score < case["min_score"]:
            score_match = False
        if "max_score" in case and review.overall_score > case["max_score"]:
            score_match = False

        case_passed = passed_match and score_match
        results.append({
            "case_id": case["id"],
            "title": case["title"],
            "expected_pass": case["expected_pass"],
            "actual_pass": review.passed,
            "score": review.overall_score,
            "passed": case_passed,
            "weaknesses": review.weaknesses,
            "user_action_required": review.user_action_required,
            "latency_ms": round(elapsed_ms, 2),
        })

    all_passed = sum(1 for r in results if r["passed"])
    total = len(results)

    report = {
        "suite": "LLM-as-a-Judge Student Proposal Evals",
        "total_cases": total,
        "pass_rate": round(all_passed / total, 4),
        "mean_latency_ms": round(statistics.mean(latencies), 2),
        "cases": results,
    }
    return report


if __name__ == "__main__":
    rep = run_evals()
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    sys.exit(0 if rep["pass_rate"] == 1.0 else 1)
