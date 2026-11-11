"""The explicitly granted, project-scoped tool surface for chat turns."""
from __future__ import annotations

import json
import re
from typing import Any

from .skills import discovery_tool_schemas, invoke_discovery_tool
from .execution_budget import execution_budget


# New registered tools do not automatically become available to the model.
CHAT_TOOLS = frozenset({
    "get_project_state", "get_writing_guidance", "search_project_materials",
    "search_public_knowledge", "search_papers", "search_official_notices",
    "fetch_official_notice", "save_project_fact", "validate_project",
})
DISCOVERY_TOOLS = frozenset({"list_available_skills", "load_skill_guidance"})

TOOL_LABELS = {
    "list_available_skills": "正在查看可用技能…",
    "load_skill_guidance": "正在读取当前赛道指南…",
    "search_project_materials": "正在检索项目资料依据…",
    "search_public_knowledge": "正在检索赛道资料及适用范围…",
    "search_papers": "正在检索真实前沿学术文献…",
    "search_official_notices": "正在检索官方申报通知与指南…",
    "fetch_official_notice": "正在读取官方通知页面原文…",
    "get_writing_guidance": "正在查阅赛道写作指南规范…",
    "save_project_fact": "正在核对并提炼项目事实…",
    "validate_project": "正在执行项目完整性预检…",
    "get_project_state": "正在读取项目当前配置与状态…",
}


def is_personal_writing_request(user_text: str) -> bool:
    """Do not restrict ordinary lookup or an explicit comparison request."""
    text = user_text if isinstance(user_text, str) else ""
    if (re.search(r"对比|比较|差异|区别|怎么写|怎样写|如何写|写作方法|写作思路", text)
            or re.search(r"分别.{0,12}(?:他|她|两(?:人|位|份)|不同(?:人|学生|申请人|资料))", text)
            or re.search(r"(?:不要|别|不用|无需|暂不)(?:帮我|给我|先|再)?(?:写|起草|撰写|生成|润色|改写)", text)):
        return False
    action = r"(?:写|起草|撰写|生成|润色|改写|修改|优化|扩写|续写|整理|梳理|给我一份)"
    subject = r"(?:申请|个人|陈述|自荐|简历|经历|成绩|学习|科研|文书|材料|正文|草稿)"
    return bool(re.search(action + r".{0,35}" + subject + "|" + subject + r".{0,25}" + action, text))


class ChatToolRouter:
    """Provide schemas and enforce the same grant again at invocation time."""

    def __init__(self, tools: Any, project_id: str, project: dict[str, Any], *, user_text: str = "",
                 deadline: float | None = None):
        self.tools = tools
        self.project_id = project_id
        self.project = project
        self.user_text = user_text
        self.deadline = deadline
        self.schemas = [schema for schema in tools.schemas()
                        if schema["function"]["name"] in CHAT_TOOLS]
        self.schemas.extend(discovery_tool_schemas())
        self.allowed = {schema["function"]["name"] for schema in self.schemas}
        self.project_scoped = {
            schema["function"]["name"] for schema in self.schemas
            if "project_id" in schema["function"].get("parameters", {}).get("properties", {})
        }

    def invoke(self, call: dict[str, Any]) -> tuple[str, Any]:
        with execution_budget(self.deadline):
            return self._invoke(call)

    def _invoke(self, call: dict[str, Any]) -> tuple[str, Any]:
        function = call.get("function") or {}
        if not isinstance(function, dict):
            return "", {"error": "工具调用格式无效。"}
        name = str(function.get("name") or "")
        if name not in self.allowed:
            return name, {"error": "该操作需要通过工作台的确认流程执行，或未获授权。"}
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return name, {"error": "工具参数不是有效的 JSON。"}
        if not isinstance(arguments, dict):
            return name, {"error": "工具参数必须是对象。"}
        arguments = dict(arguments)
        if name in DISCOVERY_TOOLS:
            return name, invoke_discovery_tool(name, arguments, self.project)
        if name in self.project_scoped:
            arguments["project_id"] = self.project_id
        history = None
        sources_allowed = True
        preference_unavailable = False
        if name in {"search_project_materials", "get_project_state"}:
            from .project_writing import project_sources_allowed
            try:
                history = self.tools.store.messages(self.project_id, limit=200)
            except Exception:
                sources_allowed = False
                preference_unavailable = True
            else:
                sources_allowed = project_sources_allowed(history, self.user_text)
            if name == "search_project_materials" and preference_unavailable:
                # Do not retrieve files when the student's saved choice cannot
                # be checked; the model can still respond without that source.
                return name, {"results": [], "retrieval_mode": "preference_unavailable",
                              "message": "暂时无法确认资料使用设置，请稍后重试。"}
            if name == "search_project_materials" and not sources_allowed:
                return name, {"results": [], "retrieval_mode": "disabled_by_user",
                              "message": "你要求暂不使用上传的材料，本次没有检索。"}
        result = self.tools.invoke(name, arguments)
        if name == "get_project_state" and isinstance(result, dict) and not sources_allowed:
            result = {**result, "documents": []}
        if name == "search_project_materials" and isinstance(result, dict) and is_personal_writing_request(self.user_text):
            from .personal_source_filter import filter_personal_evidence
            from .skills import registry
            skill = registry.get(str((self.project.get("state") or {}).get("skill_id") or ""))
            if skill:
                result, excluded = filter_personal_evidence(
                    skill, self.project, history if history is not None else [],
                    self.tools.store.list_documents(self.project_id), result,
                )
                if excluded:
                    result["message"] = "部分个人资料的申请人姓名不同，未用于本次写作；请核对材料。"
        return name, result
