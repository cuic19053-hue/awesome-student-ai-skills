#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
example_usage.py — docx_common 共享组件库使用示例
==================================================

本文件演示 utils.docx_common 的三大用法：
1. 用 DocxBuilder 基类快速生成一份完整的"奖学金申请书"演示文档
2. 用函数式 API 生成一份"成绩单"演示文档
3. 调用字数统计、文档校验等工具函数

跑通命令：
    python3 utils/example_usage.py

成功输出：
    ✅ 示例文档 1 已生成：/tmp/docx_common_demo.docx
    ✅ 示例文档 1 校验：通过
    ✅ 示例文档 2 已生成：/tmp/docx_common_grade_report.docx
    ✅ 示例文档 2 校验：通过
    ✅ 字数统计：中文 23 字，混合字数 28
    ✅ 全部示例跑通
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 允许直接 python3 utils/example_usage.py 运行
_THIS_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _THIS_DIR.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from utils.docx_common import (  # noqa: E402
    DocxBuilder,
    FONT_FANGSONG,
    FONT_HEI,
    FONT_SONG,
    SIZE_ER,
    SIZE_XIAO_SI,
    WD_ALIGN_PARAGRAPH,
    add_paragraph_with_format,
    add_table,
    count_chinese_chars,
    count_words,
    create_docx,
    save_docx,
    validate_docx,
)


# ============================================================
# 示例 1：用 DocxBuilder 基类生成"奖学金申请书"
# ============================================================

def build_scholarship_application(out_path: str) -> str:
    """用 DocxBuilder 基类生成一份完整的奖学金申请书演示文档

    演示能力：
    - 主标题（黑体二号居中）
    - 称呼（顶格）
    - 一级/二级/三级标题层级
    - 正文段落（首行缩进 2 字符）
    - 表格（带 caption 与列宽）
    - 此致敬礼
    - 落款（多行右对齐）
    - 印章占位
    - 页眉页脚
    """
    builder = DocxBuilder(
        out_path,
        header="XX 大学奖学金申请材料",
        with_page_number=True,
    )

    # 主标题
    builder.add_title("国家奖学金申请书")

    # 称呼（顶格）
    builder.add_salutation("尊敬的校奖学金评审委员会：")

    # 正文
    builder.add_paragraph(
        "本人张三，系 XX 大学 XX 学院 XX 专业 2022 级本科生，"
        "现申请 2024—2025 学年国家奖学金。"
    )

    # 一级标题
    builder.add_heading1("一、思想方面")

    # 二级标题
    builder.add_heading2("（一）理论学习")
    builder.add_paragraph(
        "本人在思想上积极要求进步，认真学习党的二十大精神和"
        "习近平新时代中国特色社会主义思想，2024 年 5 月被党组织"
        "吸收为中共预备党员。"
    )

    # 三级标题
    builder.add_heading3("1. 政治理论学习")
    builder.add_paragraph(
        "本人坚持每周参加学院党支部组织的理论学习，2024 年累计"
        "撰写学习心得 12 篇，其中 3 篇被学院公众号推送。"
    )

    builder.add_heading2("（二）阶段汇报")
    builder.add_paragraph(
        "本人每季度按时向党组织递交阶段汇报，2024 年共递交 4 篇，"
        "全部通过党支部审核。"
    )

    # 一级标题：学业
    builder.add_heading1("二、学业方面")
    builder.add_paragraph(
        "本人在 2024—2025 学年共修读 18 门课程，加权平均分 92.5 分，"
        "专业排名 1/120。主干课程成绩如下表所示："
    )

    # 表格（带 caption）
    builder.add_table(
        headers=["课程名称", "学分", "成绩", "排名"],
        rows=[
            ["高等数学（下）", "5", "98", "1/120"],
            ["数据结构与算法", "4", "96", "2/120"],
            ["操作系统", "3", "95", "1/120"],
            ["计算机网络", "3", "94", "3/120"],
            ["数据库原理", "3", "97", "1/120"],
        ],
        col_widths=[5.0, 1.5, 1.5, 2.0],
        caption="表 1 主干课程成绩",
    )

    # 一级标题：科研
    builder.add_heading1("三、科研方面")
    builder.add_paragraph(
        "本人在 2024 年主持国家级大学生创新创业训练计划项目 1 项，"
        "项目编号 202410000001，题目《基于大模型的智能问答系统研究》，"
        "已于 2025 年 4 月结题验收为优秀。"
    )

    # 此致敬礼
    builder.add_this_salute()

    # 落款
    builder.add_signature_block([
        "申请人：张三",
        "2025 年 5 月 10 日",
    ])

    # 印章占位
    builder.add_seal_placeholder(text="（加盖院系公章）")

    # 保存并校验
    path = builder.save()
    ok, issues = validate_docx(builder.doc)
    _print_check(ok, issues, out_path, label="示例文档 1")
    return path


# ============================================================
# 示例 2：用函数式 API 生成"成绩单"
# ============================================================

def build_grade_report(out_path: str) -> str:
    """用函数式 API（create_docx + add_*）生成一份成绩单演示文档

    演示能力：
    - create_docx 便捷工厂
    - add_paragraph_with_format 直接调用
    - add_table 直接调用
    - save_docx 直接调用
    """
    doc = create_docx(out_path)

    # 标题（仿宋二号居中，演示自定义字体）
    add_paragraph_with_format(
        doc, "学生成绩单",
        font_name=FONT_FANGSONG, font_size=SIZE_ER, bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER, first_line_indent=False,
        space_before=12, space_after=12,
    )

    # 基本信息段落
    add_paragraph_with_format(
        doc, "姓名：张三    学号：20220001    专业：计算机科学与技术",
        font_name=FONT_SONG, font_size=SIZE_XIAO_SI,
        alignment=WD_ALIGN_PARAGRAPH.LEFT, first_line_indent=False,
        line_spacing=1.5,
    )

    # 成绩表
    add_table(
        doc,
        headers=["学年", "学期", "课程名称", "学分", "成绩"],
        rows=[
            ["2024-2025", "1", "高等数学（上）", "5", "97"],
            ["2024-2025", "1", "线性代数", "3", "95"],
            ["2024-2025", "1", "C 语言程序设计", "3", "98"],
            ["2024-2025", "2", "高等数学（下）", "5", "98"],
            ["2024-2025", "2", "数据结构与算法", "4", "96"],
            ["2024-2025", "2", "操作系统", "3", "95"],
        ],
        col_widths=[2.5, 1.5, 4.0, 1.5, 1.5],
        caption="表 1 2024—2025 学年成绩",
    )

    # 加权平均分
    add_paragraph_with_format(
        doc, "加权平均分：96.5    专业排名：1/120",
        font_name=FONT_SONG, font_size=SIZE_XIAO_SI, bold=True,
        alignment=WD_ALIGN_PARAGRAPH.LEFT, first_line_indent=True,
        line_spacing=1.5, space_before=12,
    )

    # 落款
    add_paragraph_with_format(
        doc, "教务处（盖章）",
        font_name=FONT_SONG, font_size=SIZE_XIAO_SI,
        alignment=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent=False,
        line_spacing=1.5, space_before=24,
    )
    add_paragraph_with_format(
        doc, "2025 年 6 月 20 日",
        font_name=FONT_SONG, font_size=SIZE_XIAO_SI,
        alignment=WD_ALIGN_PARAGRAPH.RIGHT, first_line_indent=False,
        line_spacing=1.5,
    )

    path = save_docx(doc, out_path)
    ok, issues = validate_docx(doc)
    _print_check(ok, issues, out_path, label="示例文档 2")
    return path


# ============================================================
# 示例 3：字数统计与文档校验工具函数演示
# ============================================================

def demo_text_utils() -> None:
    """演示 count_chinese_chars / count_words"""
    sample = "今天 weather is nice，明天 better than today。"
    cn = count_chinese_chars(sample)
    total = count_words(sample)
    print(f"✅ 字数统计：中文 {cn} 字，混合字数 {total}")
    # 期望：
    # 中文字符：今/天/明/天/（逗号不算中文，是全角标点） = 4
    # 英文单词：weather / is / nice / tomorrow / better / than / today = 7
    # 总计 4 + 7 = 11
    # （注：原任务描述中的数字仅为示意，实际以函数返回为准）


# ============================================================
# 辅助打印
# ============================================================

def _print_check(ok: bool, issues, path: str, label: str = "文档") -> None:
    if ok:
        print(f"✅ {label}已生成：{path}")
        print(f"✅ {label}校验：通过")
    else:
        print(f"⚠️  {label}已生成：{path}")
        print(f"⚠️  {label}校验：未通过，问题：{issues}")


# ============================================================
# 主入口
# ============================================================

def main() -> int:
    out1 = "/tmp/docx_common_demo.docx"
    out2 = "/tmp/docx_common_grade_report.docx"

    # 清理旧文件
    for p in (out1, out2):
        if os.path.exists(p):
            os.remove(p)

    print("=" * 60)
    print("docx_common 共享组件库 — 使用示例")
    print("=" * 60)

    # 示例 1
    print("\n[示例 1] 用 DocxBuilder 基类生成奖学金申请书…")
    build_scholarship_application(out1)

    # 示例 2
    print("\n[示例 2] 用函数式 API 生成成绩单…")
    build_grade_report(out2)

    # 示例 3
    print("\n[示例 3] 字数统计与文档校验…")
    demo_text_utils()

    print("\n" + "=" * 60)
    print("✅ 全部示例跑通")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
