#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国家奖学金申请书 docx 生成器

格式标准：A4 纸张，页边距上下 2.54cm 左右 2.5cm；标题黑体二号居中；
称呼顶格宋体小四全角冒号；正文宋体小四 1.5 倍行距首行缩进 2 字符；
主要获奖与科研成果表宋体五号居中；
"此致"另起一行空两格，"敬礼！"另起一行顶格；落款右对齐。

使用方式：
    python build.py --data data.json --out output.docx
    python build.py --demo --out demo.docx
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

FONT_SONG = "宋体"
FONT_HEI = "黑体"
FONT_TIMES = "Times New Roman"

SIZE_ER = Pt(22)            # 二号
SIZE_SI = Pt(14)            # 四号
SIZE_XIAO_SI = Pt(12)       # 小四
SIZE_WU = Pt(10.5)          # 五号

def set_run_font(run, font_name: str = FONT_SONG, size=SIZE_XIAO_SI, bold: bool = False, italic: bool = False, color: Optional[RGBColor] = None):
    run.font.name = font_name
    run.font.size = size
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:ascii'), font_name if font_name != FONT_SONG else FONT_TIMES)
    rFonts.set(qn('w:hAnsi'), font_name if font_name != FONT_SONG else FONT_TIMES)
    rFonts.set(qn('w:eastAsia'), font_name)
    rPr.append(rFonts)

def create_document() -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)
    return doc

def build_national_scholarship_doc(data: Dict[str, Any], output_path: str):
    doc = create_document()
    
    # 标题
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(12)
    run = title_p.add_run("国家奖学金申请书")
    set_run_font(run, FONT_HEI, SIZE_ER, bold=True)
    
    # 称呼
    salutation_p = doc.add_paragraph()
    salutation_p.paragraph_format.space_after = Pt(6)
    run = salutation_p.add_run("尊敬的学校领导、评审委员会老师：")
    set_run_font(run, FONT_SONG, SIZE_XIAO_SI, bold=True)
    
    # 正文段落
    paragraphs = data.get("paragraphs", [])
    for text in paragraphs:
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        p.paragraph_format.first_line_indent = Pt(24) # 2字符
        p.paragraph_format.space_after = Pt(6)
        r = p.add_run(text)
        set_run_font(r, FONT_SONG, SIZE_XIAO_SI)
        
    # 致敬语
    cz_p = doc.add_paragraph()
    cz_p.paragraph_format.first_line_indent = Pt(24)
    r = cz_p.add_run("此致")
    set_run_font(r, FONT_SONG, SIZE_XIAO_SI)
    
    jl_p = doc.add_paragraph()
    r = jl_p.add_run("敬礼！")
    set_run_font(r, FONT_SONG, SIZE_XIAO_SI, bold=True)
    
    # 落款
    signer_p = doc.add_paragraph()
    signer_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    signer_p.paragraph_format.space_before = Pt(12)
    applicant = data.get("applicant_name", "申请人：__________")
    date_str = data.get("application_date", "2026年  月  日")
    r1 = signer_p.add_run(f"{applicant}\n{date_str}")
    set_run_font(r1, FONT_SONG, SIZE_XIAO_SI)
    
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    doc.save(output_path)
    print(f"成功生成国家奖学金申请书: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="国家奖学金申请书 docx 生成器")
    parser.add_argument("--data", help="JSON 数据文件路径")
    parser.add_argument("--out", default="国家奖学金申请书.docx", help="输出 docx 文件路径")
    parser.add_argument("--demo", action="store_true", help="使用演示数据生成")
    args = parser.parse_args()
    
    demo_data = {
        "applicant_name": "申请人：张华",
        "application_date": "2026年10月15日",
        "paragraphs": [
            "我是来自计算机科学与技术专业2023级的本科生张华。在过去的一学年里，我始终保持严谨求实的学习态度，思想上积极要求进步，学业成绩与综合考评均名列专业第一名（1/120）。现郑重向学校提交国家奖学金申请。",
            "在思想政治方面，我坚定理想信念，作为一名中共预备党员，积极参加党支部组织生活与主题党日活动，时刻以优秀党员的标准严格要求自己，荣获校级'优秀共青团员'称号。",
            "在学业科研方面，我勤奋刻苦，本学年 GPA 为 3.92/4.0，所有核心课程成绩均在 90 分以上。在导师指导下主持国家级大学生创新训练项目 1 项，以第一作者在 CCF 推荐会议发表学术论文 1 篇，已申请国家发明专利 1 项。",
            "在综合素质与社会实践方面，我代表学校参加第十九届'挑战杯'全国大学生课外学术科技作品竞赛并斩获国家级一等奖，同时积极投身志愿服务活动，累计志愿服务时长超 120 小时。",
            "如果能够获得国家奖学金，这不仅是对我过去努力的肯定，更是激励我在科研探索与追求卓越道路上不断前行的强大动力。我将戒骄戒燥，继续脚踏实地，努力成长为担当民族复兴大任的时代新人。"
        ]
    }
    
    if args.demo:
        build_national_scholarship_doc(demo_data, args.out)
    elif args.data:
        with open(args.data, "r", encoding="utf-8") as f:
            data = json.load(f)
        build_national_scholarship_doc(data, args.out)
    else:
        build_national_scholarship_doc(demo_data, args.out)

if __name__ == "__main__":
    main()
