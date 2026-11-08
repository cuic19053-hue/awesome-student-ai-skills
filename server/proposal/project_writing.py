"""Detect explicit requests to draft project text, not requests for advice."""
from __future__ import annotations

import re
from typing import Any


def is_explicit_project_draft(text: str, skill: dict[str, Any] | None) -> bool:
    if not skill or skill.get("category") not in {"research", "competition", "practice"}:
        return False
    if not isinstance(text, str) or re.search(r"怎么写|如何写|怎样写|写作思路|写作建议|写作方法", text):
        return False
    # A refusal to write the requested text must not turn into a writing
    # instruction. A separate instruction not to invent facts is allowed.
    clauses = re.split(r"[，,。；;！？?\n]", text)
    subject = (r"(?:简介|摘要|背景|正文|草稿|申请|申报|计划书|方案|章节|研究目标|市场分析|商业模式|"
               r"实施计划|团队介绍|预算|立项依据|研究内容|研究方法|技术路线|创新点|可行性分析|预期成果|"
               r"进度安排|项目目标|调研目标|调研内容|调查内容|调查方法|用户需求|产品介绍|风险分析)")
    denial = r"(?:不要|别|不必|无需|不用|暂不|不需要)(?:帮我|再|先|直接)?(?:写|撰写|起草|生成|编写)"
    if any(re.search(denial + r".{0,15}" + subject, clause)
           or re.search(subject + r".{0,10}" + denial, clause)
           for clause in clauses):
        return False
    return bool(re.search(r"(?:帮我|请|直接|先|重新|给我|为我).{0,12}(?:写|起草|撰写|生成|编写)"
                          r".{0,30}" + subject, text)
                or re.search(r"(?:起草|撰写|编写).{0,20}" + subject, text)
                or re.search(subject + r".{0,10}(?:帮我|请|直接|先|重新).{0,6}(?:写|起草|撰写|生成|编写)", text))


def project_draft_guidance(skill_id: str) -> str:
    """Give focused writing guidance without treating an example as a fact.

    Guidance is intentionally about the requested section only; it must not
    replace the student's instructions or make unverified contest rules.
    """
    shared = (
        "\n正文质量要求：只写本轮要求的部分，优先使用学生明确提供或已确认材料中的具体信息，"
        "讲清对象、问题、做法及其联系，不堆砌口号或反复套话。"
        "区分已有事实、拟议方案和预期结果；未确认的方案要写成可讨论的建议，不能写成已决定或已完成。"
        "没有根据的调查数据、成果、合作单位、市场规模、收益、预算、论文及政策文件不得自行补造，"
        "缺少且确需填写的内容用简短的【待补充】占位。不要因为缺资料虚构一段完整背景。"
    )
    specifics = {
        "innovation-research": "大创创新训练：依据实际研究对象，围绕问题、目标、研究内容和方法的对应关系展开；不要假设项目一定涉及软件、算法或实验。",
        "entrepreneurship-training": "大创创业训练：结合学生提出的对象与服务，解释需求、拟议方案和验证路径；不要默认已经注册公司或产生收入。",
        "entrepreneurship-practice": "大创创业实践：区分学生提供的现有经营情况与拟实施计划，不补造注册、营收或合作事实。",
        "challenge-cup": "挑战杯：按学生提供的研究对象与申报类别组织问题、方法及成果；社会调查、学术论文与发明制作各有侧重，不把某一类的研究方法或成果套到其他类。",
        "internet-plus": "创新大赛：围绕学生实际提出的目标用户、需求、产品或服务和实施路径写作；市场、定价、营收、融资及用户数量均需依据，未提供时不编数字。",
        "internet-plus-red-tour": "创新大赛红旅：围绕学生实际提出的服务对象、需求、行动与持续开展方式写作；不虚构帮扶对象、规模、成果或合作单位。",
        "social-survey": "三下乡社会调查：区分拟调查的问题、方法和已取得的结果；数量、时间、地点及政策依据未提供时用占位，尚未实地调查时不写已有样本或走访结果。实施方法按本轮要求说明调查目标与对象、问卷或访谈设计、样本选择、知情同意与个人信息保护、记录分析、阶段安排及安全措施；未确定的设计表述为建议，不当作既定事实。",
    }
    detail = specifics.get(str(skill_id or ""))
    return shared + ("\n" + detail if detail else "")


def project_sources_allowed(history: list[dict[str, Any]], user_text: str) -> bool:
    """Honor the student's latest explicit choice about uploaded materials."""
    allowed = True
    for item in [*history, {"role": "user", "content": user_text}]:
        if item.get("role") != "user" or not isinstance(item.get("content"), str):
            continue
        for clause in re.split(r"[，,。；;！？?\n]", item["content"]):
            denial = r"(?:不要|别|禁止|不能|不可|不允许|不希望|不想|不需要|无需|不用|不)"
            action = r"(?:使用|引用|读取|检索)"
            material = r"(?:附件|材料|资料|文档|文件)"
            if (re.search(denial + r"(?:再)?" + action + r".{0,12}" + material, clause)
                    or re.search(material + r".{0,8}" + denial + r"(?:再)?" + action, clause)):
                allowed = False
            elif (re.search(r"(?:可以|允许|同意|请|恢复)(?:再|重新|继续)?" + action + r".{0,12}" + material, clause)
                  or re.search(material + r".{0,8}(?:可以|允许|同意)(?:再|重新|继续)?" + action, clause)):
                allowed = True
    return allowed


def explicit_public_lookup(text: str) -> bool:
    """Enable external lookup only for an affirmative search request."""
    for clause in re.split(r"[，,。；;！？?\n]", text):
        if re.search(r"(?:不要|别|禁止|不必|无需|不用|不需要)(?:再)?(?:查询|查找|检索|搜索|联网|查阅|查)", clause):
            continue
        if re.search(r"(?:查询|查找|检索|搜索|联网|查阅|查).{0,16}(?:文献|论文|通知|政策|数据|资料|依据|来源)", clause):
            return True
    return False
