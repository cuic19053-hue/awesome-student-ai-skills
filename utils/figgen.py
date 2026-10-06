#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""figgen —— 申报书数据图统一渲染模块（v2.2 配图规范的运行时实现）。

设计原则（见 subskills/challenge_cup/SKILL.md 第 27 章配图规范）：
- 数据图一律代码渲染，禁止 AI 文生图（中文乱码 / 数字编造 / 图文不符三大硬伤）；
- 中文字体 fallback 链，覆盖 Windows / macOS / Linux；
- 全部赛道共享统一配色 token 与尺寸规范。

当前提供：
- render_flowchart(nodes, edges, out_path)：技术路线图 / 研究内容关系图。
  兼容两种数据形态：
  A) nodes 为字符串列表 —— 线性链条，按输入顺序自上而下连接
     （如 university_research 的 tech_roadmap[*].nodes）；
  B) nodes 为 [{id, label}] 且可选 edges [{from, to}] —— 按 DAG 分层布局
     （如 challenge_cup 的 tech_roadmap[*]）。

失败语义：渲染失败（未安装 matplotlib、无可用中文字体、布局异常等）一律
返回 None 并向 stderr 打印原因，由调用方自行降级（如回退为 Word 表格模拟），
绝不抛出异常中断文档生成。
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---- 统一配色 token（与 challenge_cup v2.2 §27.2 一致） ----
INK = "#111827"
GREY = "#4B5563"
BLUE, BLUEF = "#1E40AF", "#DBEAFE"
RED, REDF = "#B91C1C", "#FECACA"
AMBER, AMBERF = "#B45309", "#FDE68A"
GREEN, GREENF = "#15803D", "#BBF7D0"
STAGE_COLORS = [(BLUE, BLUEF), (AMBER, AMBERF), (GREEN, GREENF)]

# 中文字体 fallback 链（按优先级；一个都没有则视为无法渲染，交由调用方降级）
FONT_CANDIDATES = (
    "SimHei", "Microsoft YaHei", "Noto Sans CJK SC",
    "PingFang SC", "Heiti SC", "Arial Unicode MS",
)

_DEFAULT_DPI = 200


def _load_plt() -> Optional[Any]:
    """懒加载 matplotlib 并配置中文字体。

    返回 pyplot 模块；未安装 matplotlib 或找不到任何中文字体时返回 None
    （找不到中文字体时渲染出的是豆腐块，宁可降级也不产出废图）。
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager

        available = {f.name for f in font_manager.fontManager.ttflist}
        for name in FONT_CANDIDATES:
            if name in available:
                plt.rcParams["font.family"] = [name]
                break
        else:
            print(
                "⚠️ figgen：未找到可用中文字体（候选："
                + "、".join(FONT_CANDIDATES) + "），放弃渲染以免产出乱码图",
                file=sys.stderr,
            )
            return None
        plt.rcParams["axes.unicode_minus"] = False
        return plt
    except Exception as exc:  # matplotlib 未安装等
        print(f"⚠️ figgen：matplotlib 不可用（{exc}），放弃渲染", file=sys.stderr)
        return None


def _normalize_graph(
    nodes: Sequence[Any],
    edges: Optional[Sequence[Any]],
) -> Tuple[List[Dict[str, str]], List[Tuple[str, str]]]:
    """归一化节点/边为 ([{id,label}], [(from,to)])。

    nodes 为字符串时按输入顺序连成线性链条；为字典时取 id/label，
    edges 缺省时同样按输入顺序连成链。
    """
    norm: List[Dict[str, str]] = []
    for i, n in enumerate(nodes):
        if isinstance(n, dict):
            norm.append({
                "id": str(n.get("id", f"n{i}")),
                "label": str(n.get("label", "")),
            })
        else:
            norm.append({"id": f"n{i}", "label": str(n)})

    parsed_edges: List[Tuple[str, str]] = []
    for e in edges or []:
        if isinstance(e, dict) and "from" in e and "to" in e:
            parsed_edges.append((str(e["from"]), str(e["to"])))
    if not parsed_edges:
        parsed_edges = [
            (norm[i]["id"], norm[i + 1]["id"]) for i in range(len(norm) - 1)
        ]
    return norm, parsed_edges


def _assign_levels(
    nodes: List[Dict[str, str]],
    edges: List[Tuple[str, str]],
) -> Dict[str, int]:
    """最长路径分层（DAG）；带环保护，成环边按同层处理。"""
    preds: Dict[str, List[str]] = {n["id"]: [] for n in nodes}
    known = set(preds)
    for a, b in edges:
        if a in known and b in known:
            preds[b].append(a)

    level: Dict[str, int] = {}

    def _level(nid: str, stack: Tuple[str, ...] = ()) -> int:
        if nid in level:
            return level[nid]
        if nid in stack:  # 环保护
            return 0
        ps = preds.get(nid, [])
        lvl = 0 if not ps else 1 + max(_level(p, stack + (nid,)) for p in ps)
        level[nid] = lvl
        return lvl

    for n in nodes:
        _level(n["id"])
    return level


def _wrap(label: str, width: int) -> str:
    """CJK 友好换行：按字符数折行（textwrap 按字符计数，中英文混排可用）。"""
    return "\n".join(
        textwrap.fill(seg, width=width) for seg in label.split("\n")
    )


def render_flowchart(
    nodes: Sequence[Any],
    edges: Optional[Sequence[Any]] = None,
    out_path: Optional[str] = None,
    dpi: int = _DEFAULT_DPI,
) -> Optional[str]:
    """渲染技术路线图 / 研究内容关系图为 PNG。

    参数：
        nodes: 字符串列表（线性链）或 [{id,label}]（DAG，配 edges）。
        edges: [{from,to}]，缺省时按输入顺序连线。
        out_path: PNG 输出路径；缺省写入临时目录。
        dpi: 输出分辨率，默认 200。

    返回：PNG 绝对路径；失败返回 None（调用方降级，如回退表格模拟）。
    """
    if not nodes:
        return None
    plt = _load_plt()
    if plt is None:
        return None
    try:
        from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

        norm, parsed_edges = _normalize_graph(nodes, edges)
        levels = _assign_levels(norm, parsed_edges)
        if max(levels.values()) == 0 and len(norm) > 1:
            # 全同层（如纯环）：退化为按输入顺序纵向排列
            for i, n in enumerate(norm):
                levels[n["id"]] = i

        by_row: Dict[int, List[Dict[str, str]]] = {}
        for n in norm:
            by_row.setdefault(levels[n["id"]], []).append(n)
        rows = [by_row[r] for r in sorted(by_row)]

        # 阶段分组：点分 id 前缀优先，否则按行号；按首次出现顺序稳定配色
        def group_key(n: Dict[str, str], row: int) -> str:
            return n["id"].split(".", 1)[0] if "." in n["id"] else f"row{row}"

        BOX_W, BOX_H = 6.0, 1.15
        GAP = 0.85
        n_rows = len(rows)
        fig_h = n_rows * (BOX_H + GAP) + 0.6
        fig, ax = plt.subplots(figsize=(7.2, fig_h))
        ax.set_xlim(-4.6, 4.6)
        ax.set_ylim(-0.3, fig_h - 0.3)
        ax.axis("off")

        centers: Dict[str, Tuple[float, float]] = {}
        seen_groups: Dict[str, int] = {}
        for r, row in enumerate(rows):
            y = fig_h - 0.6 - r * (BOX_H + GAP) - BOX_H / 2
            span = 8.6 / len(row)
            for c, n in enumerate(row):
                x = -3.8 + span * (c + 0.5) if len(row) > 1 else 0.0
                gk = group_key(n, r)
                if gk not in seen_groups:
                    seen_groups[gk] = len(seen_groups)
                ec, fc = STAGE_COLORS[seen_groups[gk] % len(STAGE_COLORS)]
                wrap_w = 16 if len(row) == 1 else max(8, int(15 * span / 8.6))
                ax.add_patch(FancyBboxPatch(
                    (x - BOX_W / 2, y - BOX_H / 2), BOX_W, BOX_H,
                    boxstyle="round,pad=0.06,rounding_size=0.10",
                    fc=fc, ec=ec, lw=1.4, zorder=3))
                ax.text(x, y, _wrap(n["label"], wrap_w), ha="center",
                        va="center", fontsize=10.5, color=INK, zorder=4,
                        linespacing=1.3)
                centers[n["id"]] = (x, y)

        for a, b in parsed_edges:
            if a not in centers or b not in centers:
                continue
            (x1, y1), (x2, y2) = centers[a], centers[b]
            ax.add_patch(FancyArrowPatch(
                (x1, y1 - BOX_H / 2), (x2, y2 + BOX_H / 2),
                arrowstyle="-|>", mutation_scale=15, color=GREY, lw=1.6,
                zorder=2))

        if out_path is None:
            fd, out_path = tempfile.mkstemp(suffix=".png", prefix="figgen_")
            os.close(fd)
        out_path = os.path.abspath(out_path)
        fig.savefig(out_path, dpi=dpi, bbox_inches="tight",
                    facecolor="white", pad_inches=0.12)
        plt.close(fig)
        return out_path
    except Exception as exc:
        print(f"⚠️ figgen：流程图渲染失败（{exc}），回退为调用方默认行为",
              file=sys.stderr)
        return None


def render_chain(
    nodes: Sequence[str],
    out_path: Optional[str] = None,
    dpi: int = _DEFAULT_DPI,
) -> Optional[str]:
    """render_flowchart 的线性链条便捷封装（nodes 为字符串列表）。"""
    return render_flowchart(list(nodes), None, out_path, dpi)
