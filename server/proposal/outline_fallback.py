"""Editable fallback outlines that never invent a student's track or results."""
from __future__ import annotations

import re
from typing import Any


_CHALLENGE_CATEGORIES = {
    "natural_science": re.compile(r"自然科学(?:类|方向|学术论文)?"),
    "social_science": re.compile(r"哲学社会科学|哲社|社会科学|社会调查|社会调研"),
    "tech_invention": re.compile(r"科技发明制作|科技发明|发明制作|发明实物|发明作品"),
}
_CHALLENGE_NAMES = {
    "natural_science": "自然科学类学术论文",
    "social_science": "哲学社会科学类社会调查报告和学术论文",
    "tech_invention": "科技发明制作",
}
_CHALLENGE_SECTIONS = {
    "natural_science": [
        ("work_info", "作品基本信息"), ("abstract", "作品摘要"),
        ("background", "研究背景与问题"), ("method", "研究方法与过程"),
        ("results", "研究结果与讨论"), ("conclusion", "结论与不足"),
        ("innovation", "创新点"), ("references", "参考文献与附件"),
    ],
    "social_science": [
        ("work_info", "作品基本信息"), ("abstract", "作品摘要"),
        ("background", "调查背景与问题"), ("method", "调查设计与研究方法"),
        ("results", "调查结果与分析"), ("conclusion", "结论、建议与局限"),
        ("innovation", "作品特点与创新点"), ("references", "参考文献与附件"),
    ],
    "tech_invention": [
        ("work_info", "作品基本信息"), ("abstract", "作品简介"),
        ("background", "选题背景与需求"), ("method", "设计方案与制作过程"),
        ("results", "测试验证与结果"), ("conclusion", "应用价值与局限"),
        ("innovation", "作品创新点"), ("references", "参考文献与附件"),
    ],
}
_CHALLENGE_GENERIC = [
    ("work_info", "作品基本信息"), ("abstract", "作品简介"),
    ("background", "作品背景与问题"), ("method", "作品内容与方法"),
    ("results", "已有工作与成果"), ("conclusion", "局限与下一步"),
    ("references", "参考资料与附件"),
]


def _challenge_category(value: Any) -> str | None:
    """Infer only an unambiguous, affirmative explicit work category."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text in _CHALLENGE_CATEGORIES:
        return text
    if re.search(r"示例|举例|例如|比如|假设|虚构", text):
        return None
    hits = set()
    for category, pattern in _CHALLENGE_CATEGORIES.items():
        for match in pattern.finditer(text):
            previous = re.split(r"[，,。；;！!？?\n]", text[:match.start()])[-1][-10:]
            if re.search(r"(?:不是|不属于|不选|排除|不要|并非|而非)\s*$", previous):
                continue
            hits.add(category)
    return next(iter(hits)) if len(hits) == 1 else None


def challenge_cup_fallback(project: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    """Build a modest fallback; the student may edit it before confirmation.

    Category-specific sections are used only when an explicit category exists
    in confirmed facts or the initial request; no experiments, awards, policy
    details, or school template requirements are implied.
    """
    state = project.get("state") or {}
    facts = state.get("confirmed_facts") or {}
    explicit = []
    if isinstance(facts, dict):
        explicit = [_challenge_category(facts.get(key)) for key in ("work_type", "category", "work_category") if facts.get(key)]
    explicit = [item for item in explicit if item]
    category = (explicit[0] if len(set(explicit)) == 1 else None) if explicit else _challenge_category(state.get("initial_request"))
    pairs = _CHALLENGE_SECTIONS[category] if category else _CHALLENGE_GENERIC
    if category:
        notice = f"已按你提供的“{_CHALLENGE_NAMES[category]}”整理备用目录；请按学校要求调整。"
    else:
        notice = "请确认作品类别：自然科学类、哲学社会科学类或科技发明制作。当前为可编辑的通用目录。"
    return [{"id": sid, "title": title} for sid, title in pairs], notice


_POPULAR_SECTIONS = {
    "innovation-research": [
        ("project_info", "项目基本信息"), ("abstract", "项目摘要"),
        ("background", "选题背景与研究问题"), ("objectives", "研究目标与内容"),
        ("method", "研究方法与技术路线"), ("innovation", "项目特色与创新"),
        ("foundation", "现有基础与可行性"), ("schedule", "进度安排"),
        ("budget", "经费预算"), ("outcomes", "预期成果"), ("references", "参考资料与附件"),
    ],
    "internet-plus": [
        ("project_info", "项目基本信息"), ("summary", "项目概述"),
        ("problem", "需求与解决方案"), ("product", "产品或服务"),
        ("market", "市场与用户分析"), ("business", "商业模式与运营计划"),
        ("competition", "竞争与项目优势"), ("team", "团队与分工"),
        ("finance", "财务规划与资金需求"), ("progress", "实施计划与风险"),
        ("attachments", "参考资料与附件"),
    ],
    "internet-plus-red-tour": [
        ("project_info", "项目基本信息"), ("summary", "项目概述"),
        ("background", "服务地区背景与实际需求"), ("solution", "产品或服务方案"),
        ("implementation", "实践实施与帮扶情况"), ("impact", "社会价值与成效"),
        ("sustainability", "可持续运营方案"), ("team", "团队与分工"),
        ("plan", "后续计划与风险"), ("attachments", "参考资料与附件"),
    ],
    "social-survey": [
        ("project_info", "实践项目基本信息"), ("background", "调研背景与问题"),
        ("objectives", "调研目标与对象"), ("method", "调研内容与方法"),
        ("schedule", "实施计划与日程"), ("team", "团队分工与准备"),
        ("safety", "安全保障与应急安排"), ("outcomes", "预期成果"),
        ("budget", "经费预算"), ("attachments", "参考资料与附件"),
    ],
    "graduate-recommendation": [
        ("profile", "个人基本情况"), ("study", "学业与语言能力"),
        ("research", "科研与实践经历"), ("awards", "成果与获奖情况"),
        ("motivation", "申请动机与专业匹配"), ("plan", "未来学习与研究计划"),
        ("attachments", "证明材料与附件"),
    ],
}


def recommended_outline(project: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    """Return an editable starting structure, without claiming school rules."""
    state = project.get("state") or {}
    skill_id = state.get("skill_id") or ""
    if not skill_id:
        return [], "请先在对话中确定申报类型，再获取推荐目录。"
    if skill_id == "challenge-cup":
        return challenge_cup_fallback(project)
    pairs = _POPULAR_SECTIONS.get(skill_id)
    if pairs is None:
        category = state.get("skill_category") or ""
        if category in {"scholarship", "honor", "political", "military", "study_abroad"}:
            pairs = [("application", "申请书")]
        else:
            pairs = [("overview", "基本情况"), ("background", "背景与目标"),
                     ("content", "主要内容"), ("plan", "实施安排"),
                     ("foundation", "现有基础"), ("references", "参考资料与附件")]
    notice = "这是可编辑的起始目录，请结合学校通知和模板调整。"
    return [{"id": sid, "title": title} for sid, title in pairs], notice
