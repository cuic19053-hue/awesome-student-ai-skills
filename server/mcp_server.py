#!/usr/bin/env python3
"""MCP server exposing the same bounded tools used by the web Agent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parent
ROOT = SERVER_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from mcp.server.mcpserver import MCPServer
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools

store = Store()
tools = ProposalTools(store, ProjectRetriever(store))
server = MCPServer(
    name="awesome-student-ai-skills",
    version="0.1.0",
    description="大创创新训练申报 Agent 的项目资料、写作和导出工具。",
    instructions=(
        "只处理大学生大创创新训练项目。材料检索仅限当前项目中学生已确认的文件。"
        "先取证再写，不得编造事实；资料矛盾时询问用户。"
        "导出 Word 前运行 validate_project，缺失内容使用待补充标记。"
    ),
)


@server.tool()
def list_projects() -> dict[str, Any]:
    """列出本机已保存的大创申报项目。"""
    return {"projects": store.list_projects()}


@server.tool()
def create_project(
    title: str,
    level: str = "",
    discipline: str = "",
    school: str = "",
) -> dict[str, Any]:
    """创建一个本地申报项目；项目资料保存在配置的本机数据目录。"""
    project = store.create_project(title, level, discipline, school)
    return {
        "project_id": project["id"],
        "title": project["title"],
        "level": project["level"],
        "discipline": project["discipline"],
        "school": project["school"],
    }


@server.tool()
def get_project_state(project_id: str) -> dict[str, Any]:
    """读取项目基本设定、已确认事实、目录、草稿和材料确认状态。"""
    return tools.get_project_state(project_id)


@server.tool()
def add_text_material(project_id: str, filename: str, text: str) -> dict[str, Any]:
    """添加文本材料为待确认状态；未经确认不会进入本项目 RAG。"""
    return tools.add_text_material(project_id, filename, text)


@server.tool()
def confirm_project_material(
    project_id: str,
    document_id: str,
    corrected_text: str = "",
) -> dict[str, Any]:
    """用户确认识别文字后，将材料索引到当前项目 RAG。"""
    return tools.confirm_project_material(project_id, document_id, corrected_text)


@server.tool()
def get_writing_guidance(project_id: str, section: str = "") -> dict[str, Any]:
    """按需读取大创创新训练的写作指南。"""
    return tools.get_writing_guidance(project_id, section)


@server.tool()
def search_project_materials(project_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
    """在该项目已确认资料中做 RAG 检索，返回文件名和页码/段落来源。"""
    return tools.search_project_materials(project_id, query, top_k)


@server.tool()
def search_papers(query: str, limit: int = 5) -> dict[str, Any]:
    """通过 Crossref 查询真实论文元数据；仅有摘要/元数据时不得声称读过全文。"""
    return tools.search_papers(query, limit)


@server.tool()
def search_official_notices(project_id: str, query: str, school: str = "") -> dict[str, Any]:
    """搜索学校/政府官方域名的申报通知；返回链接供用户核验。"""
    project = store.get_project(project_id)
    if not project:
        return {"error": "找不到这个项目。"}
    return tools.search_official_notices(query, school or project["school"])


@server.tool()
def fetch_official_notice(url: str) -> dict[str, Any]:
    """读取用户提供的学校/政府官方 HTTPS 通知，仅允许 edu.cn/gov.cn 域名。"""
    return tools.fetch_official_notice(url)


@server.tool()
def save_project_fact(
    project_id: str,
    key: str,
    value: str,
    source_quote: str,
) -> dict[str, Any]:
    """保存学生确认且有原文证据支持的项目事实。source_quote 必须可逐字核验。"""
    return tools.save_project_fact(project_id, key, value, source_quote)


@server.tool()
def save_section(project_id: str, section_id: str, content: str) -> dict[str, Any]:
    """保存一章草稿，供网页预览和修改。"""
    return tools.save_section(project_id, section_id, content)


@server.tool()
def save_diagram(project_id: str, title: str, nodes: list[str]) -> dict[str, Any]:
    """保存已确认的图表节点并尝试生成本地图像预览。"""
    return tools.save_diagram(project_id, title, nodes)


@server.tool()
def validate_project(project_id: str) -> dict[str, Any]:
    """导出前基础检查：缺失信息、未确认材料和照片占位；不做自动评审打分。"""
    return tools.validate_project(project_id)


@server.tool()
def export_docx(project_id: str) -> dict[str, Any]:
    """显式生成 Word 草稿。缺失项会标为待补充，不得作为已核验正式申报书。"""
    return tools.export_docx(project_id)


@server.tool()
def simulate_review(project_id: str) -> dict[str, Any]:
    """用户主动要求时，对当前草稿做规则式模拟评审；仅供修改参考。"""
    return tools.simulate_review(project_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "streamable-http", "sse"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
