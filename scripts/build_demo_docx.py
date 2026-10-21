#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成图文并茂的《大创·创新训练项目申报书》示例 docx。

结构参照各高校教务处公开模板的通用栏目，内容为虚构示例。
配图来自 scripts/demo_figures.py 的代码渲染结果。
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "build" / "figures"
OUT = ROOT / "examples" / "demos" / "demo_innovation_research.docx"

HEI = "黑体"
SONG = "宋体"
INK = RGBColor(0x11, 0x18, 0x27)
GREY = RGBColor(0x6B, 0x72, 0x80)


def set_font(run, name=SONG, size=12, bold=False, color=INK):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    return run


def para(doc, text="", size=12, bold=False, name=SONG, align=None,
         first_indent=True, space_after=6, line=1.5, color=INK):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(space_after)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = line
    if first_indent:
        pf.first_line_indent = Pt(size * 2)
    if text:
        set_font(p.add_run(text), name, size, bold, color)
    return p


def h1(doc, text):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(18)
    pf.space_after = Pt(8)
    pf.line_spacing = 1.5
    set_font(p.add_run(text), HEI, 15, True)
    return p


def h2(doc, text):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(10)
    pf.space_after = Pt(5)
    pf.line_spacing = 1.5
    set_font(p.add_run(text), HEI, 12.5, True)
    return p


def figure(doc, filename, caption, width_cm=15.2):
    """插入图片 + 图注（图注在下方居中，五号楷体风格）。"""
    path = FIG / filename
    if not path.exists():
        print(f"  ⚠ 缺少配图 {filename}，跳过")
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.add_run().add_picture(str(path), width=Cm(width_cm))

    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(12)
    set_font(cap.add_run(caption), SONG, 10.5, False, GREY)


def table(doc, header, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        cell = t.rows[0].cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_font(p.add_run(h), HEI, 10.5, True)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            if i > 0:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_font(p.add_run(str(v)), SONG, 10.5)
    if widths:
        for r in t.rows:
            for i, w in enumerate(widths):
                r.cells[i].width = Cm(w)
    return t


def build():
    doc = Document()

    # 页面设置：A4，公文页边距
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.top_margin, sec.bottom_margin = Cm(2.54), Cm(2.54)
    sec.left_margin, sec.right_margin = Cm(3.0), Cm(2.6)

    # 默认样式
    style = doc.styles["Normal"]
    style.font.name = SONG
    style.font.size = Pt(12)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), SONG)

    # ---------------- 封面 ----------------
    for _ in range(3):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(p.add_run("大学生创新创业训练计划"), HEI, 26, True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(30)
    set_font(p.add_run("创 新 训 练 项 目 申 报 书"), HEI, 22, True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    set_font(p.add_run("面向复杂环境的无人机自主路径规划系统"), HEI, 16, True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(60)
    set_font(p.add_run("—— 基于滚动时域与动态代价函数的改进 A* 算法"), SONG, 12, False, GREY)

    info = [
        ("项目类别", "创新训练项目"),
        ("所属学科", "计算机科学与技术 / 控制科学与工程"),
        ("项目负责人", "李　明"),
        ("指导教师", "张建国　副教授"),
        ("申报单位", "智能科学与技术学院"),
        ("申请经费", "3.00 万元"),
        ("起止时间", "2026 年 04 月 — 2027 年 03 月"),
    ]
    t = doc.add_table(rows=0, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for k, v in info:
        cells = t.add_row().cells
        cells[0].width, cells[1].width = Cm(4.2), Cm(9.0)
        p0 = cells[0].paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        set_font(p0.add_run(k + "："), SONG, 12)
        p1 = cells[1].paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
        set_font(p1.add_run(v), SONG, 12)

    doc.add_page_break()

    # ---------------- 一、项目简介 ----------------
    h1(doc, "一、项目简介")
    para(doc,
         "本项目面向城市低空物流与应急救援场景，研究复杂动态环境下的无人机自主路径规划问题。"
         "现有 A* 类算法在障碍物位置随时间变化的场景中，存在重规划频繁、路径抖动、避障成功率偏低等缺陷。"
         "本项目提出以滚动时域规划为框架、引入动态代价函数与局部避障约束的改进方案，"
         "并通过 Gazebo 仿真与实机验证，形成一套可在嵌入式平台实时运行的规划模块。")

    table(doc,
          ["项目名称", "面向复杂环境的无人机自主路径规划系统"],
          [("项目类别", "创新训练项目"),
           ("研究周期", "12 个月（2026.04 — 2027.03）"),
           ("核心指标", "避障成功率 ≥ 92%，路径长度降低 ≥ 15%，单次规划耗时 ≤ 200 ms"),
           ("预期成果", "期刊论文 1 篇、样机 1 台、软件著作权 1 项")],
          widths=[3.2, 12.0])

    # ---------------- 二、立项依据 ----------------
    h1(doc, "二、立项依据")
    h2(doc, "2.1 研究背景与痛点")
    para(doc,
         "随着低空经济政策逐步落地，无人机在城市配送、电力巡检、灾害搜救等场景的应用快速扩张。"
         "这类场景的共同特征是障碍物动态变化——行人、车辆、临时禁飞区都会在飞行过程中出现。"
         "而当前主流的 A* 及其变体算法本质上是在静态栅格地图上做一次性最优搜索，"
         "一旦环境变化就必须全局重规划，带来的计算开销与路径抖动在嵌入式平台上难以接受。")

    h2(doc, "2.2 现有方案不足")
    para(doc,
         "调研发现，现有改进方向主要分为三类：一是引入 D* Lite 等增量搜索算法降低重规划代价，"
         "但对突发障碍的响应仍依赖完整重算；二是采用模型预测控制做局部避障，"
         "但缺乏全局最优性保证，易陷入局部极小；三是基于强化学习的端到端方法，"
         "但训练成本高、可解释性差，难以通过工程验收。本项目试图在全局最优性与实时响应之间取得平衡。")

    figure(doc, "06_innovation.png",
           "图 1　项目创新逻辑链：从痛点识别到成果验证的完整推导路径")

    # ---------------- 三、研究内容与技术路线 ----------------
    h1(doc, "三、研究内容与技术路线")

    h2(doc, "3.1 研究内容")
    para(doc, "本项目按四个阶段推进，各阶段研究内容与产出如下：")
    table(doc,
          ["阶段", "研究内容", "阶段产出"],
          [("第一阶段", "文献调研与痛点定位；无人机六自由度动力学建模", "需求分析报告、动力学模型"),
           ("第二阶段", "改进 A* 路径规划算法设计；动态障碍规避策略", "算法设计文档、核心代码"),
           ("第三阶段", "Gazebo 仿真平台搭建；多场景对比实验", "仿真数据集、对比实验报告"),
           ("第四阶段", "样机集成与参数整定；论文撰写与成果整理", "原理样机、期刊论文")],
          widths=[2.6, 8.6, 4.2])

    h2(doc, "3.2 技术路线")
    para(doc,
         "技术路线采用「建模—设计—验证—落地」的递进结构。第一阶段完成环境建模与问题形式化；"
         "第二阶段在经典 A* 基础上引入时间维度，将代价函数扩展为 g(n,t)+h(n,t)，"
         "并以滚动时域方式在每个控制周期内求解局部最优子问题；"
         "第三阶段通过仿真构造多类动态场景验证算法鲁棒性；第四阶段完成嵌入式移植与实机测试。")

    figure(doc, "01_tech_roadmap.png",
           "图 2　四阶段技术路线图（含各阶段研究内容与前后依赖关系）")

    h2(doc, "3.3 关键科学问题")
    para(doc,
         "（1）动态代价函数的构建方式：如何在保证启发函数可采纳性的前提下，"
         "将障碍物的运动趋势编码进代价值，避免算法退化为贪心搜索。")
    para(doc,
         "（2）滚动时域的窗口长度选取：窗口过短会导致全局性缺失，过长则失去实时性优势，"
         "需要通过实验确定与飞行速度、障碍密度的函数关系。")

    # ---------------- 四、研究方案与可行性 ----------------
    h1(doc, "四、研究方案与可行性分析")

    h2(doc, "4.1 研究方案")
    para(doc,
         "算法实现基于 ROS 2 框架，规划模块以独立节点形式部署，"
         "接收感知节点输出的动态障碍物位姿序列，输出平滑的局部航点。"
         "为便于对比，同步实现经典 A*、D* Lite 两个基线算法，在同一数据集上做横向评测。")

    figure(doc, "04_compare.png",
           "图 3　改进算法与经典 A* 在四项核心指标上的对比（归一化处理，数值为实际测量值）")

    para(doc,
         "实验结果显示：在 200 组随机动态场景中，改进算法避障成功率由 72.5% 提升至 94.3%，"
         "平均路径长度由 128.4 m 降至 106.2 m（降低 17.3%），"
         "单次规划耗时由 420 ms 降至 168 ms（降低 60.0%），能耗下降 18.3%。")

    h2(doc, "4.2 可行性分析")
    para(doc, "采用 SWOT 方法对项目的内外部条件做系统梳理，结果如下：")

    figure(doc, "05_swot.png",
           "图 4　项目 SWOT 分析矩阵")

    para(doc,
         "结论：项目的技术路线清晰、团队基础扎实、外部政策环境有利；"
         "主要风险集中于实机测试场地与元器件供货周期，已通过校地合作与提前备料予以对冲。")

    # ---------------- 五、进度安排 ----------------
    h1(doc, "五、进度安排")
    para(doc,
         "项目总周期 12 个月，按 8 项任务分解，设置中期检查与结题验收两个关键节点。"
         "各任务的起止时间与工期如下：")

    figure(doc, "02_gantt.png",
           "图 5　项目进度甘特图（M1—M12，红色虚线为中期检查与结题验收节点）")

    # ---------------- 六、预期成果 ----------------
    h1(doc, "六、预期成果与考核指标")
    table(doc,
          ["成果类型", "具体内容", "考核指标"],
          [("学术论文", "投稿中文核心期刊 1 篇", "录用或见刊"),
           ("知识产权", "软件著作权 1 项", "获得登记证书"),
           ("实物成果", "原理样机 1 台", "完成实机飞行验证"),
           ("竞赛成果", "参加省级以上学科竞赛", "获省级三等奖以上")],
          widths=[3.4, 7.6, 4.4])

    # ---------------- 七、经费预算 ----------------
    h1(doc, "七、经费预算")
    para(doc,
         "项目申请经费 3.00 万元，按下表科目编列。预算编制遵循「必需、节约、可核查」原则，"
         "设备与材料费占比最高，主要用于无人机机体、传感器与计算平台。")

    figure(doc, "03_budget.png", "图 6　经费预算结构（合计 3.00 万元）", width_cm=12.5)

    table(doc,
          ["序号", "支出科目", "金额（元）", "测算依据"],
          [("1", "设备与材料费", "12,600", "无人机机体 2 套、激光雷达 1 台、机载计算模块 2 块"),
           ("2", "测试与加工费", "6,000", "结构件 3D 打印、电路板打样与贴片"),
           ("3", "差旅与调研费", "4,500", "参加学术会议 2 次、企业调研 3 次"),
           ("4", "文献与资料费", "2,400", "文献数据库检索、标准文本购置"),
           ("5", "专家咨询费", "2,100", "邀请领域专家指导 3 次"),
           ("6", "其他支出", "2,400", "耗材、打印、成果印制"),
           ("", "合　计", "30,000", "—")],
          widths=[1.6, 3.6, 3.0, 7.8])

    # ---------------- 八、审核意见 ----------------
    h1(doc, "八、审核意见")
    for title in ("指导教师意见", "学院审核意见", "学校评审意见"):
        h2(doc, title)
        para(doc, "　", first_indent=False, space_after=18)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_after = Pt(4)
        set_font(p.add_run("签字：＿＿＿＿＿＿＿＿　　　日期：　　年　　月　　日"),
                 SONG, 11, False, GREY)
        para(doc, "　", first_indent=False, space_after=10)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(f"✓ 已生成 {OUT}")
    return OUT


if __name__ == "__main__":
    build()
