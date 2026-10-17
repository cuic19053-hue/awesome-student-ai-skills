# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import pytest
from server.proposal.workflow import (
    AgenticWorkflowEngine,
    DraftOutput,
    CriticReview,
    ProjectBlackboard,
    WorkflowResult,
)


def test_project_blackboard_conclusions_and_context():
    bb = ProjectBlackboard(
        project_name="AI多模态火场搜救系统",
        problem_statement="复杂烟雾环境下红外视觉穿透力弱",
        scientific_challenge="多传感器异构特征对齐与极低时延融合",
        technical_approach="轻量化双光注意力特征金字塔模型",
        quantitative_targets="端到端推理时延 < 15ms，小目标检出率 > 88%",
    )
    # 模拟第 1 章节生成完毕后，自动回写黑板
    bb.record_chapter_conclusion(
        section_id="background",
        title="1. 项目立项背景",
        content="本项目针对复杂森林及工业火灾搜救场景，传统单模态相机失效严重。通过引入毫米波雷达与长波红外融合，突破能见度限制。"
    )
    prompt_text = bb.to_context_prompt()
    assert "AI多模态火场搜救系统" in prompt_text
    assert "1. 项目立项背景" in prompt_text
    assert "毫米波雷达" in prompt_text


def test_parse_draft_extracts_missing_facts():
    engine = AgenticWorkflowEngine(draft_caller=lambda msgs, opts: "")
    raw = (
        "## 1.1 研究背景\n"
        "本项目针对复杂火灾场景中的多源传感器融合进行攻关。"
        "【待补充：请在此填写具体火场模拟试验场地与温湿度条件】\n"
        "系统拟采用双光热成像模组，待补充：具体模组镜头焦距与帧率。"
    )
    draft = engine.parse_draft(raw, "background", "研究背景")
    assert draft.section_id == "background"
    assert "复杂火灾场景" in draft.content
    assert len(draft.missing_facts) >= 2
    assert any("火场模拟试验场地" in item for item in draft.missing_facts)
    assert any("模组镜头焦距" in item for item in draft.missing_facts)


def test_parse_critic_robust_json():
    engine = AgenticWorkflowEngine(draft_caller=lambda msgs, opts: "")
    raw_markdown_json = """
    一些思考过程...
    ```json
    {
      "overall_score": 88.5,
      "passed": true,
      "dimensions": [
        {"name": "真实性与防伪事实", "score": 92.0, "weight": 0.35, "comment": "规范使用待补充"}
      ],
      "strengths": ["论述闭环清晰"],
      "weaknesses": ["字数可稍作扩充"],
      "actionable_revisions": [],
      "user_action_required": ["请学生补充指导教师职称"]
    }
    ```
    """
    review = engine.parse_critic(raw_markdown_json)
    assert review.overall_score == 88.5
    assert review.passed is True
    assert len(review.strengths) == 1
    assert "请学生补充指导教师职称" in review.user_action_required


def test_workflow_runs_self_correction_with_decoupled_models():
    # 验证决策 6-A：Draft 与 Critic 模型解耦
    draft_calls = []
    critic_calls = []

    def mock_draft(messages, options):
        prompt_text = messages[-1]["content"]
        if "第 2 轮自愈反思修订任务" in prompt_text:
            draft_calls.append("draft_round_2")
            return "这是根据评审意见重新修订后的高质量技术方案，已增加算法对比与具体时延指标。"
        else:
            draft_calls.append("draft_round_1")
            return "初稿：本项目研究无人机目标检测，效果很好。【待补充：具体数据集样本量】"

    def mock_critic(messages, options):
        prompt_text = messages[-1]["content"]
        if "重新修订后的高质量技术方案" in prompt_text:
            critic_calls.append("critic_round_2")
            return json.dumps({
                "overall_score": 86.0,
                "passed": True,
                "dimensions": [{"name": "综合", "score": 86.0, "weight": 1.0, "comment": "修改后达标"}],
                "strengths": ["技术路线详细自洽"],
                "weaknesses": [],
                "actionable_revisions": [],
                "user_action_required": []
            })
        else:
            critic_calls.append("critic_round_1")
            return json.dumps({
                "overall_score": 65.0,
                "passed": False,
                "dimensions": [{"name": "综合", "score": 65.0, "weight": 1.0, "comment": "内容偏空泛"}],
                "strengths": [],
                "weaknesses": ["论述偏空泛，缺少指标对比"],
                "actionable_revisions": ["请补全与传统算法的对比并明确时延指标"],
                "user_action_required": ["建议提供真实实验测试平台型号"]
            })

    engine = AgenticWorkflowEngine(
        draft_caller=mock_draft,
        critic_caller=mock_critic,
        max_retries=2,
        pass_threshold=80.0,
    )
    result = engine.run_workflow(
        project_context={"project_name": "消防无人机项目"},
        section_id="research_route",
        section_title="技术路线与关键技术",
        skill_guidance="要求必须具备算法对比表与指标量化",
        evidence_results=[],
    )

    assert result.passed is True
    assert result.final_score == 86.0
    assert result.iterations == 2
    assert "重新修订后" in result.content
    assert draft_calls == ["draft_round_1", "draft_round_2"]
    assert critic_calls == ["critic_round_1", "critic_round_2"]
    # 验证决策 7-A：包含结构化 review_card 与等级
    assert result.review_card.grade == "推荐立项 (A)"
    assert result.review_card.score == 86.0
    assert any("评委建议补充" in hint for hint in result.user_hints)


def test_workflow_max_retries_graceful_exit():
    def mock_failing_critic(messages, options):
        return json.dumps({
            "overall_score": 72.0,
            "passed": False,
            "weaknesses": ["实验数据不足"],
            "actionable_revisions": ["需要增加实测结果"],
            "user_action_required": ["需学生提供实测数据报告"]
        })

    engine = AgenticWorkflowEngine(
        draft_caller=lambda msgs, opts: "正文草稿内容...【待补充：核心实验数据】",
        critic_caller=mock_failing_critic,
        max_retries=1,
        pass_threshold=80.0,
    )
    result = engine.run_workflow(
        project_context={},
        section_id="experiment",
        section_title="实验结果与分析",
        skill_guidance="需给出定量分析",
        evidence_results=[],
    )

    assert result.iterations == 2  # round 1 + 1 retry = 2
    assert result.passed is False
    assert result.status == "needs_user_attention"
    assert result.review_card.grade == "需完善 (C)"
    assert len(result.user_hints) >= 1
    assert "核心实验数据" in result.missing_facts[0]
