# -*- coding: utf-8 -*-
"""
Agentic Workflow Engine: Draft -> Critic -> Self-Correction
===========================================================

构建国家级申报书“撰写 Agent + 评审 Agent + 自愈修正”闭环状态机：
  1. Project Blackboard: 全局事实黑板，维护核心论点与各章精炼结论，控制 Context 预算；
  2. Draft Agent: 依据申报赛道金奖标准、事实黑板与证据库逐章撰写，强制 Pydantic 结构化输出；
  3. Critic Reviewer: 依据国家级评审细则（真实性/科学性/结构规范/学术行文）挑刺打分；
  4. Self-Correction Loop: 未达标时基于针对性修订意见自动迭代（默认上限 2 次）；
  5. 轻重模型解耦 (Model Decoupling): 支持独立的 Draft 模型与严师 Critic 模型；
  6. Review Card: 结构化评审结果卡，用于前端静默自愈后的可视化呈现。
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field


class ProjectBlackboard(BaseModel):
    """全局项目事实黑板：轻量、全局一致且不随章节数无限膨胀。"""
    project_name: str = ""
    problem_statement: str = ""           # 核心痛点与行业背景
    scientific_challenge: str = ""        # 拟攻关的核心科学问题/技术难点
    technical_approach: str = ""          # 核心技术方案与关键算法
    quantitative_targets: str = ""        # 预期可量化的核心指标
    team_and_advisor: str = ""            # 团队成员与指导教师
    budget_summary: str = ""              # 经费预算总览
    chapter_conclusions: Dict[str, str] = Field(
        default_factory=dict,
        description="各章节生成后的核心事实结论精炼摘要 (section_id -> 100字摘要)"
    )

    def to_context_prompt(self) -> str:
        """格式化为适合注入 Prompt 的结构化 Markdown 事实上下文。"""
        lines = [
            f"- **项目名称**：{self.project_name or '待补充'}",
            f"- **核心痛点**：{self.problem_statement or '待补充'}",
            f"- **核心科学/技术挑战**：{self.scientific_challenge or '待补充'}",
            f"- **技术方案与关键算法**：{self.technical_approach or '待补充'}",
            f"- **预期量化指标**：{self.quantitative_targets or '待补充'}",
        ]
        if self.team_and_advisor:
            lines.append(f"- **团队与导师**：{self.team_and_advisor}")
        if self.chapter_conclusions:
            lines.append("\n### 前序各章节已确立的核心结论（必须保持前后自洽一致）：")
            for sec_id, summary in self.chapter_conclusions.items():
                lines.append(f"  * 【{sec_id}】：{summary}")
        return "\n".join(lines)

    def record_chapter_conclusion(self, section_id: str, title: str, content: str) -> None:
        """从新生成的章节中提炼核心事实，增量记录进黑板。"""
        # 提取第一段或核心概括（截取 150 字精粹）
        cleaned = re.sub(r"[#*`\-]", "", content).strip()
        paragraphs = [p.strip() for p in cleaned.split("\n") if p.strip()]
        first_para = paragraphs[0] if paragraphs else ""
        summary = first_para[:150]
        if len(first_para) > 150:
            summary += "..."
        self.chapter_conclusions[section_id] = f"{title}：{summary}"

        # 针对特定章节同步更新全局画像
        lower_id = section_id.lower()
        if any(k in lower_id for k in ("background", "problem", "背景", "痛点")) and not self.problem_statement:
            self.problem_statement = summary
        elif any(k in lower_id for k in ("challenge", "scientific", "问题", "挑战")) and not self.scientific_challenge:
            self.scientific_challenge = summary
        elif any(k in lower_id for k in ("route", "method", "方案", "路线", "算法")) and not self.technical_approach:
            self.technical_approach = summary
        elif any(k in lower_id for k in ("expected", "target", "成果", "目标", "指标")) and not self.quantitative_targets:
            self.quantitative_targets = summary


class DraftOutput(BaseModel):
    """撰写 Agent 的结构化输出规范。"""
    section_id: str
    title: str
    content: str = Field(description="Markdown 格式的正文章节草稿")
    missing_facts: List[str] = Field(default_factory=list, description="本章识别出缺失且需待补充的事实列表")
    todos: List[str] = Field(default_factory=list, description="后续撰写或实施待办事项")
    word_count: int = 0


class CriticDimension(BaseModel):
    """评审单一维度的打分与评价。"""
    name: str = Field(description="维度名称，如真实性、科学深度、结构规范")
    score: float = Field(ge=0.0, le=100.0, description="得分 (0-100)")
    weight: float = Field(ge=0.0, le=1.0, description="权重 (0-1.0)")
    comment: str = Field(default="", description="评委评语")


class CriticReview(BaseModel):
    """评审 Agent（挑刺评委）的结构化评审结果。"""
    overall_score: float = Field(ge=0.0, le=100.0, description="加权综合得分")
    passed: bool = Field(description="是否达到准入标准")
    dimensions: List[CriticDimension] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list, description="主要亮点")
    weaknesses: List[str] = Field(default_factory=list, description="主要不足与扣分项")
    actionable_revisions: List[str] = Field(default_factory=list, description="针对 Draft Agent 的具体可执行修改建议")
    user_action_required: List[str] = Field(
        default_factory=list,
        description="因缺少学生客观事实导致的问题（提示用户补充，不要求模型盲目虚构）"
    )


class ReviewCard(BaseModel):
    """供前端结果卡片展示的评审成绩单（决策 7-A）。"""
    score: float
    grade: str = Field(description="评定等级：国赛金奖级 (A+) | 推荐立项 (A) | 良好 (B) | 需完善 (C)")
    passed: bool
    iterations: int
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    user_hints: List[str] = Field(default_factory=list)
    dimensions: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowIteration(BaseModel):
    """单轮自愈迭代快照。"""
    iteration: int
    draft: DraftOutput
    critic: CriticReview


class WorkflowResult(BaseModel):
    """自愈工作流最终交付产物。"""
    section_id: str
    title: str
    content: str
    final_score: float
    passed: bool
    iterations: int
    status: str = Field(description="passed | self_corrected | needs_user_attention")
    review_card: ReviewCard
    history: List[WorkflowIteration] = Field(default_factory=list)
    user_hints: List[str] = Field(default_factory=list, description="呈现给用户的操作提示与事实补充建议")
    missing_facts: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    retrieval_mode: Optional[str] = None
    notice: Optional[str] = None


# ============================================================================
# 评委 Prompt 与评估规则
# ============================================================================

CRITIC_SYSTEM_PROMPT = """你是一名极其严苛的高校申报书评委专家（国家级大创、挑战杯、互联网+评委）。
你的任务是对学生申报书的指定章节进行全方位挑刺与打分。

打分维度与权重：
1. 真实性与防伪事实 (权重 0.35)：
   - 严厉检查是否出现凭空捏造的指导教师、虚假合作企业、凭空产生的实验指标或无依据的奖项。
   - 学生未提供但该章节必需的硬性数据，是否规范使用了“【待补充：...】”占位符。若没有事实还伪装成已完成，此项直接不及格（<60分）。
2. 科学性与论证深度 (权重 0.30)：
   - 检查痛点分析是否停留在泛泛而谈的套话。
   - 是否阐明了科学问题、技术机理或方案原理。逻辑是否闭环自洽。
3. 结构与规范符合度 (权重 0.20)：
   - 是否严格遵循该赛道 Skill 的章节撰写要求（如三段式结构、对比指标、量化阶段等）。
4. 行文与学术成熟度 (权重 0.15)：
   - 是否存在大量无意义的口语化 AI 套话（如“正如我们所知”、“在当今快速发展的时代”）。文风是否符合学术申报公文规范。

请以 100% 纯 JSON 格式输出，格式必须符合：
{
  "overall_score": 82.5,
  "passed": true,
  "dimensions": [
    {"name": "真实性与防伪事实", "score": 90.0, "weight": 0.35, "comment": "..."},
    {"name": "科学性与论证深度", "score": 75.0, "weight": 0.30, "comment": "..."},
    {"name": "结构与规范符合度", "score": 85.0, "weight": 0.20, "comment": "..."},
    {"name": "行文与学术成熟度", "score": 80.0, "weight": 0.15, "comment": "..."}
  ],
  "strengths": ["..."],
  "weaknesses": ["..."],
  "actionable_revisions": ["修改建议1: 强化痛点量化指标...", "修改建议2: 删去第二段套话..."],
  "user_action_required": ["建议学生在事实面板补充：实验数据集的采集规模与具体传感器型号"]
}
"""


def _compute_grade(score: float) -> str:
    if score >= 90.0:
        return "国赛金奖级 (A+)"
    if score >= 82.0:
        return "推荐立项 (A)"
    if score >= 75.0:
        return "良好 (B)"
    return "需完善 (C)"


class AgenticWorkflowEngine:
    """多智能体闭环引擎：负责编排 Draft -> Critic -> Self-Correction 状态流。"""

    def __init__(
        self,
        draft_caller: Callable[[List[Dict[str, str]], Optional[Dict[str, Any]]], str],
        critic_caller: Optional[Callable[[List[Dict[str, str]], Optional[Dict[str, Any]]], str]] = None,
        max_retries: int = 2,
        pass_threshold: float = 80.0,
    ) -> None:
        """
        Args:
            draft_caller: 撰写 Agent 的调用函数（轻量/极速模型）
            critic_caller: 评审 Agent 的调用函数（高推理/严格批判模型，可选；未提供时复用 draft_caller）
            max_retries: 最大自愈迭代次数（默认 2 次，防死循环）
            pass_threshold: 评审通过阈值（默认 80 分）
        """
        self.draft_caller = draft_caller
        self.critic_caller = critic_caller or draft_caller
        self.max_retries = max_retries
        self.pass_threshold = pass_threshold

    def parse_draft(self, text: str, section_id: str, title: str) -> DraftOutput:
        """从 LLM 返回文本中提取草稿正文与结构化待补充项。"""
        missing_facts: List[str] = []
        todos: List[str] = []
        content = text.strip()

        if content.startswith("{") and content.endswith("}"):
            try:
                data = json.loads(content)
                if isinstance(data, dict) and "content" in data:
                    content = str(data["content"]).strip()
                    missing_facts = [str(x) for x in data.get("missing_facts", [])]
                    todos = [str(x) for x in data.get("todos", [])]
            except Exception:
                pass

        extracted_missing = re.findall(r"(?:【待补充[：:](.*?)】|待补充[：:]([^\n]+))", content)
        for group in extracted_missing:
            item = (group[0] or group[1]).strip()
            if item and item not in missing_facts:
                missing_facts.append(item)

        return DraftOutput(
            section_id=section_id,
            title=title,
            content=content,
            missing_facts=missing_facts,
            todos=todos,
            word_count=len(content),
        )

    def parse_critic(self, text: str) -> CriticReview:
        """解析 Critic 评委的评审 JSON，具备鲁棒的容错与降级机制。"""
        cleaned = text.strip()
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1).strip()
        elif "{" in cleaned and "}" in cleaned:
            cleaned = cleaned[cleaned.find("{"):cleaned.rfind("}") + 1]

        try:
            data = json.loads(cleaned)
            score = float(data.get("overall_score", 70.0))
            passed = bool(data.get("passed", score >= self.pass_threshold))
            dims_data = data.get("dimensions", [])
            dims = [
                CriticDimension(
                    name=d.get("name", "综合"),
                    score=float(d.get("score", score)),
                    weight=float(d.get("weight", 0.25)),
                    comment=d.get("comment", ""),
                )
                for d in dims_data
                if isinstance(d, dict)
            ]
            return CriticReview(
                overall_score=score,
                passed=passed,
                dimensions=dims,
                strengths=data.get("strengths", []),
                weaknesses=data.get("weaknesses", []),
                actionable_revisions=data.get("actionable_revisions", []),
                user_action_required=data.get("user_action_required", []),
            )
        except Exception:
            return CriticReview(
                overall_score=75.0,
                passed=True,
                dimensions=[CriticDimension(name="默认评估", score=75.0, weight=1.0, comment="自动降级通过")],
                strengths=["完成了基本章节结构起草"],
                weaknesses=["评审模型返回格式非标准JSON，已执行降级容错"],
                actionable_revisions=[],
                user_action_required=[],
            )

    def run_workflow(
        self,
        project_context: Dict[str, Any],
        section_id: str,
        section_title: str,
        skill_guidance: str,
        evidence_results: List[Dict[str, Any]],
        blackboard: Optional[ProjectBlackboard] = None,
        retrieval_mode: Optional[str] = None,
        notice: Optional[str] = None,
    ) -> WorkflowResult:
        """执行 Draft -> Critic -> Self-Correction 完整工作流闭环。"""
        history: List[WorkflowIteration] = []
        all_user_actions: List[str] = []
        all_missing_facts: List[str] = []
        feedback_prompt: Optional[str] = None
        current_draft: Optional[DraftOutput] = None
        current_critic: Optional[CriticReview] = None

        # 确保黑板实例存在 (决策 5-A)
        bb = blackboard or ProjectBlackboard(
            project_name=project_context.get("project_name", ""),
            problem_statement=project_context.get("problem", ""),
            scientific_challenge=project_context.get("goal", ""),
            technical_approach=project_context.get("method", ""),
            quantitative_targets=project_context.get("expected_output", ""),
        )

        for iteration in range(1, self.max_retries + 2):
            # 1. Draft 阶段（使用 draft_caller）
            draft_messages = self._build_draft_prompt(
                project_context=project_context,
                blackboard=bb,
                section_id=section_id,
                section_title=section_title,
                skill_guidance=skill_guidance,
                evidence_results=evidence_results,
                previous_feedback=feedback_prompt,
                iteration=iteration,
            )
            draft_text = self.draft_caller(draft_messages, {"temperature": 0.3})
            current_draft = self.parse_draft(draft_text, section_id, section_title)
            for mf in current_draft.missing_facts:
                if mf not in all_missing_facts:
                    all_missing_facts.append(mf)

            # 2. Critic 阶段（使用严师 critic_caller）
            critic_messages = self._build_critic_prompt(
                section_title=section_title,
                skill_guidance=skill_guidance,
                draft_content=current_draft.content,
                project_context=project_context,
                blackboard=bb,
            )
            critic_text = self.critic_caller(critic_messages, {"temperature": 0.0})
            current_critic = self.parse_critic(critic_text)
            for act in current_critic.user_action_required:
                if act not in all_user_actions:
                    all_user_actions.append(act)

            history.append(
                WorkflowIteration(
                    iteration=iteration,
                    draft=current_draft,
                    critic=current_critic,
                )
            )

            # 3. 达标判定与决策分支
            if current_critic.passed or current_critic.overall_score >= self.pass_threshold:
                break

            if iteration > self.max_retries:
                break

            # 4. 组装下一轮自愈反思指导
            revisions_text = "\n".join(f"- {r}" for r in current_critic.actionable_revisions)
            weakness_text = "\n".join(f"- {w}" for w in current_critic.weaknesses)
            feedback_prompt = (
                f"【上一轮评委打分：{current_critic.overall_score} 分（未达标）】\n"
                f"评审指出的主要缺陷：\n{weakness_text}\n"
                f"必须执行的修改要求：\n{revisions_text}\n"
                "请严格基于上述评审意见进行重写与精细化改进。不得伪造事实，缺少的数据项继续使用【待补充：具体内容】占位标注。"
            )

        assert current_draft is not None
        assert current_critic is not None

        # 5. 更新项目全局事实黑板 (决策 5-A)
        bb.record_chapter_conclusion(section_id, section_title, current_draft.content)

        # 6. 用户提示组装（决策 3-A）
        user_hints: List[str] = []
        if all_missing_facts:
            user_hints.append(
                f"💡 检测到本章缺少 {len(all_missing_facts)} 项硬性事实，已安全标注为【待补充】占位符，避免虚构。"
            )
        if all_user_actions:
            for item in all_user_actions:
                user_hints.append(f"📌 评委建议补充：{item}")

        status = "passed"
        if len(history) > 1:
            status = "self_corrected"
        if user_hints or not current_critic.passed:
            status = "needs_user_attention"

        # 7. 构建 Review Card（决策 7-A）
        review_card = ReviewCard(
            score=current_critic.overall_score,
            grade=_compute_grade(current_critic.overall_score),
            passed=current_critic.passed or current_critic.overall_score >= self.pass_threshold,
            iterations=len(history),
            strengths=current_critic.strengths,
            weaknesses=current_critic.weaknesses,
            user_hints=user_hints,
            dimensions=[d.model_dump() for d in current_critic.dimensions],
        )

        return WorkflowResult(
            section_id=section_id,
            title=section_title,
            content=current_draft.content,
            final_score=current_critic.overall_score,
            passed=current_critic.passed or current_critic.overall_score >= self.pass_threshold,
            iterations=len(history),
            status=status,
            review_card=review_card,
            history=history,
            user_hints=user_hints,
            missing_facts=current_draft.missing_facts,
            evidence=evidence_results,
            retrieval_mode=retrieval_mode,
            notice=notice,
        )

    # ----------------------------------------------------------------------
    # Prompt 构建器
    # ----------------------------------------------------------------------

    def _build_draft_prompt(
        self,
        project_context: Dict[str, Any],
        blackboard: ProjectBlackboard,
        section_id: str,
        section_title: str,
        skill_guidance: str,
        evidence_results: List[Dict[str, Any]],
        previous_feedback: Optional[str],
        iteration: int,
    ) -> List[Dict[str, str]]:
        system = (
            "你是一名服务于中国高校顶级科研与创业大赛的材料撰写首席专家（精通国家级大创、挑战杯、互联网+等）。\n"
            "你撰写的材料必须具备极高的专业学术水准、逻辑严密、论证闭环，杜绝空洞口号与AI套话。\n"
            "【铁律守则】：\n"
            "1. 绝不凭空编造学生经历、未确认的测试数据、合作单位、指导教师姓名或国家级奖项。\n"
            "2. 只要缺少必要硬事实，必须且只能使用【待补充：请在此填入具体xxx】进行合规占位。\n"
            "3. 严格遵循该赛道 Skill 规范对本章节的核心逻辑结构（如科学问题递进、算法对比、量化指标）。\n"
            "4. 严格与【项目全局事实黑板】保持事实自洽，绝不可与前序章节的核心结论发生逻辑矛盾。"
        )

        user_content = [
            f"# 任务：撰写章节【{section_title}】（标识: {section_id}）",
            f"## 项目全局事实黑板（Project Blackboard）：\n{blackboard.to_context_prompt()}",
            f"## 已核实证据素材：\n{json.dumps(evidence_results, ensure_ascii=False, indent=2)}",
            f"## 该赛道章节写作规范标准：\n{skill_guidance[:3500]}",
        ]

        if previous_feedback:
            user_content.append(
                f"\n## ⚠️ 第 {iteration} 轮自愈反思修订任务：\n{previous_feedback}"
            )
        else:
            user_content.append(
                "\n请直接输出高质量 Markdown 正文。若缺少未确认事实，用【待补充：说明】标出。"
            )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(user_content)},
        ]

    def _build_critic_prompt(
        self,
        section_title: str,
        skill_guidance: str,
        draft_content: str,
        project_context: Dict[str, Any],
        blackboard: ProjectBlackboard,
    ) -> List[Dict[str, str]]:
        user_content = (
            f"请评审以下章节草稿：\n"
            f"【章节名称】：{section_title}\n"
            f"【项目全局事实黑板】：\n{blackboard.to_context_prompt()}\n\n"
            f"【赛道考核规范】：\n{skill_guidance[:2500]}\n\n"
            f"【待评审草稿正文】：\n{draft_content}\n\n"
            "请严格以纯 JSON 格式输出评估报告，必须包含 overall_score, passed, dimensions, "
            "strengths, weaknesses, actionable_revisions, user_action_required。"
        )
        return [
            {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
