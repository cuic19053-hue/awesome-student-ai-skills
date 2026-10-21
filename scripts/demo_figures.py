#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""申报书配图生成器 —— 六类标准图，统一配色。

输出到 build/figures/*.png，供 docx 嵌入与 HTML 展示页复用。
所有图 300dpi，中文字体 PingFang SC / SimHei fallback。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Wedge
from matplotlib.lines import Line2D

# ---- 统一配色 token ----
INK = "#111827"
GREY = "#6B7280"
GRID = "#E5E7EB"
BLUE, BLUEF = "#1D4ED8", "#DBEAFE"
AMBER, AMBERF = "#B45309", "#FDE68A"
GREEN, GREENF = "#15803D", "#BBF7D0"
RED, REDF = "#B91C1C", "#FEE2E2"
PURPLE, PURPLEF = "#6D28D9", "#EDE9FE"

PALETTE = [BLUE, AMBER, GREEN, PURPLE, "#0891B2", "#DB2777"]

OUT = Path(__file__).resolve().parent.parent / "build" / "figures"


def setup_font() -> str:
    """挑一个能显示中文的字体，找不到就报错退出（不产出豆腐块）。"""
    candidates = ("PingFang SC", "Heiti SC", "Songti SC", "SimHei",
                  "Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans CN",
                  "Arial Unicode MS")
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return name
    raise SystemExit("没有可用中文字体，拒绝产出乱码图")


def _save(fig, name: str) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    fig.savefig(p, dpi=300, bbox_inches="tight", facecolor="white", pad_inches=0.15)
    plt.close(fig)
    print(f"  ✓ {name}")
    return str(p)


# ---------------------------------------------------------------- 1. 技术路线图
def tech_roadmap(name="01_tech_roadmap.png"):
    """四阶段技术路线图，横向分组 + 纵向流程。"""
    stages = [
        ("第一阶段\n需求与建模", ["文献调研\n与痛点定位", "无人机\n动力学建模"], BLUE, BLUEF),
        ("第二阶段\n算法设计", ["改进 A* 路径\n规划算法", "动态障碍\n规避策略"], AMBER, AMBERF),
        ("第三阶段\n仿真验证", ["Gazebo 仿真\n平台搭建", "多场景\n对比实验"], GREEN, GREENF),
        ("第四阶段\n实机测试", ["样机集成\n与调参", "成果整理\n与论文撰写"], PURPLE, PURPLEF),
    ]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.set_xlim(0, 4 * 2.5)
    ax.set_ylim(0, 3.6)
    ax.axis("off")

    for i, (title, items, ec, fc) in enumerate(stages):
        x0 = i * 2.5 + 0.12
        ax.add_patch(FancyBboxPatch(
            (x0, 3.05), 2.26, 0.42,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            fc=ec, ec=ec, lw=0, zorder=4))
        ax.text(x0 + 1.13, 3.26, title, ha="center", va="center",
                fontsize=10, color="white", fontweight="bold", zorder=5,
                linespacing=1.35)

        for j, it in enumerate(items):
            y = 2.15 - j * 1.05
            ax.add_patch(FancyBboxPatch(
                (x0 + 0.06, y - 0.4), 2.14, 0.8,
                boxstyle="round,pad=0.02,rounding_size=0.12",
                fc=fc, ec=ec, lw=1.3, zorder=3))
            ax.text(x0 + 1.13, y, it, ha="center", va="center",
                    fontsize=9.2, color=INK, zorder=4, linespacing=1.45)

        if i < 3:
            ax.add_patch(FancyArrowPatch(
                (x0 + 2.26, 3.26), (x0 + 2.56, 3.26),
                arrowstyle="-|>", mutation_scale=16, color=GREY, lw=1.6,
                zorder=2))

    # 阶段内部纵向箭头
    for i in range(4):
        x0 = i * 2.5 + 0.12
        ax.add_patch(FancyArrowPatch(
            (x0 + 1.13, 1.75), (x0 + 1.13, 1.15),
            arrowstyle="-|>", mutation_scale=13, color=GREY, lw=1.3, zorder=2))

    ax.text(0, 0.12, "总目标：构建面向复杂环境的无人机自主路径规划系统，"
                     "在动态障碍场景下路径长度缩短 15% 以上",
            ha="left", va="bottom", fontsize=9, color=GREY, style="italic")
    return _save(fig, name)


# ---------------------------------------------------------------- 2. 甘特图
def gantt(name="02_gantt.png"):
    tasks = [
        ("文献调研与需求分析", 0, 2, BLUE),
        ("无人机动力学建模", 1, 2, BLUE),
        ("改进 A* 算法设计", 3, 3, AMBER),
        ("动态避障策略实现", 4, 2, AMBER),
        ("仿真平台搭建", 5, 2, GREEN),
        ("多场景对比实验", 7, 3, GREEN),
        ("样机集成与调参", 9, 2, PURPLE),
        ("论文撰写与成果整理", 10, 2, PURPLE),
    ]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    labels = [t[0] for t in tasks][::-1]
    for idx, (label, start, dur, color) in enumerate(tasks[::-1]):
        ax.barh(idx, dur, left=start, height=0.52, color=color,
                alpha=0.88, edgecolor="white", linewidth=1.2, zorder=3)
        ax.text(start + dur + 0.12, idx, f"{dur} 月", va="center",
                fontsize=8.5, color=GREY, zorder=4)

    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9.5, color=INK)
    ax.set_xticks(range(0, 13, 2))
    ax.set_xticklabels([f"M{i}" for i in range(0, 13, 2)], fontsize=9, color=GREY)
    ax.set_xlim(0, 13.4)
    ax.set_xlabel("项目周期（月）", fontsize=9.5, color=GREY, labelpad=8)
    ax.grid(axis="x", color=GRID, linewidth=0.9, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)

    # 里程碑
    for m, txt in [(6, "中期检查"), (12, "结题验收")]:
        ax.axvline(m, color=RED, ls=(0, (4, 3)), lw=1.2, zorder=2)
        ax.text(m, len(labels) - 0.35, txt, fontsize=8.5, color=RED,
                ha="center", va="bottom")
    return _save(fig, name)


# ---------------------------------------------------------------- 3. 经费预算环形图
def budget_donut(name="03_budget.png"):
    items = [("设备与材料费", 42), ("测试与加工费", 20),
             ("差旅与调研费", 15), ("文献与资料费", 8),
             ("专家咨询费", 7), ("其他支出", 8)]
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    vals = [v for _, v in items]
    colors = PALETTE[:len(items)]
    wedges, _ = ax.pie(
        vals, colors=colors, startangle=90, counterclock=False,
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2.2))

    total = sum(vals)
    ax.text(0, 0.12, "3.0", ha="center", va="center",
            fontsize=26, fontweight="bold", color=INK)
    ax.text(0, -0.18, "万元", ha="center", va="center",
            fontsize=11, color=INK)
    ax.text(0, -0.42, "合计申请经费", ha="center", va="center",
            fontsize=8.8, color=GREY)

    ax.legend(wedges, [f"{k}  {v}%" for k, v in items],
              loc="center left", bbox_to_anchor=(1.02, 0.5),
              frameon=False, fontsize=9.2, labelcolor=INK,
              handlelength=1.1, handleheight=1.1, labelspacing=1.0)
    ax.set_aspect("equal")
    return _save(fig, name)


# ---------------------------------------------------------------- 4. 方案对比柱状图
def algo_compare(name="04_compare.png"):
    metrics = ["路径长度\n(m)", "规划耗时\n(ms)", "避障成功率\n(%)", "能耗\n(kJ)"]
    traditional = [128.4, 420, 72.5, 18.6]
    ours = [106.2, 168, 94.3, 15.2]
    # 归一化到同一量纲做对比（各指标除以传统方案）
    norm_t = [100, 100, 72.5, 100]
    norm_o = [round(106.2 / 128.4 * 100, 1), round(168 / 420 * 100, 1), 94.3,
              round(15.2 / 18.6 * 100, 1)]

    x = range(len(metrics))
    w = 0.36
    fig, ax = plt.subplots(figsize=(9, 4.3))
    b1 = ax.bar([i - w / 2 for i in x], norm_t, w, label="传统 A* 算法",
                color="#94A3B8", edgecolor="white", linewidth=1.2, zorder=3)
    b2 = ax.bar([i + w / 2 for i in x], norm_o, w, label="本项目改进算法",
                color=BLUE, edgecolor="white", linewidth=1.2, zorder=3)

    for bars, vals in ((b1, traditional), (b2, ours)):
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2.5,
                    f"{v}", ha="center", va="bottom", fontsize=8.6,
                    color=INK, fontweight="medium")

    ax.set_xticks(list(x))
    ax.set_xticklabels(metrics, fontsize=9.2, color=INK)
    ax.set_ylabel("相对基准值 (%)", fontsize=9.5, color=GREY)
    ax.set_ylim(0, 122)
    ax.grid(axis="y", color=GRID, linewidth=0.9, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0, colors=GREY)
    ax.legend(frameon=False, fontsize=9.5, loc="upper center",
              ncol=2, bbox_to_anchor=(0.5, 1.14), labelcolor=INK)

    ax.annotate("路径缩短 17.3%\n耗时降低 60%",
                xy=(0.18, 106), xytext=(1.1, 118),
                fontsize=8.8, color=GREEN, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.2))
    return _save(fig, name)


# ---------------------------------------------------------------- 5. SWOT 矩阵
def swot(name="05_swot.png"):
    blocks = [
        ("S 优势 Strengths", BLUE, BLUEF,
         ["• 算法在动态障碍场景下成功率 94.3%", "• 团队 3 人具备 ROS 与 SLAM 基础",
          "• 已有实验室无人机平台可复用"]),
        ("W 劣势 Weaknesses", AMBER, AMBERF,
         ["• 实机测试场地受限，样本量不足", "• 长续航电池成本较高",
          "• 缺乏商业化落地经验"]),
        ("O 机会 Opportunities", GREEN, GREENF,
         ["• 低空经济政策明确支持", "• 物流配送无人机需求快速增长",
          "• 校地合作可提供测试场景"]),
        ("T 威胁 Threats", RED, REDF,
         ["• 头部厂商已有成熟避障方案", "• 同类开源项目迭代速度快",
          "• 核心元器件供货周期波动"]),
    ]
    fig, ax = plt.subplots(figsize=(9.6, 6.4))
    ax.set_xlim(0, 2)
    ax.set_ylim(0, 2)
    ax.axis("off")
    pos = [(0, 1), (1, 1), (0, 0), (1, 0)]
    for (x0, y0), (title, ec, fc, items) in zip(pos, blocks):
        ax.add_patch(Rectangle((x0 + 0.02, y0 + 0.02), 0.96, 0.96,
                               fc=fc, ec=ec, lw=1.6, zorder=2))
        ax.add_patch(Rectangle((x0 + 0.02, y0 + 0.82), 0.96, 0.16,
                               fc=ec, ec=ec, lw=0, zorder=3))
        ax.text(x0 + 0.5, y0 + 0.90, title, ha="center", va="center",
                fontsize=10.5, color="white", fontweight="bold", zorder=4)
        for k, it in enumerate(items):
            ax.text(x0 + 0.07, y0 + 0.70 - k * 0.20, it,
                    ha="left", va="top", fontsize=8.8, color=INK,
                    zorder=4, wrap=True)
    ax.add_patch(Rectangle((0.02, 0.02), 1.96, 1.96, fc="none",
                           ec=GREY, lw=1.4, zorder=5))
    return _save(fig, name)


# ---------------------------------------------------------------- 6. 创新点逻辑链
def innovation_chain(name="06_innovation.png"):
    steps = [
        ("痛点", "复杂环境下\n静态规划失效", "#B91C1C", REDF),
        ("现有方案不足", "A* 无法响应\n动态障碍", "#B45309", AMBERF),
        ("核心创新", "滚动时域 +\n动态代价函数", BLUE, BLUEF),
        ("验证指标", "成功率 94.3%\n路径 -17.3%", GREEN, GREENF),
        ("成果", "论文 1 篇\n样机 1 台", PURPLE, PURPLEF),
    ]
    fig, ax = plt.subplots(figsize=(12, 3.0))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 2.2)
    ax.axis("off")
    for i, (tag, body, ec, fc) in enumerate(steps):
        x = i * 2.36 + 0.1
        ax.add_patch(FancyBboxPatch((x, 0.95), 2.0, 0.52,
                                    boxstyle="round,pad=0.02,rounding_size=0.10",
                                    fc=ec, ec=ec, lw=0, zorder=3))
        ax.text(x + 1.0, 1.21, tag, ha="center", va="center",
                fontsize=10, color="white", fontweight="bold", zorder=4)

        ax.add_patch(FancyBboxPatch((x, 0.12), 2.0, 0.68,
                                    boxstyle="round,pad=0.02,rounding_size=0.10",
                                    fc=fc, ec=ec, lw=1.3, zorder=3))
        ax.text(x + 1.0, 0.46, body, ha="center", va="center",
                fontsize=8.8, color=INK, zorder=4, linespacing=1.5)

        if i < 4:
            ax.add_patch(FancyArrowPatch((x + 2.03, 0.8), (x + 2.33, 0.8),
                                         arrowstyle="-|>", mutation_scale=15,
                                         color=GREY, lw=1.5, zorder=2))
    return _save(fig, name)


def main():
    font = setup_font()
    print(f"中文字体：{font}")
    print(f"输出目录：{OUT}")
    for fn in (tech_roadmap, gantt, budget_donut, algo_compare, swot, innovation_chain):
        fn()
    print("全部完成")


if __name__ == "__main__":
    main()
