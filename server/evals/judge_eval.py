#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM-as-a-Judge 自动化评测套件
============================

评测目标：
  使用独立的裁判大模型（如 DeepSeek-R1 / GPT-4o / Claude 3.5）对学生申报书草稿进行
  盲审打分与事实防伪评测，检验真实模型在 4 维度 Rubrics 下的区分度与一致性。

运行模式：
  1. 真实大模型模式（需配置 EVAL_API_KEY / EVAL_MODEL 或 OPENAI_API_KEY）：
     调用真实模型对正向样本与对抗样本打分，输出区分度指标与延迟统计。
  2. 离线校验模式（未提供外部密钥时）：
     明确提示未配置真实模型密钥，不将规则模拟冒充真实评测结论。
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from proposal.workflow import AgenticWorkflowEngine, CriticResponse, ProjectBlackboard


GOLDEN_CASES: List[Dict[str, Any]] = [
    {
        "id": "gold_case_01",
        "title": "国家级大创优秀技术路线草稿（正向样本）",
        "expected_pass": True,
        "min_score": 80.0,
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
        "max_score": 70.0,
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
        "max_score": 75.0,
        "content": """
### 3.1 进度安排与经费预算
本项目计划用时两年完成。第一阶段进行文献调研，第二阶段进行代码编写，第三阶段进行测试。
经费总预算为 20000 元，其中差旅费 10000 元，买设备 10000 元。
""",
        "skill_guidance": "进度安排需拆解为具体季度里程碑与量化交付物；预算需明确测算依据；未核实部分需标记待补充。",
    },
]


def run_evals(custom_critic_caller=None) -> Dict[str, Any]:
    api_key = os.environ.get("EVAL_API_KEY", os.environ.get("OPENAI_API_KEY", "")).strip()
    api_base = os.environ.get("EVAL_API_BASE", os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")).rstrip("/")
    eval_model = os.environ.get("EVAL_MODEL", "gpt-4o-mini").strip()

    if custom_critic_caller is None and not api_key:
        return {
            "suite": "LLM-as-a-Judge Student Proposal Evals",
            "status": "skipped",
            "message": "未配置 EVAL_API_KEY 或 OPENAI_API_KEY。为避免误将规则模拟作为模型评测，已跳过线上真实评测。离线结构测试请运行 pytest tests/test_review_safety.py",
            "total_cases": len(GOLDEN_CASES),
            "pass_rate": None,
        }

    def remote_llm_judge(messages: List[Dict[str, str]], options: Any = None) -> str:
        req = urllib.request.Request(
            f"{api_base}/chat/completions",
            data=json.dumps({
                "model": eval_model,
                "temperature": 0.0,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "critic_response",
                        "strict": True,
                        "schema": CriticResponse.model_json_schema(),
                    },
                },
                "messages": messages,
            }, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    critic_fn = custom_critic_caller or remote_llm_judge
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

        score_match = True
        if review.overall_score is None:
            score_match = False
        else:
            if "min_score" in case and review.overall_score < case["min_score"]:
                score_match = False
            if "max_score" in case and review.overall_score > case["max_score"]:
                score_match = False

        passed_match = (review.overall_score is not None and (review.overall_score >= 80.0) == case["expected_pass"])
        case_passed = passed_match and score_match

        results.append({
            "case_id": case["id"],
            "title": case["title"],
            "expected_pass": case["expected_pass"],
            "score": review.overall_score,
            "passed": case_passed,
            "review_status": review.review_status,
            "weaknesses": review.weaknesses,
            "blocking_issues": review.blocking_issues,
            "latency_ms": round(elapsed_ms, 2),
        })

    all_passed = sum(1 for r in results if r["passed"])
    total = len(results)

    return {
        "suite": "LLM-as-a-Judge Student Proposal Evals",
        "status": "completed",
        "eval_model": eval_model,
        "total_cases": total,
        "pass_rate": round(all_passed / total, 4),
        "mean_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0,
        "cases": results,
    }


if __name__ == "__main__":
    rep = run_evals()
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if rep.get("status") == "skipped":
        sys.exit(0)
    sys.exit(0 if rep.get("pass_rate") == 1.0 else 1)
