#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
awesome-student-ai-skills · Model Context Protocol (MCP) Server
==============================================================

将 35 个高校学生申报材料 AI Skills（大创、挑战杯、互联网+、国奖、保研等）
封装为标准 MCP 工具，供 Codex、Claude Code、Cursor 等 AI Agent 客户端调用。

提供的核心工具：
  - list_student_skills: 列出全部 35 个申报赛道及分类
  - route_student_skill: 根据用户诉求智能路由推荐最佳赛道
  - get_skill_info: 获取指定赛道详情与元数据
  - get_skill_requirements: 获取指定赛道的信息采集字段清单与撰写指南
  - generate_student_doc: 渲染生成规范排版的 Word (.docx) 申报材料文档
  - simulate_student_review: 模拟评委盲审打分与给出改进建议
  - list_school_templates: 列出支持的学校排版样式（北大/清华/武大/浙大/通用）
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# 优先尝试使用 mcp 2.x 的 MCPServer，兼容 mcp 1.x FastMCP
try:
    from mcp.server.mcpserver import MCPServer
    ServerClass = MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
        ServerClass = FastMCP
    except ImportError:
        raise RuntimeError("请先安装 mcp 依赖: pip install 'mcp>=1.3.0'")

PROJECT_DIR = Path(__file__).resolve().parent
UTILS_DIR = PROJECT_DIR / "utils"
SUBSKILLS_DIR = PROJECT_DIR / "subskills"
INDEX_JSON_PATH = PROJECT_DIR / "index.json"
SCHOOLS_DIR = UTILS_DIR / "schools"

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from utils.dispatcher import Dispatcher

server = ServerClass("awesome-student-ai-skills")
_dispatcher = Dispatcher()


def _normalize_skill_id(skill_name: str) -> str:
    """归一化 skill 名称，支持下划线或连字符"""
    name = skill_name.strip().lower()
    # 尝试在 index 中查找匹配项
    for s in _dispatcher.skills:
        s_name = s.get("name", "")
        s_id = s.get("id", "")
        if name in (s_name.lower(), s_id.lower(), s_name.replace("-", "_").lower()):
            return s_name
    return name


@server.tool()
def list_student_skills(category: Optional[str] = None) -> Dict[str, Any]:
    """
    列出所有支持的高校学生申报书与申请材料赛道（共 35 个）。

    参数:
      category: 可选分类过滤。支持:
        - 'research': 科研立项 / 大创（创新训练、创业训练、创业实践等）
        - 'competition': 学科竞赛（挑战杯、互联网+、红旅赛道等）
        - 'scholarship': 奖学金（国家奖学金、国家励志、校级、企业专项等）
        - 'honor': 荣誉评优（优秀毕业生、三好学生、优秀学生干部等）
        - 'political': 政治身份（入团申请、思想汇报、转正申请等）
        - 'practice': 实践活动（三下乡社会调查、支教、科技服务、西部计划等）
        - 'study_abroad': 公派留学 / 国际交流
        - 'military': 应征入伍
        - 'other': 转专业等
    """
    try:
        with open(INDEX_JSON_PATH, "r", encoding="utf-8") as f:
            index_data = json.load(f)

        skills = index_data.get("skills", [])
        categories = index_data.get("categories", {})

        if category:
            cat_norm = category.strip().lower()
            skills = [s for s in skills if s.get("category", "").lower() == cat_norm]

        return {
            "total": len(skills),
            "categories": categories,
            "skills": [
                {
                    "name": s.get("name"),
                    "id": s.get("id"),
                    "display_name": s.get("display_name"),
                    "category": s.get("category"),
                    "description": s.get("description"),
                    "triggers": s.get("triggers", [])[:5],
                }
                for s in skills
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@server.tool()
def route_student_skill(query: str, top_n: int = 3) -> Dict[str, Any]:
    """
    根据学生的意图或诉求描述（如“我想写一个计算机视觉的大创”、“准备申请国家奖学金”），
    智能匹配并推荐最合适的前 N 个申报材料赛道。

    参数:
      query: 用户的自然语言诉求或关键词
      top_n: 返回推荐赛道的数量（默认 3）
    """
    try:
        matches = _dispatcher.dispatch(query, top_n=top_n)
        return {
            "query": query,
            "recommended_skills": matches,
            "note": "匹配得分越高越精准。如需该赛道的具体撰写指南，可调用 get_skill_requirements 工具。"
        }
    except Exception as e:
        return {"error": str(e)}


@server.tool()
def get_skill_info(skill_name: str) -> Dict[str, Any]:
    """
    获取指定申报材料赛道的详细元数据与配置。

    参数:
      skill_name: 赛道名称或标识（如 'innovation-research', 'national-scholarship', 'challenge-cup'）
    """
    norm_name = _normalize_skill_id(skill_name)
    info = _dispatcher.info(norm_name)
    if not info:
        info = _dispatcher.info(norm_name.replace("-", "_"))
    if not info:
        return {"error": f"未找到名为 '{skill_name}' 的赛道，请调用 list_student_skills 查看所有有效名称。"}
    return info


@server.tool()
def get_skill_requirements(skill_name: str) -> Dict[str, Any]:
    """
    获取指定赛道的信息采集清单（必填项、字段规范、评分避坑要点）。
    Agent 在为用户撰写申报书前，应调用此工具获取必须向用户询问的关键信息清单。

    参数:
      skill_name: 赛道名称（如 'innovation-research', 'national-scholarship'）
    """
    norm_name = _normalize_skill_id(skill_name)
    skill_dir = SUBSKILLS_DIR / norm_name
    if not skill_dir.exists():
        skill_dir = SUBSKILLS_DIR / norm_name.replace("-", "_")

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return {"error": f"找不到赛道 '{skill_name}' 的 SKILL.md 文档"}

    content = skill_md.read_text(encoding="utf-8")

    # 尝试提取信息采集清单章节与注意事项
    sections = {}
    current_sec = "overview"
    sec_lines: List[str] = []

    for line in content.splitlines():
        if line.startswith("#"):
            if sec_lines:
                sections[current_sec] = "\n".join(sec_lines).strip()
                sec_lines = []
            current_sec = line.strip("# ").strip()
        else:
            sec_lines.append(line)
    if sec_lines:
        sections[current_sec] = "\n".join(sec_lines).strip()

    # 挑选出关键核心小节
    relevant_sections = {}
    for sec_title, sec_content in sections.items():
        if any(k in sec_title for k in ["信息采集", "采集清单", "必填", "格式规范", "评审", "避坑", "输入数据", "字段"]):
            relevant_sections[sec_title] = sec_content[:3000]

    return {
        "skill_name": norm_name,
        "file_path": str(skill_md),
        "total_length": len(content),
        "key_sections": relevant_sections or {"full_preview": content[:4000]},
        "summary": f"已成功提取 {norm_name} 的材料采集与撰写规范，请根据清单向用户收集真实数据。"
    }


@server.tool()
def list_school_templates() -> Dict[str, Any]:
    """
    列出当前内置支持的高校特定排版样式模板。
    支持清华、北大、浙大、武大等高校的标准页边距、字号和红头格式。
    """
    templates = []
    if SCHOOLS_DIR.exists():
        for f in sorted(SCHOOLS_DIR.glob("template_*.json")):
            try:
                with open(f, "r", encoding="utf-8") as tf:
                    cfg = json.load(tf)
                templates.append({
                    "id": f.stem.replace("template_", ""),
                    "name": cfg.get("school_name", f.stem),
                    "font_family": cfg.get("font_body", "仿宋_GB2312"),
                    "line_spacing": cfg.get("line_spacing", 1.5),
                    "file": f.name,
                })
            except Exception:
                templates.append({"id": f.stem.replace("template_", ""), "file": f.name})
    return {
        "templates": templates,
        "usage": "在调用 generate_student_doc 时，可传入 school 参数（如 'pku', 'tsinghua', 'zju', 'whu' 或 'default'）。"
    }


@server.tool()
def generate_student_doc(
    skill_name: str,
    data: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
    school: Optional[str] = None,
    demo: bool = False,
) -> Dict[str, Any]:
    """
    根据采集到的结构化申报数据，自动执行本地渲染脚本，生成一份标准规范的 Word (.docx) 文档。

    参数:
      skill_name: 赛道名称（如 'innovation-research', 'challenge-cup' 等）
      data: 申报书数据字典（若 demo=True 则此项可为空）
      output_path: 生成的目标 .docx 绝对路径（可选；默认自动生成在 outputs 或 /tmp 下）
      school: 学校版式模板（如 'tsinghua', 'pku', 'whu', 'zju', 'default'）
      demo: 是否使用内置示例数据快速体验生成
    """
    norm_name = _normalize_skill_id(skill_name)
    skill_dir = SUBSKILLS_DIR / norm_name
    if not skill_dir.exists():
        skill_dir = SUBSKILLS_DIR / norm_name.replace("-", "_")

    build_py = skill_dir / "build.py"
    if not build_py.exists():
        return {"error": f"赛道 '{skill_name}' 暂未找到 build.py 构建脚本: {build_py}"}

    if not output_path:
        out_dir = PROJECT_DIR / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"{norm_name}_申报书.docx")
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, str(build_py), "--out", output_path]
    if school:
        cmd.extend(["--school", school])

    temp_json = None
    if demo:
        cmd.append("--demo")
    elif data:
        tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, tf, ensure_ascii=False, indent=2)
        tf.close()
        temp_json = tf.name
        cmd.extend(["--data", temp_json])
    else:
        return {"error": "必须提供 data 参数或设置 demo=True"}

    try:
        res = subprocess.run(cmd, cwd=str(PROJECT_DIR), capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            return {
                "success": False,
                "error": f"生成失败 (exit code {res.returncode})",
                "stdout": res.stdout,
                "stderr": res.stderr,
            }

        out_file = Path(output_path)
        return {
            "success": True,
            "output_path": str(out_file.resolve()),
            "file_size_bytes": out_file.stat().st_size if out_file.exists() else 0,
            "message": f"Word 文档已成功生成！位于: {output_path}",
            "details": res.stdout.strip(),
        }
    except Exception as err:
        return {"success": False, "error": str(err)}
    finally:
        if temp_json and os.path.exists(temp_json):
            try:
                os.remove(temp_json)
            except OSError:
                pass


@server.tool()
def simulate_student_review(
    skill_name: str,
    text: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    对学生的申报文本或申报数据执行评审模拟与打分。
    输出各维度得分、总体等级、评委意见、一票否决预警、查重预检及具体改进建议。

    参数:
      skill_name: 赛道名称（如 'innovation_research', 'challenge_cup' 等）
      text: 申报正文文本（可选）
      data: 申报结构化数据字典（可选）
    """
    # 评审模拟器内部使用下划线格式
    norm_name = _normalize_skill_id(skill_name).replace("-", "_")
    rev_py = UTILS_DIR / "review_simulator.py"
    if not rev_py.exists():
        return {"error": "未找到 review_simulator.py 工具"}

    cmd = [sys.executable, str(rev_py), "--skill", norm_name, "--json"]
    temp_json = None

    if data:
        tf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, tf, ensure_ascii=False, indent=2)
        tf.close()
        temp_json = tf.name
        cmd.extend(["--data", temp_json])

    if text:
        cmd.extend(["--text", text])

    if not data and not text:
        cmd.extend(["--text", "申报草稿文本检测与评估"])

    try:
        res = subprocess.run(cmd, cwd=str(PROJECT_DIR), capture_output=True, text=True, timeout=30)
        # 优先解析 stdout 的 json
        out_text = res.stdout.strip()
        try:
            result_data = json.loads(out_text)
            return {
                "success": True,
                "review_result": result_data,
            }
        except json.JSONDecodeError:
            return {
                "success": res.returncode == 0,
                "raw_output": out_text,
                "stderr": res.stderr,
            }
    except Exception as err:
        return {"success": False, "error": str(err)}
    finally:
        if temp_json and os.path.exists(temp_json):
            try:
                os.remove(temp_json)
            except OSError:
                pass


if __name__ == "__main__":
    server.run()
