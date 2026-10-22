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


def ink_() -> str:
    return INK


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
    fig, ax = plt.subplots(figsize=(7.4, 4.0))
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


# ---------------------------------------------------------------- 7. 商业模式画布
def business_canvas(name="07_canvas.png"):
    """标准九宫格商业模式画布。"""
    blocks = {
        "kp": (0.0, 0.62, 0.20, 0.38, "重要伙伴 KP",
               ["高校智能制造实验室", "本地农机合作社", "传感器供应商"]),
        "ka": (0.20, 0.62, 0.16, 0.19, "关键业务 KA",
               ["作物长势模型训练", "无人机巡田作业"]),
        "kr": (0.20, 0.43, 0.16, 0.19, "核心资源 KR",
               ["多光谱影像数据集", "自研识别算法"]),
        "vp": (0.36, 0.43, 0.20, 0.57, "价值主张 VP",
               ["按亩计费的巡田服务", "病虫害预警准确率 91%",
                "较人工巡查成本下降 60%"]),
        "cr": (0.56, 0.62, 0.16, 0.19, "客户关系 CR",
               ["合作社驻点服务", "微信小程序自助下单"]),
        "ch": (0.56, 0.43, 0.16, 0.19, "渠道通路 CH",
               ["县级农技推广站", "农机经销商代销"]),
        "cs": (0.72, 0.62, 0.20, 0.38, "客户细分 CS",
               ["50—500 亩规模种植户", "农业合作社", "县域农服公司"]),
        "cost": (0.0, 0.0, 0.50, 0.38, "成本结构 Cost",
                 ["无人机折旧与维护", "飞手人力成本", "算力与数据标注"]),
        "rev": (0.50, 0.0, 0.42, 0.38, "收入来源 Revenue",
                ["巡田服务费 8 元/亩·次", "植保方案订阅 1200 元/年",
                 "农资集采佣金 3%"]),
    }
    fills = {"kp": (BLUE, BLUEF), "ka": (BLUE, BLUEF), "kr": (BLUE, BLUEF),
             "vp": (AMBER, AMBERF), "cr": (GREEN, GREENF), "ch": (GREEN, GREENF),
             "cs": (GREEN, GREENF), "cost": (PURPLE, PURPLEF), "rev": (PURPLE, PURPLEF)}

    fig, ax = plt.subplots(figsize=(13.6, 5.4))
    ax.set_xlim(-0.01, 0.93)
    ax.set_ylim(-0.01, 1.01)
    ax.axis("off")
    for key, (x, y, w, h, title, items) in blocks.items():
        ec, fc = fills[key]
        ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=1.4, zorder=2))
        ax.add_patch(Rectangle((x, y + h - 0.055), w, 0.055,
                               fc=ec, ec=ec, lw=0, zorder=3))
        ax.text(x + w / 2, y + h - 0.027, title, ha="center", va="center",
                fontsize=8.6, color="white", fontweight="bold", zorder=4)
        for k, it in enumerate(items):
            ax.text(x + 0.008, y + h - 0.085 - k * 0.052, "· " + it,
                    ha="left", va="top", fontsize=7.4, color=INK, zorder=4)
    return _save(fig, name)


# ---------------------------------------------------------------- 8. 能力雷达图
def capability_radar(name="08_radar.png"):
    labels = ["专业成绩", "科研训练", "竞赛获奖", "社会实践", "学生工作", "外语能力"]
    me = [92, 78, 88, 82, 90, 75]
    avg = [80, 62, 55, 70, 68, 72]

    n = len(labels)
    angles = [i / n * 2 * 3.141592653589793 for i in range(n)]
    angles += angles[:1]
    me_c = me + me[:1]
    avg_c = avg + avg[:1]

    fig, ax = plt.subplots(figsize=(7.2, 4.9), subplot_kw=dict(polar=True))
    ax.set_theta_offset(3.141592653589793 / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9.6, color=INK)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=7.4, color=GREY)
    ax.grid(color=GRID, linewidth=0.9)

    ax.plot(angles, avg_c, color="#94A3B8", linewidth=1.6, label="同专业平均水平")
    ax.fill(angles, avg_c, color="#94A3B8", alpha=0.14)
    ax.plot(angles, me_c, color=BLUE, linewidth=2.0, label="本人")
    ax.fill(angles, me_c, color=BLUE, alpha=0.20)

    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.16), ncol=2,
              frameon=False, fontsize=9, labelcolor=INK)
    return _save(fig, name)


# ---------------------------------------------------------------- 9. 成果时间轴
def achievement_timeline(name="09_timeline.png"):
    events = [
        ("2023.09", "入学，专业排名 3/126", BLUE),
        ("2024.05", "校级大创立项（负责人）", BLUE),
        ("2024.11", "全国大学生数学建模竞赛省一", AMBER),
        ("2025.04", "SCI 四区论文 1 篇（二作）", GREEN),
        ("2025.08", "超聚变黑客松全国 35 强", AMBER),
        ("2025.12", "国家奖学金", RED),
        ("2026.06", "保研推免资格（专业第 2）", PURPLE),
    ]
    fig, ax = plt.subplots(figsize=(11.5, 3.6))
    ax.set_xlim(-0.4, len(events) - 0.6)
    ax.set_ylim(-1.0, 1.15)
    ax.axis("off")
    ax.plot([-0.3, len(events) - 0.7], [0, 0], color=GREY, lw=1.8, zorder=2)

    for i, (date, text, color) in enumerate(events):
        up = i % 2 == 0
        y = 0.55 if up else -0.55
        ax.plot([i, i], [0, y * 0.72], color=color, lw=1.2, zorder=2)
        ax.scatter([i], [0], s=90, color=color, zorder=4,
                   edgecolor="white", linewidth=1.6)
        va = "bottom" if up else "top"
        ax.text(i, y * 0.80, date, ha="center", va=va, fontsize=9,
                color=color, fontweight="bold")
        ax.text(i, y * 0.80 + (0.16 if up else -0.16), text, ha="center", va=va,
                fontsize=8.4, color=INK, wrap=True)
    return _save(fig, name)


# ---------------------------------------------------------------- 10. 财务预测
def revenue_forecast(name="10_forecast.png"):
    years = ["第 1 年", "第 2 年", "第 3 年", "第 4 年", "第 5 年"]
    revenue = [48, 132, 268, 462, 720]
    cost = [62, 118, 196, 302, 438]
    profit = [r - c for r, c in zip(revenue, cost)]

    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    x = range(len(years))
    ax.plot(x, revenue, marker="o", ms=6, color=BLUE, lw=2.2, label="营业收入")
    ax.plot(x, cost, marker="s", ms=6, color="#94A3B8", lw=2.0, label="营业成本")
    ax.plot(x, profit, marker="^", ms=6, color=GREEN, lw=2.0, label="净利润")
    ax.fill_between(x, profit, 0,
                    where=[p < 0 for p in profit], color=RED, alpha=0.10)
    ax.fill_between(x, profit, 0,
                    where=[p >= 0 for p in profit], color=GREEN, alpha=0.10)

    for i, (r, p) in enumerate(zip(revenue, profit)):
        ax.annotate(f"{r}", (i, r), textcoords="offset points", xytext=(0, 9),
                    ha="center", fontsize=8.4, color=BLUE)
        ax.annotate(f"{p}", (i, p), textcoords="offset points",
                    xytext=(0, -16 if p >= 0 else 8),
                    ha="center", fontsize=8.4, color=GREEN if p >= 0 else RED)

    ax.axhline(0, color=GREY, lw=1.0)
    ax.set_xticks(list(x))
    ax.set_xticklabels(years, fontsize=9.4, color=INK)
    ax.set_ylabel("金额（万元）", fontsize=9.5, color=GREY)
    ax.grid(axis="y", color=GRID, lw=0.9, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0, colors=GREY)
    ax.legend(frameon=False, fontsize=9.2, loc="upper left", labelcolor=INK)
    ax.text(len(years) - 1, revenue[-1] + 62, "第 5 年实现\n净利 282 万元",
            ha="right", va="bottom", fontsize=8.6, color=GREEN, fontweight="bold")
    return _save(fig, name)


# ---------------------------------------------------------------- 11. 文献分布
def literature_dist(name="11_literature.png"):
    cats = ["路径规划", "动态避障", "多机协同", "强化学习", "传感器融合", "工程应用"]
    counts = [48, 36, 22, 31, 17, 14]

    fig, ax = plt.subplots(figsize=(9.8, 3.7))
    y = range(len(cats))
    ax.barh(list(y), counts, height=0.58, color=BLUE, alpha=0.9,
            edgecolor="white", linewidth=1.2, zorder=3)
    for i, v in enumerate(counts):
        ax.text(v + 1.0, i, f"{v} 篇", va="center", fontsize=9, color=INK)

    ax.set_yticks(list(y))
    ax.set_yticklabels(cats, fontsize=9.6, color=INK)
    ax.invert_yaxis()
    ax.set_xlabel("文献数量（篇）", fontsize=9.5, color=GREY)
    ax.set_xlim(0, max(counts) * 1.18)
    ax.grid(axis="x", color=GRID, lw=0.9, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0, colors=GREY)
    ax.text(max(counts) * 1.16, len(cats) - 0.6,
            "共检索 168 篇，精读 62 篇", ha="right", va="top",
            fontsize=8.6, color=GREY, style="italic")
    return _save(fig, name)


# ---------------------------------------------------------------- 12. 研究内容分解（WBS）
def work_package(name="12_wbs.png"):
    """三层研究内容分解图：总目标 → 4 个研究任务 → 各自子任务。"""
    root = "总目标：动态环境下实时自主避障"
    tasks = [
        ("研究任务一\n动力学建模与约束", BLUE, BLUEF,
         ["六自由度\n状态方程", "可行域\n参数辨识"]),
        ("研究任务二\n动态代价函数设计", AMBER, AMBERF,
         ["时空禁行\n锥体建模", "可采纳性\n下界构造"]),
        ("研究任务三\n滚动时域框架", GREEN, GREENF,
         ["窗口长度\n自适应策略", "路径平滑\n与速度规划"]),
        ("研究任务四\n仿真与实机验证", PURPLE, PURPLEF,
         ["200 组\n场景评测", "机载\n移植测试"]),
    ]
    fig, ax = plt.subplots(figsize=(11.6, 5.6))
    ax.set_xlim(0, 11.6)
    ax.set_ylim(0, 5.6)
    ax.axis("off")

    # 根节点
    ax.add_patch(FancyBboxPatch((3.0, 4.72), 5.6, 0.62,
                                boxstyle="round,pad=0.02,rounding_size=0.10",
                                fc=INK, ec=INK, lw=0, zorder=3))
    ax.text(5.8, 5.03, root, ha="center", va="center",
            fontsize=11, color="white", fontweight="bold", zorder=4)

    for i, (title, ec, fc, subs) in enumerate(tasks):
        cx = 1.45 + i * 2.9
        # 连线
        ax.plot([5.8, 5.8], [4.72, 4.28], color=GREY, lw=1.4, zorder=2)
        ax.plot([cx, 5.8], [4.28, 4.28], color=GREY, lw=1.4, zorder=2)
        ax.plot([cx, cx], [4.28, 4.02], color=GREY, lw=1.4, zorder=2)

        ax.add_patch(FancyBboxPatch((cx - 1.22, 3.34), 2.44, 0.68,
                                    boxstyle="round,pad=0.02,rounding_size=0.10",
                                    fc=fc, ec=ec, lw=1.5, zorder=3))
        ax.text(cx, 3.68, title, ha="center", va="center", fontsize=9.2,
                color=INK, fontweight="bold", zorder=4, linespacing=1.4)

        for j, sub in enumerate(subs):
            sy = 2.42 - j * 1.42
            ax.plot([cx, cx], [3.34, sy + 0.44], color=GREY, lw=1.2, zorder=2)
            ax.add_patch(FancyBboxPatch((cx - 1.02, sy - 0.44), 2.04, 0.88,
                                        boxstyle="round,pad=0.02,rounding_size=0.10",
                                        fc="white", ec=ec, lw=1.1, zorder=3))
            ax.text(cx, sy, sub, ha="center", va="center", fontsize=8.2,
                    color=INK, zorder=4, linespacing=1.45)
    return _save(fig, name)


# ---------------------------------------------------------------- 13. 风险矩阵
def risk_matrix(name="13_risk.png"):
    """概率—影响二维风险矩阵，气泡标注风险项。"""
    risks = [
        ("R1 启发函数失效", 0.55, 0.85, RED),
        ("R2 机载算力不足", 0.40, 0.72, AMBER),
        ("R3 测试场地受限", 0.62, 0.42, AMBER),
        ("R4 论文投稿周期", 0.48, 0.30, BLUE),
        ("R5 元器件交期", 0.30, 0.55, GREEN),
    ]
    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    # 风险分区底色
    ax.add_patch(Rectangle((0, 0), 1, 1, fc="#F9FAFB", ec="none", zorder=0))
    ax.add_patch(Rectangle((0.5, 0.5), 0.5, 0.5, fc="#FEE2E2", ec="none",
                           alpha=0.55, zorder=1))
    ax.add_patch(Rectangle((0, 0.5), 0.5, 0.5, fc="#FEF3C7", ec="none",
                           alpha=0.45, zorder=1))
    ax.add_patch(Rectangle((0.5, 0), 0.5, 0.5, fc="#FEF3C7", ec="none",
                           alpha=0.45, zorder=1))
    ax.add_patch(Rectangle((0, 0), 0.5, 0.5, fc="#DCFCE7", ec="none",
                           alpha=0.45, zorder=1))
    ax.axhline(0.5, color=GREY, lw=1.2, ls=(0, (5, 4)), zorder=2)
    ax.axvline(0.5, color=GREY, lw=1.2, ls=(0, (5, 4)), zorder=2)

    for label, p, im, color in risks:
        ax.scatter(p, im, s=340, color=color, alpha=0.80, zorder=4,
                   edgecolor="white", linewidth=2)
        ax.annotate(label, (p, im), textcoords="offset points", xytext=(0, 17),
                    ha="center", fontsize=8.8, color=INK, fontweight="medium")

    ax.text(0.75, 0.955, "高影响 · 高概率", ha="center", va="top",
            fontsize=9, color=RED, fontweight="bold")
    ax.text(0.25, 0.045, "低影响 · 低概率", ha="center", va="bottom",
            fontsize=9, color=GREEN, fontweight="bold")

    ax.set_xlabel("发生概率 →", fontsize=9.6, color=GREY)
    ax.set_ylabel("影响程度 →", fontsize=9.6, color=GREY)
    ax.set_xticks([0, 0.5, 1]); ax.set_yticks([0, 0.5, 1])
    ax.set_xticklabels(["低", "中", "高"], fontsize=9, color=GREY)
    ax.set_yticklabels(["低", "中", "高"], fontsize=9, color=GREY)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(length=0)
    return _save(fig, name)


# ---------------------------------------------------------------- 14. 学业成绩趋势
def grade_trend(name="14_grade.png"):
    """六学期加权均分（柱）与专业排名（折线，反向轴）双轴图。"""
    terms = ["大一上", "大一下", "大二上", "大二下", "大三上", "大三下"]
    score = [89.2, 91.4, 92.8, 93.1, 91.6, 92.4]
    rank = [7, 4, 3, 2, 2, 2]

    fig, ax1 = plt.subplots(figsize=(9.4, 4.2))
    x = range(len(terms))
    bars = ax1.bar(list(x), score, width=0.52, color=BLUE, alpha=0.86,
                   edgecolor="white", linewidth=1.2, zorder=3, label="加权均分")
    for b, v in zip(bars, score):
        ax1.text(b.get_x() + b.get_width() / 2, 64.5, f"{v}",
                 ha="center", va="center", fontsize=9.0, color="white",
                 fontweight="bold", zorder=4)

    ax1.set_ylim(60, 100)
    ax1.set_ylabel("加权平均分", fontsize=9.5, color=GREY)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(terms, fontsize=9.2, color=INK)
    ax1.grid(axis="y", color=GRID, lw=0.9, zorder=0)
    ax1.set_axisbelow(True)
    ax1.tick_params(length=0, colors=GREY)
    for s in ("top", "right"):
        ax1.spines[s].set_visible(False)
    ax1.spines["left"].set_color(GRID)
    ax1.spines["bottom"].set_color(GRID)

    ax2 = ax1.twinx()
    ax2.plot(list(x), rank, marker="o", ms=7, color=AMBER, lw=2.2,
             markeredgecolor="white", markeredgewidth=1.6, zorder=5,
             label="专业排名")
    for i, r in enumerate(rank):
        ax2.annotate(f"{r}", (i, r), textcoords="offset points", xytext=(0, 13),
                     ha="center", fontsize=9.0, color=AMBER, fontweight="bold")
    ax2.set_ylim(9.2, 0.4)          # 反向：排名越靠前越靠上
    ax2.set_ylabel("专业排名（名次）", fontsize=9.5, color=AMBER)
    ax2.tick_params(length=0, colors=GREY)
    for s in ("top", "left", "bottom"):
        ax2.spines[s].set_visible(False)
    ax2.spines["right"].set_color(GRID)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, frameon=False, fontsize=9.2,
               loc="upper center", bbox_to_anchor=(0.5, 1.13),
               labelcolor=INK, ncol=2)
    return _save(fig, name)


def readiness_bars(name="17_readiness.png"):
    """出国准备就绪度：六维度横向进度条（0-100%）。"""
    items = [
        ("语言成绩（雅思 7.0）", 88, GREEN, GREENF),
        ("研究计划与外方对接", 82, BLUE, BLUEF),
        ("专业课成绩与排名", 92, BLUE, BLUEF),
        ("论文与成果产出", 64, AMBER, AMBERF),
        ("跨文化沟通与生活自理", 75, PURPLE, PURPLEF),
        ("回国服务渠道确认", 70, PURPLE, PURPLEF),
    ]
    fig, ax = plt.subplots(figsize=(9.4, 4.0))
    ys = range(len(items))
    for y, (label, val, ec, fc) in zip(ys, items):
        ax.barh(y, 100, height=0.52, color="#F3F4F6", edgecolor="none", zorder=1)
        ax.barh(y, val, height=0.52, color=fc, edgecolor=ec, lw=1.4, zorder=2)
        ax.text(3, y, label, va="center", ha="left", fontsize=10,
                color=INK, fontweight="bold", zorder=3)
        ax.text(val + 2, y, f"{val}%", va="center", ha="left", fontsize=11,
                color=ec, fontweight="bold", zorder=3)
    ax.set_xlim(0, 108)
    ax.set_ylim(-0.7, len(items) - 0.3)
    ax.invert_yaxis()
    ax.axis("off")
    ax.set_title("出国准备就绪度自评（截至申请季）", fontsize=12.5,
                 color=INK, fontweight="bold", pad=14)
    return _save(fig, name)


def training_plan(name="15_training.png"):
    """入伍前体能训练：当前水平 vs 合格线（成对横条）。"""
    items = [
        ("3000 米跑（秒）", 12.4, 13.0, True),
        ("引体向上（个）", 11, 8, False),
        ("俯卧撑 2 分钟（个）", 42, 35, False),
        ("仰卧起坐 2 分钟（个）", 48, 40, False),
        ("单杠卷身上（个）", 4, 3, False),
        ("400 米障碍（秒）", 138, 150, True),
    ]
    fig, ax = plt.subplots(figsize=(9.6, 4.1))
    ys = [i for i in range(len(items))]
    for y, (label, cur, std, lower_better) in zip(ys, items):
        base = max(cur, std)
        ax.barh(y + 0.19, cur / base * 100, height=0.32,
                color=BLUEF, edgecolor=BLUE, lw=1.4, zorder=2)
        ax.barh(y - 0.19, std / base * 100, height=0.32,
                color=AMBERF, edgecolor=AMBER, lw=1.4, zorder=2)
        ax.text(cur / base * 100 + 1.5, y + 0.19, f"{cur:g}", va="center",
                fontsize=9.5, color=BLUE, fontweight="bold")
        ax.text(std / base * 100 + 1.5, y - 0.19, f"{std:g}", va="center",
                fontsize=9.5, color=AMBER, fontweight="bold")
        ax.text(-2, y, label, va="center", ha="right", fontsize=10, color=INK)
    ax.set_xlim(0, 118)
    ax.set_ylim(-0.7, len(items) - 0.3)
    ax.invert_yaxis()
    ax.axis("off")
    handles = [Rectangle((0, 0), 1, 1, fc=BLUEF, ec=BLUE, lw=1.4),
               Rectangle((0, 0), 1, 1, fc=AMBERF, ec=AMBER, lw=1.4)]
    ax.legend(handles, ["本人当前水平", "入伍合格线"], frameon=False,
              fontsize=9.8, loc="lower right", bbox_to_anchor=(1.0, -0.04),
              labelcolor=INK, ncol=2)
    ax.set_title("入伍前体能储备与合格线对照（跑类项目越短越好）", fontsize=12.5,
                 color=INK, fontweight="bold", pad=14)
    return _save(fig, name)


def time_allocation(name="16_timeuse.png"):
    """学期时间分配：五类投入的横向堆叠条。"""
    terms = ["大一", "大二", "大三", "大四上"]
    cats = ["课程学习", "科研与竞赛", "学生工作", "社会实践", "自主学习"]
    data = [
        [46, 12, 18, 12, 12],
        [40, 26, 14, 8, 12],
        [26, 44, 10, 8, 12],
        [18, 52, 4, 10, 16],
    ]
    colors = [BLUE, AMBER, GREEN, PURPLE, "#0891B2"]
    fills = [BLUEF, AMBERF, GREENF, PURPLEF, "#CFFAFE"]

    fig, ax = plt.subplots(figsize=(10.2, 3.9))
    ys = range(len(terms))
    for y, row in zip(ys, data):
        left = 0
        for v, c, f in zip(row, colors, fills):
            ax.barh(y, v, left=left, height=0.56, color=f, edgecolor=c, lw=1.2)
            if v >= 9:
                ax.text(left + v / 2, y, f"{v}%", ha="center", va="center",
                        fontsize=9.2, color=c, fontweight="bold")
            left += v
    ax.set_yticks(list(ys))
    ax.set_yticklabels(terms, fontsize=10.5, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("每周可支配时间占比（%）", fontsize=9.8, color=GREY)
    ax.tick_params(length=0, colors=GREY)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="x", color=GRID, lw=0.9, zorder=0)
    ax.set_axisbelow(True)
    handles = [Rectangle((0, 0), 1, 1, fc=f, ec=c, lw=1.2)
               for c, f in zip(colors, fills)]
    ax.legend(handles, cats, frameon=False, fontsize=9.2, ncol=5,
              loc="upper center", bbox_to_anchor=(0.5, -0.16), labelcolor=INK)
    ax.set_title("四年时间投入结构变化：从「刷绩点」到「做项目」", fontsize=12.5,
                 color=INK, fontweight="bold", pad=14)
    return _save(fig, name)


# ---------------------------------------------------------------- 18. 单亩经济模型瀑布
def unit_economics(name="18_unit_econ.png"):
    """单亩单次收入如何被成本吃掉，最终剩 3.6 元（毛利率 45%）。"""
    steps = [
        ("服务收入", 8.0, "total"),
        ("飞手人工", -1.7, "cost"),
        ("设备折旧\n与油电", -1.2, "cost"),
        ("数据处理", -0.6, "cost"),
        ("管理与损耗", -0.9, "cost"),
        ("单亩毛利", 3.6, "total"),
    ]
    fig, ax = plt.subplots(figsize=(10.6, 4.3))
    running, xs = 0.0, range(len(steps))
    for x, (label, val, kind) in zip(xs, steps):
        if kind == "total":
            bottom, height = 0, val
            color, edge = (BLUEF, BLUE) if x == 0 else (GREENF, GREEN)
        else:
            bottom, height = running + val, -val
            color, edge = REDF, RED
        ax.bar(x, height, bottom=bottom, width=0.56, color=color,
               edgecolor=edge, lw=1.6, zorder=3)
        top = bottom + height
        ty = top + 0.22 if kind == "total" else top + 0.18
        ax.text(x, ty, f"{val:+.1f}" if kind == "cost" else f"{val:.1f}",
                ha="center", va="bottom", fontsize=10.5,
                color=edge, fontweight="bold", zorder=4)
        if kind == "cost":
            ax.plot([x - 0.28, x + 0.28], [running, running],
                    color=GREY, lw=0.9, ls=(0, (3, 2)), zorder=2)
            running += val
        else:
            running = height if x == 0 else running
    # 连接线
    for i in range(len(steps) - 1):
        a, b = steps[i], steps[i + 1]
        ya = a[1] if a[2] == "total" else None
    ax.set_xticks(list(xs))
    ax.set_xticklabels([s[0] for s in steps], fontsize=9.6, color=INK)
    ax.set_ylabel("元 / 亩·次", fontsize=9.8, color=GREY)
    ax.set_ylim(0, 9.4)
    ax.tick_params(length=0, colors=GREY)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID)
    ax.grid(axis="y", color=GRID, lw=0.9, zorder=0)
    ax.set_axisbelow(True)
    ax.set_title("单亩单次经济模型：8.0 元收入中成本占 4.4 元（毛利率 45%）",
                 fontsize=12.5, color=INK, fontweight="bold", pad=14)
    return _save(fig, name)


# ---------------------------------------------------------------- 19. 服务交付流程
def service_flow(name="19_service_flow.png"):
    """六步交付链路，标注责任角色与单次耗时。"""
    steps = [
        ("签约建档", "市场", "1 天", PURPLE, PURPLEF),
        ("航线规划", "算法", "0.5 天", BLUE, BLUEF),
        ("多光谱采集", "飞手", "2 小时/千亩", AMBER, AMBERF),
        ("数据处理", "算法", "4 小时", BLUE, BLUEF),
        ("报告交付", "算法", "0.5 天", BLUE, BLUEF),
        ("复购回访", "市场", "持续", PURPLE, PURPLEF),
    ]
    fig, ax = plt.subplots(figsize=(11.2, 3.5))
    ax.set_xlim(0, len(steps) * 2.0)
    ax.set_ylim(0, 3.0)
    ax.axis("off")
    for i, (label, role, dur, ec, fc) in enumerate(steps):
        x = i * 2.0 + 0.16
        ax.add_patch(FancyBboxPatch(
            (x, 1.28), 1.62, 0.86,
            boxstyle="round,pad=0.02,rounding_size=0.12",
            fc=fc, ec=ec, lw=1.6, zorder=3))
        ax.text(x + 0.81, 1.79, label, ha="center", va="center",
                fontsize=11, color=INK, fontweight="bold", zorder=4)
        ax.text(x + 0.81, 1.44, f"{role} · {dur}", ha="center", va="center",
                fontsize=8.6, color=ec, zorder=4)
        if i < len(steps) - 1:
            ax.annotate("", xy=(x + 1.96, 1.71), xytext=(x + 1.66, 1.71),
                        arrowprops=dict(arrowstyle="-|>", color=GREY, lw=1.4))
    ax.text(0.1, 0.66, "单次作业从签约到交付 3—4 个工作日；订阅客户按生长季滚动，"
                       "复购环节不重复建档与规划",
            fontsize=9.6, color=GREY)
    ax.text(0.1, 0.28, "关键约束：飞手旺季单日上限 1,200 亩（含转场），"
                       "超过则需临时增派——这是服务半径的直接上限",
            fontsize=9.6, color=AMBER)
    return _save(fig, name)


# ---------------------------------------------------------------- 20. 能力与岗位匹配矩阵
def match_matrix(name="20_match_matrix.png"):
    """四个岗位方向 × 五项能力，分值 1—5，用于说明培训成本差异。"""
    posts = ["无人机侦察/巡线", "信息化装备维护", "通信与指挥辅助", "文书与信息化办公"]
    skills = ["执照与操控", "飞控与调试", "编程与数据", "设备维护", "纪律与体能"]
    score = [
        [5, 4, 3, 2, 4],
        [3, 3, 4, 5, 4],
        [2, 2, 4, 3, 4],
        [1, 1, 5, 3, 4],
    ]
    fig, ax = plt.subplots(figsize=(9.6, 4.2))
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "wf", ["#FEF3C7", "#BBF7D0"])
    im = ax.imshow(score, cmap=cmap, vmin=0, vmax=5, aspect="auto")
    ax.set_xticks(range(len(skills)))
    ax.set_xticklabels(skills, fontsize=9.8, color=INK)
    ax.set_yticks(range(len(posts)))
    ax.set_yticklabels(posts, fontsize=9.8, color=INK)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xticks([x - 0.5 for x in range(1, len(skills))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(posts))], minor=True)
    ax.grid(which="minor", color="white", lw=2)
    for i, row in enumerate(score):
        for j, v in enumerate(row):
            ax.text(j, i, str(v), ha="center", va="center", fontsize=12,
                    color=INK if v >= 3 else GREY, fontweight="bold")
    cb = fig.colorbar(im, ax=ax, fraction=0.026, pad=0.02)
    cb.set_label("本人准备程度（5 = 可直接上手）", fontsize=9, color=GREY)
    cb.ax.tick_params(length=0, colors=GREY)
    ax.set_title("专业能力与岗位方向的匹配度自评", fontsize=12.5,
                 color=INK, fontweight="bold", pad=12)
    return _save(fig, name)


# ---------------------------------------------------------------- 21. 回国发展路径
def career_path(name="21_career_path.png"):
    """留学两年 + 回国服务期 + 长期目标的横向时间轴（色块在上、节点在下）。"""
    fig, ax = plt.subplots(figsize=(11.2, 3.8))
    ax.set_xlim(2026.9, 2034.5)
    ax.set_ylim(0, 3.4)
    ax.axis("off")

    AXIS_Y = 1.62
    ax.plot([2027.2, 2034.1], [AXIS_Y, AXIS_Y], color=GRID, lw=3, zorder=1)

    segs = [
        (2027.2, 2029.3, "公派留学 24 个月", BLUE, BLUEF),
        (2029.3, 2031.4, "回国服务期（≥2 年）", AMBER, AMBERF),
        (2031.4, 2034.1, "长期：独立课题与产业化", GREEN, GREENF),
    ]
    for x0, x1, label, ec, fc in segs:
        ax.add_patch(FancyBboxPatch(
            (x0, 2.52), x1 - x0, 0.5,
            boxstyle="round,pad=0.01,rounding_size=0.10",
            fc=fc, ec=ec, lw=1.6, zorder=3))
        ax.text((x0 + x1) / 2, 2.77, label, ha="center", va="center",
                fontsize=10.4, color=ec, fontweight="bold", zorder=4)
        # 色块下缘引出竖虚线到时间轴
        ax.plot([(x0 + x1) / 2, (x0 + x1) / 2], [2.5, AXIS_Y + 0.06],
                color=ec, lw=1, ls=(0, (3, 3)), zorder=2)

    marks = [
        (2027.2, "赴德入学"),
        (2029.3, "按期回国入职"),
        (2031.4, "服务期满"),
        (2034.1, "团队与成果转化"),
    ]
    for x, label in marks:
        ax.plot(x, AXIS_Y, "o", ms=8, mfc="white", mec=INK, mew=1.7, zorder=5)
        ax.text(x, AXIS_Y - 0.2, label, ha="center", va="top",
                fontsize=9.6, color=INK)
        ax.text(x, 0.72, str(int(x)) if float(x).is_integer() else f"{x:.1f}",
                ha="center", va="center", fontsize=9.6, color=GREY)

    ax.text(2026.95, 3.18, "回国服务承诺的落点：把系统级验证方法带回国内团队",
            fontsize=11, color=INK, fontweight="bold")
    return _save(fig, name)


# ---------------------------------------------------------------- 22. 分场景成功率
def scenario_success(name="22_scenario_success.png"):
    """四类典型场景的避障成功率，基线 vs 本项目。"""
    scenes = ["室内走廊", "窄通道", "动态障碍密集", "室外有风"]
    base = [98, 64, 71, 58]
    ours = [99, 92, 94, 88]
    fig, ax = plt.subplots(figsize=(9.6, 4.1))
    x = range(len(scenes))
    w = 0.34
    b1 = ax.bar([i - w / 2 for i in x], base, w, color=AMBERF,
                edgecolor=AMBER, lw=1.5, label="基线 A*")
    b2 = ax.bar([i + w / 2 for i in x], ours, w, color=GREENF,
                edgecolor=GREEN, lw=1.5, label="本项目")
    for bars in (b1, b2):
        for r in bars:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 1.6,
                    f"{r.get_height():.0f}", ha="center", fontsize=10,
                    color=INK, fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels(scenes, fontsize=10, color=INK)
    ax.set_ylim(0, 112)
    ax.set_ylabel("避障成功率（%）", fontsize=9.8, color=GREY)
    ax.axhline(94.3, color=BLUE, lw=1.2, ls=(0, (4, 3)), zorder=1)
    ax.text(len(scenes) - 0.45, 96, "200 组随机场景总体 94.3%",
            ha="right", fontsize=9, color=BLUE)
    ax.tick_params(length=0, colors=GREY)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID)
    ax.grid(axis="y", color=GRID, lw=0.9, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=9.6, loc="lower right", labelcolor=INK, ncol=2)
    ax.set_title("分场景避障成功率：提升集中在窄通道与动态障碍场景",
                 fontsize=12.5, color=INK, fontweight="bold", pad=14)
    return _save(fig, name)


# ---------------------------------------------------------------- 23. 团队组织架构
def org_chart(name="23_org_chart.png"):
    """五人核心团队 + 两条执行线的组织架构。"""
    fig, ax = plt.subplots(figsize=(10.4, 4.2))
    ax.set_xlim(0, 10.4)
    ax.set_ylim(0, 4.2)
    ax.axis("off")

    def box(x, y, w, h, title, sub, ec, fc, ts=10.6):
        ax.add_patch(FancyBboxPatch(
            (x - w / 2, y - h / 2), w, h,
            boxstyle="round,pad=0.02,rounding_size=0.12",
            fc=fc, ec=ec, lw=1.6, zorder=3))
        ax.text(x, y + 0.16, title, ha="center", va="center",
                fontsize=ts, color=INK, fontweight="bold", zorder=4)
        ax.text(x, y - 0.20, sub, ha="center", va="center",
                fontsize=8.6, color=ec, zorder=4)

    box(5.2, 3.55, 2.5, 0.78, "创始人 / CEO", "王浩 · 融资与政府对接", BLUE, BLUEF)
    box(8.6, 3.55, 2.2, 0.78, "技术顾问", "陈立新 教授", PURPLE, PURPLEF)

    mid = [(1.7, "算法负责人", "李明 · 模型与报告", AMBER, AMBERF),
           (5.2, "作业负责人", "张强 · 飞手与调度", GREEN, GREENF),
           (8.0, "市场负责人", "周宁 · 县域合伙", AMBER, AMBERF)]
    for x, t, sub, ec, fc in mid:
        box(x, 2.05, 2.3, 0.76, t, sub, ec, fc)
        ax.plot([5.2, 5.2, x], [3.16, 2.62, 2.62], color=GREY, lw=1.2, zorder=2)
        ax.plot([x, x], [2.62, 2.43], color=GREY, lw=1.2, zorder=2)
    ax.plot([5.2, 8.6], [3.16, 3.16], color=PURPLE, lw=1.2, ls=(0, (3, 2)), zorder=2)

    low = [(1.7, "数据处理 1 人"), (5.2, "飞手 3—5 人 / 县"), (8.0, "农资采购 1 人（待补）")]
    for x, t in low:
        ax.add_patch(FancyBboxPatch(
            (x - 1.05, 0.72), 2.1, 0.44,
            boxstyle="round,pad=0.02,rounding_size=0.10",
            fc="white", ec=GREY, lw=1.1, ls=(0, (3, 2)), zorder=3))
        ax.text(x, 0.94, t, ha="center", va="center", fontsize=9, color=GREY, zorder=4)
        ax.plot([x, x], [1.67, 1.16], color=GREY, lw=1, ls=(0, (2, 2)), zorder=2)

    ax.text(0.15, 0.24, "缺口：懂农资供应链的人。集采上量后采购与账期管理需专职，"
                        "计划 A 轮前引进（图中虚线框）",
            fontsize=9.2, color=RED)
    return _save(fig, name)


# ---------------------------------------------------------------- 24. 入伍后阶段规划
def service_plan(name="24_service_plan.png"):
    """入伍后 2 年 / 5 年 / 长期三段规划，色块在上、节点在下。"""
    fig, ax = plt.subplots(figsize=(11.0, 3.6))
    ax.set_xlim(0, 10.4)
    ax.set_ylim(0, 3.4)
    ax.axis("off")

    segs = [
        (0.35, 3.5, "义务兵役期 2 年", "打基础：队列、体能、专业岗位", BLUE, BLUEF),
        (3.75, 6.9, "选取士官 / 考学（第 3—5 年）", "进专业：成为岗位骨干", AMBER, AMBERF),
        (7.15, 10.2, "长期：技术骨干与带训", "带团队：把经验交给下一批", GREEN, GREENF),
    ]
    for x0, x1, title, sub, ec, fc in segs:
        ax.add_patch(FancyBboxPatch(
            (x0, 1.62), x1 - x0, 1.06,
            boxstyle="round,pad=0.02,rounding_size=0.12",
            fc=fc, ec=ec, lw=1.6, zorder=3))
        ax.text((x0 + x1) / 2, 2.36, title, ha="center", va="center",
                fontsize=10.4, color=ec, fontweight="bold", zorder=4)
        ax.text((x0 + x1) / 2, 1.92, sub, ha="center", va="center",
                fontsize=9.2, color=INK, zorder=4)
    for x, t in ((3.62, "转段节点"), (7.02, "二次选择")):
        ax.annotate("", xy=(x + 0.12, 2.15), xytext=(x - 0.12, 2.15),
                    arrowprops=dict(arrowstyle="-|>", color=GREY, lw=1.4))
        ax.text(x, 1.28, t, ha="center", va="center", fontsize=8.6, color=GREY)

    ax.text(0.35, 0.72, "三个阶段对应的能力要求不同，我的准备也有侧重：",
            fontsize=9.8, color=INK)
    ax.text(0.35, 0.34, "① 体能与纪律（已提前 8 个月训练）　② 专业岗位技能（无人机执照 + 飞控调试）"
                        "　③ 组织与带训能力（在校任学生干部 2 年）",
            fontsize=9.4, color=GREY)
    return _save(fig, name)


# ---------------------------------------------------------------- 25. 消融实验
def ablation(name="25_ablation.png"):
    """逐项剥离后成功率的变化，标注各模块贡献。"""
    items = [
        ("完整方法", 94.3, GREEN, GREENF, "—"),
        ("去掉曲率约束", 92.8, AMBER, AMBERF, "−1.5"),
        ("去掉动态代价函数", 85.6, RED, REDF, "−8.7"),
        ("去掉滚动时域", 78.1, RED, REDF, "−16.2"),
    ]
    fig, ax = plt.subplots(figsize=(9.8, 3.9))
    ys = range(len(items))
    for y, (label, val, ec, fc, delta) in zip(ys, items):
        ax.barh(y, val, height=0.5, color=fc, edgecolor=ec, lw=1.5, zorder=3)
        ax.text(val + 0.8, y, f"{val:.1f}%", va="center", ha="left",
                fontsize=10.5, color=ec, fontweight="bold", zorder=4)
        ax.text(2.5, y, label, va="center", ha="left", fontsize=10.2,
                color=INK, zorder=4)
        if delta != "—":
            ax.text(val - 1.5, y, delta, va="center", ha="right",
                    fontsize=9.6, color=ec, zorder=4)
    ax.set_xlim(0, 104)
    ax.set_ylim(-0.65, len(items) - 0.35)
    ax.invert_yaxis()
    ax.set_yticks([])
    ax.tick_params(length=0, colors=GREY)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="x", color=GRID, lw=0.9, zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlabel("200 组随机动态场景下的避障成功率（%）", fontsize=9.6, color=GREY)
    ax.set_title("消融实验：滚动时域贡献最大，曲率约束主要影响能耗而非成功率",
                 fontsize=12.2, color=INK, fontweight="bold", pad=14)
    return _save(fig, name)



# ---------------------------------------------------------------- 26. 市场漏斗
def market_funnel(name="26_market_funnel.png"):
    """TAM → SAM → SOM 逐层收敛，标明每层的收敛条件。"""
    layers = [
        ("TAM 理论市场", "576 亿元", "全国耕地 18 亿亩 × 年巡田 4 次 × 8 元/亩", 1.00, BLUE, BLUEF),
        ("SAM 可服务市场", "192 亿元", "50 亩以上规模种植户 6 亿亩", 0.62, AMBER, AMBERF),
        ("SOM 可获取市场", "0.96 亿元", "首期 3 个县、300 万亩", 0.30, GREEN, GREENF),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 3.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")

    top_w = 7.0
    for i, (label, val, cond, ratio, ec, fc) in enumerate(layers):
        y = 3.0 - i * 1.0
        w = top_w * ratio
        x0 = (7.4 - w) / 2
        ax.add_patch(plt.Polygon(
            [(x0, y + 0.42), (x0 + w, y + 0.42),
             (x0 + w - 0.34 * ratio, y - 0.42), (x0 + 0.34 * ratio, y - 0.42)],
            closed=True, facecolor=fc, edgecolor=ec, lw=1.6, zorder=3))
        ax.text(x0 + w / 2, y + 0.04, label, ha="center", va="center",
                fontsize=10.2, color=ink_(), fontweight="bold", zorder=5)
        ax.text(x0 + w / 2, y - 0.26, val, ha="center", va="center",
                fontsize=11.0, color=ec, fontweight="bold", zorder=5)
        ax.text(w + (7.4 - w) / 2 + 0.25, y + 0.02, cond, ha="left", va="center",
                fontsize=8.8, color=GREY, zorder=5)

    ax.text(0.02, 0.20,
            "首年目标 48 万元，仅为 SOM 的 0.5%：渗透假设刻意取保守值，"
            "宁可低估市场，也不要靠乐观假设撑估值。",
            ha="left", va="bottom", fontsize=8.8, color=GREY, style="italic")
    return _save(fig, name)


# ---------------------------------------------------------------- 27. 竞争定位
def competitive_map(name="27_competitive_map.png"):
    """横轴监测专业度、纵轴服务闭环度，四类玩家与本项目的位置。"""
    players = [
        ("植保无人机厂商", 7.2, 3.6, 1150, BLUE, "o"),
        ("农服平台", 3.8, 8.2, 1150, AMBER, "o"),
        ("县域飞防队", 1.8, 2.6, 850, GREY, "o"),
        ("第三方检测机构", 6.4, 1.2, 780, PURPLE, "o"),
        ("智农巡田（本项目）", 8.6, 7.2, 1500, GREEN, "*"),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 3.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axvspan(5, 10, ymin=0.5, ymax=1.0, color=GREENF, alpha=0.55, zorder=0)
    ax.axhline(5, color=GRID, lw=1.1, ls=(0, (4, 3)), zorder=1)
    ax.axvline(5, color=GRID, lw=1.1, ls=(0, (4, 3)), zorder=1)

    for label, x, y, size, color, marker in players:
        ax.scatter(x, y, s=size, color=color, marker=marker,
                   edgecolor="white", lw=1.4, zorder=4, alpha=0.95)
        if marker == "*":
            ax.text(x, y - 0.95, label, fontsize=9.6, color=GREEN,
                    ha="center", va="top", fontweight="bold", zorder=5)
        elif x >= 6.0:
            ax.text(x - 0.55, y, label, fontsize=9.4, color=INK,
                    ha="right", va="center", zorder=5)
        else:
            ax.text(x + 0.55, y, label, fontsize=9.4, color=INK,
                    ha="left", va="center", zorder=5)

    ax.text(9.7, 9.7, "有监测能力、又有交付闭环（目前是空位）",
            ha="right", va="top", fontsize=9.2, color=GREEN, fontweight="bold")
    ax.text(0.3, 9.7, "有渠道、缺自主数据", ha="left", va="top",
            fontsize=8.8, color=GREY)
    ax.text(9.7, 0.4, "硬件强、监测只是附属功能", ha="right", va="bottom",
            fontsize=8.8, color=GREY)
    ax.set_xlabel("监测专业度（自有数据 + 模型能力）→", fontsize=9.2, color=GREY)
    ax.set_ylabel("服务闭环度（能否直接交付到农户）→", fontsize=9.2, color=GREY,
                  labelpad=8)
    ax.set_xticks([])
    ax.set_yticks([])
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    for s_ in ("left", "bottom"):
        ax.spines[s_].set_color(GRID)
    ax.set_title("四类玩家各占一角，右上角还没有人站住",
                 fontsize=11.6, color=INK, fontweight="bold", pad=12)
    fig.text(0.01, 0.01,
             "注：位置依据公开资料与 47 份农户访谈整理，为定性判断，非量化测评。",
             ha="left", va="bottom", fontsize=8.4, color=GREY, style="italic")
    return _save(fig, name)


# ---------------------------------------------------------------- 28. 现金流
def cashflow(name="28_cashflow.png"):
    """净利润柱 + 累计现金流线，标出资金最低点。"""
    years = ["第 1 年", "第 2 年", "第 3 年"]
    profit = [-14, -6, 72]
    cum = [-14, -20, 52]

    fig, ax = plt.subplots(figsize=(8.6, 3.9))
    x = list(range(len(years)))
    bars = ax.bar(x, profit, width=0.46, color=[REDF, REDF, GREENF],
                  edgecolor=[RED, RED, GREEN], lw=1.6, zorder=3, label="当年净利润")
    for xi, v in zip(x, profit):
        ax.text(xi, v + (6 if v >= 0 else -6), f"{v:+d}", ha="center",
                va="bottom" if v >= 0 else "top", fontsize=10.2,
                color=GREEN if v >= 0 else RED, fontweight="bold", zorder=4)

    ax.plot(x, cum, marker="o", ms=7, color=BLUE, lw=2.2, zorder=5,
            label="累计净利润")
    for xi, v in zip(x, cum):
        ax.annotate(f"{v:+d}", (xi, v), textcoords="offset points",
                    xytext=(0, -17), ha="center", fontsize=9.4, color=BLUE, zorder=6)

    ax.axhline(0, color=GREY, lw=1.0)
    ax.annotate("资金最低点 −20 万元\n（第 2 年末）", (1, -20),
                textcoords="offset points", xytext=(28, -34), fontsize=9.0,
                color=RED, arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.2),
                zorder=7)
    ax.annotate("第 3 年累计转正", (2, 52), textcoords="offset points",
                xytext=(-8, 22), ha="right", fontsize=9.0, color=GREEN,
                arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=1.2), zorder=7)

    ax.set_xticks(x)
    ax.set_xticklabels(years, fontsize=9.8, color=INK)
    ax.set_ylabel("万元", fontsize=9.6, color=GREY)
    ax.set_ylim(-46, 78)
    ax.grid(axis="y", color=GRID, lw=0.9, zorder=0)
    ax.set_axisbelow(True)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0, colors=GREY)
    ax.legend(frameon=False, fontsize=9.2, loc="upper left", labelcolor=INK)
    ax.text(0.02, -42, "注：未计入融资款，仅反映经营自身造血能力；融资到账后现金缺口完全覆盖。",
            fontsize=8.4, color=GREY, style="italic")
    return _save(fig, name)


# ---------------------------------------------------------------- 29. 风险热力
def risk_heat(name="29_risk_heat.png"):
    """概率 × 影响 的风险热力矩阵，8 项风险落点。"""
    risks = [
        ("R1", "作业窗口受天气挤压", 4, 3),
        ("R2", "飞手流失", 3, 3),
        ("R3", "价格战", 4, 4),
        ("R4", "模型准确率不达预期", 2, 4),
        ("R5", "补贴政策退坡", 2, 2),
        ("R6", "回款账期拉长", 3, 2),
        ("R7", "设备炸机与丢失", 2, 3),
        ("R8", "竞品下沉县域", 3, 4),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 3.9))
    for i in range(1, 5):
        for j in range(1, 5):
            score = i * j
            if score >= 12:
                fc, ec = REDF, RED
            elif score >= 6:
                fc, ec = AMBERF, AMBER
            else:
                fc, ec = GREENF, GREEN
            ax.add_patch(Rectangle((i - 0.5, j - 0.5), 1, 1, facecolor=fc,
                                   edgecolor="white", lw=2.0, zorder=1))
    for code, label, p, im in risks:
        ax.scatter(p, im, s=620, color="white", edgecolor=INK, lw=1.6, zorder=5)
        ax.text(p, im, code, ha="center", va="center", fontsize=8.6,
                color=INK, fontweight="bold", zorder=6)
    # 右侧列出编号对照，避免图内文字过密
    for k, (code, label, _, _) in enumerate(risks):
        ax.text(5.15, 4.05 - k * 0.46, f"{code} {label}", fontsize=8.8,
                color=INK, ha="left", va="center")
    ax.set_xlim(0.4, 8.6)
    ax.set_ylim(0.4, 4.6)
    ax.set_xticks([1, 2, 3, 4])
    ax.set_xticklabels(["很低", "低", "中", "高"], fontsize=9.2, color=INK)
    ax.set_yticks([1, 2, 3, 4])
    ax.set_yticklabels(["很小", "小", "中", "大"], fontsize=9.2, color=INK)
    ax.set_xlabel("发生概率 →", fontsize=9.4, color=GREY)
    ax.set_ylabel("影响程度 →", fontsize=9.4, color=GREY)
    ax.tick_params(length=0, colors=GREY)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    for s_ in ("left", "bottom"):
        ax.spines[s_].set_color(GRID)
    ax.set_title("右上角两项（价格战、竞品下沉）是真正会致命的",
                 fontsize=11.4, color=INK, fontweight="bold", pad=12)
    return _save(fig, name)


# ---------------------------------------------------------------- 30. 实施甘特图
def gantt_impl(name="30_gantt_impl.png"):
    """M1–M12 三条泳道的实施排期，含里程碑与依赖关系。"""
    lanes = [
        ("产品与数据", BLUE, BLUEF, [
            ("采集流程标准化", 1, 3),
            ("模型 v1 训练", 2, 5),
            ("地块档案系统", 4, 8),
            ("模型 v2 迭代", 8, 12),
        ]),
        ("组织与作业", AMBER, AMBERF, [
            ("飞手招募培训", 1, 4),
            ("首县整村作业", 4, 7),
            ("作业 SOP", 6, 9),
            ("第二县复制", 9, 12),
        ]),
        ("商务与合规", GREEN, GREENF, [
            ("合作社签约 8 家", 2, 5),
            ("经营许可与保险", 1, 4),
            ("按亩定价", 5, 7),
            ("第三县签约回款", 10, 12),
        ]),
    ]
    milestones = [
        (5, "M5 首县跑通", "center", -1.16),
        (8, "M8 复购验证", "center", -1.62),
        (12, "M12 三县达产", "right", -1.16),
    ]

    fig, ax = plt.subplots(figsize=(8.6, 3.9))
    ylabels, ypos, y = [], {}, 0.0
    row_h = 0.62
    for lname, c, cf, items in lanes:
        ylabels.append((y + (len(items) - 1) * row_h / 2, lname))
        for text, s, e in items:
            ypos[text] = y
            ax.add_patch(FancyBboxPatch(
                (s - 0.5, y - 0.22), (e - s + 1), 0.44,
                boxstyle="round,pad=0.02,rounding_size=0.10",
                facecolor=cf, edgecolor=c, linewidth=1.3, zorder=3))
            ax.text((s + e) / 2, y, text, ha="center", va="center",
                    fontsize=12, color=INK, zorder=4)
            y += row_h
        y += 0.42

    ax.set_yticks([])
    ax.set_ylim(y - 0.55, -1.95)
    ax.set_xlim(-0.95, 12.95)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels([f"M{i}" for i in range(1, 13)], fontsize=11, color=INK)
    ax.xaxis.grid(True, color=GRID, linewidth=1.0, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="x", length=0, pad=6)

    for yy, lname in ylabels:
        ax.text(-0.90, yy, lname, ha="left", va="center",
                fontsize=11.5, color=INK, fontweight="bold")

    # 顶部里程碑带：竖虚线定月份，菱形对齐到排期行
    for x, label, ha, ly in milestones:
        ax.plot([x, x], [-0.62, y - 0.62], color=RED, linewidth=0.9,
                linestyle=(0, (4, 4)), alpha=0.45, zorder=1)
        ax.plot([x], [-0.72], marker="D", markersize=10.0,
                color=RED, zorder=6, clip_on=False)
        ax.text(x, ly, label, ha=ha, va="center",
                fontsize=11, color=RED, fontweight="bold")

    ax.text(-0.90, -1.16, "对外承诺里程碑", ha="left", va="center",
            fontsize=11, color=RED, fontweight="bold")

    ax.set_title("十二个月实施排期：三条泳道并行推进，三个里程碑卡住节奏",
                 fontsize=13.2, color=INK, fontweight="bold", pad=14)
    fig.text(0.01, 0.005,
             "说明：菱形为对外承诺的里程碑，未按期达成即触发融资款暂缓到账（见第六章）。",
             fontsize=10.2, color=GREY)
    return _save(fig, name)


# ---------------------------------------------------------------- 31. 单位经济瀑布
def unit_walk(name="31_unit_walk.png"):
    """每亩次收入如何被各项成本吃掉，最后剩下 3.6 元毛利。"""
    steps = [
        ("按亩收费", 8.0, "total", BLUE),
        ("飞行作业", -2.6, "neg", RED),
        ("数据标注", -1.1, "neg", AMBER),
        ("销售与履约", -0.7, "neg", PURPLE),
        ("单亩毛利", 3.6, "total", GREEN),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 3.9))
    run = 0.0
    xs = []
    for i, (label, val, kind, c) in enumerate(steps):
        xs.append(i)
        if kind == "total":
            ax.bar(i, val, width=0.56, facecolor=c, edgecolor=c,
                   linewidth=1.2, alpha=0.92, zorder=3)
            ax.text(i, val + 0.20, f"{val:.1f}", ha="center", va="bottom",
                    fontsize=12.8, color=c, fontweight="bold")
            run = val if i == 0 else run
        else:
            ax.bar(i, val, width=0.56, bottom=run, facecolor="#FFFFFF",
                   edgecolor=c, linewidth=1.8, hatch="///", zorder=3)
            ax.text(i, run + val - 0.42, f"{val:.1f}", ha="center", va="top",
                    fontsize=12.4, color=c, fontweight="bold")
            run = run + val
        if i < len(steps) - 1 and kind != "total":
            ax.plot([i - 0.28, i + 0.28], [run, run], color=GREY,
                    linewidth=1.1, linestyle=(0, (3, 3)), zorder=2)
        elif i == 0:
            ax.plot([i - 0.28, i + 0.28], [run, run], color=GREY,
                    linewidth=1.1, linestyle=(0, (3, 3)), zorder=2)

    ax.set_xticks(xs)
    ax.set_xticklabels([s[0] for s in steps], fontsize=11.6, color=INK)
    ax.set_ylabel("元 / 亩·次", fontsize=11.6, color=INK)
    ax.set_ylim(0, 9.4)
    ax.yaxis.grid(True, color=GRID, linewidth=1.0, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)

    ax.text(3.62, 7.05,
            "毛利 3.6 元 = 45%\n变动成本 4.4 元 = 55%",
            ha="center", va="center", fontsize=11.6, color=INK,
            bbox=dict(boxstyle="round,pad=0.45", facecolor=GREENF,
                      edgecolor=GREEN, linewidth=1.2))

    ax.set_title("单位经济拆解：8 元的收费里，有 4.4 元是随作业量走的变动成本",
                 fontsize=13.2, color=INK, fontweight="bold", pad=14)
    fig.text(0.01, -0.02,
             "说明：土地、设备折旧、管理与研发等固定成本未摊入，"
             "盈亏平衡点按固定成本总额除以 3.6 元反算（见第五章）。",
             fontsize=10.2, color=GREY)
    return _save(fig, name)


def main():
    font = setup_font()
    print(f"中文字体：{font}")
    print(f"输出目录：{OUT}")
    for fn in (tech_roadmap, gantt, budget_donut, algo_compare, swot, innovation_chain,
               business_canvas, capability_radar, achievement_timeline,
               revenue_forecast, literature_dist, work_package, risk_matrix,
               grade_trend, training_plan, time_allocation, readiness_bars,
               unit_economics, service_flow, match_matrix, career_path,
               scenario_success, org_chart, service_plan, ablation,
               market_funnel, competitive_map, cashflow, risk_heat,
               gantt_impl, unit_walk):
        fn()
    print("全部完成")


if __name__ == "__main__":
    main()
