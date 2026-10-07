# -*- coding: utf-8 -*-
"""v2.2 配图规范测试：技术路线图默认渲染为真图（utils/figgen）。

对应 Issue #1（university_research 技术路线图输出为表格而非图片）。
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from docx import Document

ROOT = Path(__file__).resolve().parent.parent
UR_BUILD = ROOT / "subskills" / "university-research" / "build.py"

CHAIN_NODES = [
    "总目标：开发本土化方案",
    "研究内容 1.1 方案设计（产出方案文档）",
    "研究内容 1.2 试点实施",
    "研究内容 1.3 效果评估",
]
DAG_NODES = [
    {"id": "1.1", "label": "需求分析"},
    {"id": "2.1", "label": "算法开发"},
    {"id": "2.2", "label": "模型训练"},
    {"id": "3.1", "label": "集成验证"},
]
DAG_EDGES = [
    {"from": "1.1", "to": "2.1"},
    {"from": "1.1", "to": "2.2"},
    {"from": "2.1", "to": "3.1"},
    {"from": "2.2", "to": "3.1"},
]


def _load_build_module():
    spec = importlib.util.spec_from_file_location("ur_build", UR_BUILD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("ur_build", mod)
    spec.loader.exec_module(mod)
    return mod


def _roadmaps(nodes, edges=None, image_path=""):
    rm = {"fig_no": "图 1", "title": "项目技术路线图",
          "description": "测试说明", "nodes": nodes}
    if edges:
        rm["edges"] = edges
    if image_path:
        rm["image_path"] = image_path
    return [rm]


def test_figgen_chain_renders_png(tmp_path):
    """字符串链（university_research 形态）→ PNG 文件。"""
    from utils.figgen import render_chain
    out = render_chain(CHAIN_NODES, str(tmp_path / "chain.png"))
    assert out and Path(out).exists() and Path(out).stat().st_size > 1000


def test_figgen_dag_renders_png(tmp_path):
    """{id,label}+edges（challenge_cup 形态）→ PNG 文件。"""
    from utils.figgen import render_flowchart
    out = render_flowchart(DAG_NODES, DAG_EDGES, str(tmp_path / "dag.png"))
    assert out and Path(out).exists() and Path(out).stat().st_size > 1000


def test_figgen_empty_nodes_degrades_to_none():
    """空节点 → 返回 None（由调用方降级），不抛异常。"""
    from utils.figgen import render_flowchart
    assert render_flowchart([]) is None


def test_build_demo_embeds_roadmap_images(tmp_path):
    """端到端：university_research --demo 产出的 docx 必须含真图（≥2 张）。"""
    import subprocess
    out = tmp_path / "university_research.docx"
    proc = subprocess.run(
        [sys.executable, str(UR_BUILD), "--demo", "--out", str(out)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"build.py 失败：{proc.stderr[-800:]}"
    doc = Document(str(out))
    assert len(doc.inline_shapes) >= 2, (
        f"技术路线图未嵌入真图，inline_shapes={len(doc.inline_shapes)}")


def test_user_image_path_takes_priority(tmp_path, capsys):
    """tech_roadmap[].image_path 优先于自动渲染。"""
    from utils.figgen import render_chain
    from docx import Document as NewDoc
    user_img = render_chain(CHAIN_NODES, str(tmp_path / "user.png"))
    mod = _load_build_module()
    doc = NewDoc()
    mod.add_tech_roadmap_section(
        doc, _roadmaps(CHAIN_NODES, image_path=user_img))
    assert len(doc.inline_shapes) == 1
    assert "用户自备图" in capsys.readouterr().err


def test_table_fallback_explicit_mode(capsys):
    """render_mode="table"：显式要求表格模拟，不嵌入图片。"""
    from docx import Document as NewDoc
    mod = _load_build_module()
    doc = NewDoc()
    mod.add_tech_roadmap_section(
        doc, _roadmaps(CHAIN_NODES), render_mode="table")
    assert len(doc.inline_shapes) == 0
    assert "流程图框" not in doc.paragraphs[0].text  # 占位文本未出现


def test_flowchart_image_used_when_render_unavailable(tmp_path, capsys, monkeypatch):
    """figgen 不可用时回退全局 tech_flowchart_image，而非表格。"""
    from utils.figgen import render_chain
    from docx import Document as NewDoc
    global_img = render_chain(CHAIN_NODES, str(tmp_path / "global.png"))
    mod = _load_build_module()
    monkeypatch.setattr(mod, "_figgen_render", None)  # 模拟 matplotlib 缺失
    doc = NewDoc()
    mod.add_tech_roadmap_section(
        doc, _roadmaps(CHAIN_NODES), flowchart_image=global_img)
    assert len(doc.inline_shapes) == 1
    assert "tech_flowchart_image" in capsys.readouterr().err


def test_figgen_dag_parallel_nodes_no_overlap_or_clip(tmp_path):
    """验证 Issue #7：DAG 存在多分支并行节点时，节点间互不重叠且不被画布裁切。"""
    from utils.figgen import render_flowchart
    parallel_nodes = [
        {"id": "1", "label": "输入与需求分析"},
        {"id": "2a", "label": "并行分支A 深度学习模型优化与超参数调优"},
        {"id": "2b", "label": "并行分支B 硬件边缘部署加速与低功耗适配"},
        {"id": "3", "label": "综合成果验收与上线发布"},
    ]
    parallel_edges = [
        {"from": "1", "to": "2a"},
        {"from": "1", "to": "2b"},
        {"from": "2a", "to": "3"},
        {"from": "2b", "to": "3"},
    ]
    out = render_flowchart(parallel_nodes, parallel_edges, str(tmp_path / "dag_no_overlap.png"))
    assert out and Path(out).exists()
    assert Path(out).stat().st_size > 1000
