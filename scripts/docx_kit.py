#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""申报书 docx 排版的公共构件（供各 demo 生成脚本复用）。

排版基准：A4、公文页边距、宋体小四、1.5 倍行距、首行缩进 2 字符。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "build" / "figures"

# 正文可用宽度：A4 21cm − 左 3.0 − 右 2.6 = 15.4cm
TEXT_W = 15.4

HEI = "黑体"
SONG = "宋体"
KAI = "楷体"
INK = RGBColor(0x11, 0x18, 0x27)
GREY = RGBColor(0x6B, 0x72, 0x80)
RED = RGBColor(0xB9, 0x1C, 0x1C)


def set_font(run, name=SONG, size=12, bold=False, color=INK):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    return run


def _field_run(p, instr: str):
    """在段落里插入一个会随打印刷新取值的域（PAGE / NUMPAGES）。"""
    r1 = p.add_run()
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "begin")
    r1._r.append(fc)

    r2 = p.add_run()
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = f" {instr} "
    r2._r.append(it)

    r3 = p.add_run()
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    r3._r.append(sep)

    r4 = p.add_run("1")          # 占位值，打开时由 Word/WPS 刷新

    r5 = p.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    r5._r.append(end)

    for r in (r1, r2, r3, r4, r5):
        set_font(r, SONG, 9, False, GREY)
    return p


def _add_page_footer(doc):
    """页脚居中「第 X 页　共 Y 页」，封面不显示（评审装订后便于定位）。"""
    sec = doc.sections[0]
    sec.different_first_page_header_footer = True
    p = sec.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    set_font(p.add_run("第 "), SONG, 9, False, GREY)
    _field_run(p, "PAGE")
    set_font(p.add_run(" 页　共 "), SONG, 9, False, GREY)
    _field_run(p, "NUMPAGES")
    set_font(p.add_run(" 页"), SONG, 9, False, GREY)


def new_doc() -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.top_margin, sec.bottom_margin = Cm(2.54), Cm(2.54)
    sec.left_margin, sec.right_margin = Cm(3.0), Cm(2.6)
    style = doc.styles["Normal"]
    style.font.name = SONG
    style.font.size = Pt(12)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), SONG)
    _add_page_footer(doc)
    return doc


def para(doc, text="", size=12, bold=False, name=SONG, align=None,
         first_indent=True, space_after=6, line=1.5, color=INK, keep_next=False):
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
    if keep_next:
        # 引导句（「……如下：」）不与后面的图/表分离
        pf.keep_with_next = True
        pf.keep_together = True
    if text:
        set_font(p.add_run(text), name, size, bold, color)
    return p


def h1(doc, text, size=15):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(14)
    pf.space_after = Pt(7)
    pf.line_spacing = 1.5
    pf.keep_with_next = True          # 标题不与正文分离
    pf.keep_together = True
    set_font(p.add_run(text), HEI, size, True)
    return p


def h2(doc, text, size=12.5):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(10)
    pf.space_after = Pt(5)
    pf.line_spacing = 1.5
    pf.keep_with_next = True
    pf.keep_together = True
    set_font(p.add_run(text), HEI, size, True)
    return p


def cn_num(n: int) -> str:
    """1..99 的中文序号（十一、二十一），用于章节自动编号。"""
    digits = "一二三四五六七八九"
    if n <= 0:
        return ""
    if n < 10:
        return digits[n - 1]
    if n < 20:
        return "十" + (digits[n - 11] if n > 10 else "")
    tens, ones = divmod(n, 10)
    return digits[tens - 1] + "十" + (digits[ones - 1] if ones else "")


def _next_fig_no(doc) -> int:
    """文档级配图计数器：按出现顺序自动编号，避免手工写死导致错号。"""
    n = getattr(doc, "_fig_counter", 0) + 1
    doc._fig_counter = n
    return n


_CN_DIGIT = {c: i + 1 for i, c in enumerate("一二三四五六七八九")}


def cn_int(s: str) -> int:
    """中文序号转整数（一→1，十一→11，二十九→29），识别失败返回 0。"""
    s = s.strip()
    if not s:
        return 0
    if "十" not in s:
        return _CN_DIGIT.get(s[0], 0) if len(s) == 1 else 0
    head, _, tail = s.partition("十")
    tens = _CN_DIGIT.get(head, 0) if head else 1
    ones = _CN_DIGIT.get(tail, 0) if tail else 0
    return tens * 10 + ones


_H1_RE = re.compile(r"^([一二三四五六七八九十]+)、")
_SUB_RE = re.compile(r"^(\d+)\.(\d+)(\s+\S.*)$")


def renumber_subheads(doc) -> list:
    """二级标题按所在章重排为「章号.序」，保证连续且与章序号对应。

    手工补写内容时最容易出现的硬伤：某章小节从 2.2 起跳、4.1/4.2 缺失。
    评审翻到「2.2」却找不到「2.1」会直接判定材料拼凑，故统一重排。
    """
    cur_ch, seq, log = 0, 0, []
    for p in doc.paragraphs:
        t = p.text.strip()
        if not t or not p.runs:
            continue
        if not p.runs[0].bold:
            continue
        m1 = _H1_RE.match(t)
        if m1:
            cur_ch = cn_int(m1.group(1))
            seq = 0
            continue
        m = _SUB_RE.match(t)
        if not m or not cur_ch:
            continue
        seq += 1
        old = f"{m.group(1)}.{m.group(2)}"
        new = f"{cur_ch}.{seq}"
        if old == new:
            continue
        r0 = p.runs[0]
        if old not in r0.text:
            print(f"  ⚠ 小节编号跨 run，未重排：{t[:30]}")
            continue
        r0.text = r0.text.replace(old, new, 1)
        log.append(f"{old}→{new} {m.group(3).strip()[:18]}")
    return log



def _next_tab_no(doc) -> int:
    """文档级表格计数器：图、表各自独立编号。"""
    n = getattr(doc, "_tab_counter", 0) + 1
    doc._tab_counter = n
    return n


# 当前正在构建的文档键（供表题登记表按文档取题），由 build_demos 设置
CURRENT_DOC = ""


def _table_caption(doc, header, explicit=None):
    """表题文本（不含「表 N」前缀）。显式给出优先，否则查登记表。"""
    if explicit:
        return explicit
    try:
        from table_captions import CAPTIONS
    except ImportError:
        return None
    key = (CURRENT_DOC, tuple(str(h) for h in header))
    val = CAPTIONS.get(key)
    if val is None:
        val = CAPTIONS.get(("*", tuple(str(h) for h in header)))
    if val is None:
        print(f"  ⚠ 缺表题：{CURRENT_DOC} / {' | '.join(map(str, header))}")
        return None
    if isinstance(val, (list, tuple)):
        used = getattr(doc, "_tab_used", None)
        if used is None:
            used = doc._tab_used = {}
        i = used.get(key, 0)
        used[key] = i + 1
        return val[i] if i < len(val) else val[-1]
    return val


def table_caption(doc, header, explicit=None):
    """在表格上方输出「表 N　表题」（黑体五号居中），并与表格绑定同页。"""
    text = _table_caption(doc, header, explicit)
    if not text:
        return None
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(6)
    pf.space_after = Pt(2)
    pf.line_spacing = 1.2
    pf.keep_with_next = True        # 表题不与表格分离
    pf.keep_together = True
    set_font(p.add_run(f"表 {_next_tab_no(doc)}　{text}"), HEI, 10.5, False, INK)
    return p


def figure(doc, filename, caption, width_cm=14.8, max_h_cm=7.0):
    path = FIG / filename
    if not path.exists():
        print(f"  ⚠ 缺少配图 {filename}，跳过")
        return

    # 图号自动生成：调用方若已写「图 N　」，剥掉后重新编号
    caption = re.sub(r"^图\s*\d+[　\s]*", "", caption)
    caption = f"图 {_next_fig_no(doc)}　{caption}"

    # 按图片纵横比约束高度，避免过高的图放不进页面而把整页撑出空白
    w_cm = min(width_cm, TEXT_W)
    try:
        from PIL import Image
        with Image.open(path) as im:
            iw, ih = im.size
        if iw > 0:
            h_at_w = w_cm * ih / iw
            if h_at_w > max_h_cm:
                w_cm = max_h_cm * iw / ih
    except Exception:
        pass

    # 图片段落与图注绑定，避免图在一页、图注在下一页
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.keep_together = True
    p.add_run().add_picture(str(path), width=Cm(w_cm))

    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(0)
    cap.paragraph_format.space_after = Pt(10)
    cap.paragraph_format.keep_together = True
    set_font(cap.add_run(caption), SONG, 10.5, False, GREY)


def _table_setup(t, n_cols, widths):
    """固定布局 + 单元格内边距 + 列宽归一化。"""
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False

    tblPr = t._tbl.tblPr
    # 固定列宽（否则 Word/WPS 会重新自动布局，列宽形同虚设）
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)

    # 单元格内边距，避免文字贴边
    mar = OxmlElement("w:tblCellMar")
    for side, val in (("top", 50), ("bottom", 50), ("left", 100), ("right", 100)):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:w"), str(val))
        e.set(qn("w:type"), "dxa")
        mar.append(e)
    tblPr.append(mar)

    # 列宽归一化到正文宽度
    if widths:
        total = sum(widths)
        widths = [w * TEXT_W / total for w in widths]
    else:
        widths = [TEXT_W / n_cols] * n_cols

    for i, w in enumerate(widths):
        t.columns[i].width = Cm(w)
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)
    return widths


def _table_spacer(doc):
    """表格后的间距，避免正文贴住表格底边框、或两张表粘连。"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = Pt(12)
    set_font(p.add_run(""), SONG, 8)
    return p


def table(doc, header: Sequence[str], rows: Iterable[Sequence], widths=None,
          bold_last=False, caption=None):
    rows = list(rows)
    n_cols = len(header)
    table_caption(doc, header, caption)      # 表题在上，与表格同页
    t = doc.add_table(rows=1, cols=n_cols)
    t.style = "Table Grid"

    # 表头
    hdr = t.rows[0]
    for i, h in enumerate(header):
        cell = hdr.cells[i]
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        set_font(p.add_run(h), HEI, 10.5, True)

    # 跨页时重复表头
    trPr = hdr._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:tblHeader"))
    trPr.append(OxmlElement("w:cantSplit"))

    for ri, row in enumerate(rows):
        r = t.add_row()
        r._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))  # 行不跨页拆开
        cells = r.cells
        is_last = bold_last and ri == len(rows) - 1
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.15
            if i > 0:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_font(p.add_run(str(v)), SONG, 10.5, is_last)

    _table_setup(t, n_cols, widths)

    # 短表整表不跨页：示例里的数据表最多 9 行、高不超过 12cm，
    # 完全可以整张放在一页。否则最常见的结果是「90% 在上一页，
    # 最后 1 行带着重复表头孤零零跑到下一页」，比整表换页难看得多。
    # 超长表（>12 行）不绑，避免反而制造整页留白。
    if len(t.rows) <= 13:
        n = len(t.rows)
        for i, row in enumerate(t.rows):
            if i == n - 1:
                continue
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.keep_with_next = True
                    p.paragraph_format.keep_together = True

    _table_spacer(doc)
    return t


def kv_table(doc, items, k_w=4.6, v_w=10.8, k_align=WD_ALIGN_PARAGRAPH.RIGHT):
    t = doc.add_table(rows=0, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    t._tbl.tblPr.append(layout)
    for k, v in items:
        cells = t.add_row().cells
        cells[0].width, cells[1].width = Cm(k_w), Cm(v_w)
        p0 = cells[0].paragraphs[0]
        p0.alignment = k_align
        p0.paragraph_format.space_before = Pt(0)
        p0.paragraph_format.space_after = Pt(0)
        set_font(p0.add_run(k if k.endswith(("：", ":")) else k + "："), SONG, 12)
        p1 = cells[1].paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p1.paragraph_format.space_before = Pt(0)
        p1.paragraph_format.space_after = Pt(0)
        set_font(p1.add_run(v), SONG, 12)
    for i, w in enumerate((k_w, v_w)):
        t.columns[i].width = Cm(w)
    return t


def cover(doc, org: str, doc_kind: str, title: str, subtitle: str = "",
          info=None, red_header: bool = False):
    """封面：机构名 + 文档类型 + 项目名 + 信息表。"""
    for _ in range(3):
        doc.add_paragraph()

    if red_header:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(24)
        set_font(p.add_run(org), HEI, 30, True, RED)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    set_font(p.add_run(org), HEI, 22 if not red_header else 18, True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(34)
    set_font(p.add_run(doc_kind), HEI, 26, True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    set_font(p.add_run(title), HEI, 16, True)

    if subtitle:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(56)
        set_font(p.add_run(subtitle), SONG, 12, False, GREY)
    else:
        doc.add_paragraph()

    if info:
        kv_table(doc, info)

    doc.add_page_break()


def _para_border(p, edge="bottom", sz=6, color="7A7A7A"):
    """给段落画一条边框线（代替表格内部分隔线，使一栏压成单行后仍保留视觉分隔）。"""
    pPr = p._p.get_or_add_pPr()
    pBdr = pPr.find(qn("w:pBdr"))
    if pBdr is None:
        pBdr = OxmlElement("w:pBdr")
        pPr.append(pBdr)
    e = OxmlElement(f"w:{edge}")
    e.set(qn("w:val"), "single")
    e.set(qn("w:sz"), str(sz))
    e.set(qn("w:space"), "1")
    e.set(qn("w:color"), color)
    pBdr.append(e)


def signature_block(doc, titles, box_h_cm=1.8):
    """审核意见区：每个意见栏压成「一行」，保证整栏不可被拆到两页。

    早期做法是一栏 = 标题条 / 书写区 / 签字行 三行，靠 keep_with_next 把三行
    粘起来。但 keep_with_next 是段落属性，对「表格行之间」的约束在不同渲染器
    里实现不一——LibreOffice/Word 会整块换页，腾讯文档预览之类的渲染器不认，
    于是出现「学院审核意见」标题孤零零留在页底、书写区和签字行被甩到下一页。

    改成一栏一行、栏内三个段落（栏内分隔线用段落边框画），
    配合行级 cantSplit：任何渲染器都无法在栏内断开，
    最坏情况退化为「整栏移到下一页」，每栏仍是完整的签字单元。
    """
    t = doc.add_table(rows=0, cols=1)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False

    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    t._tbl.tblPr.append(layout)

    for title in titles:
        r = t.add_row()
        cell = r.cells[0]
        cell.width = Cm(TEXT_W)

        # ① 标题条
        p1 = cell.paragraphs[0]
        p1.paragraph_format.space_before = Pt(2)
        p1.paragraph_format.space_after = Pt(2)
        set_font(p1.add_run(title), HEI, 10.5, True)
        _para_border(p1, "bottom")

        # ② 书写区：空段落按精确行距撑出固定高度（供手写/盖章）
        p2 = cell.add_paragraph()
        pf2 = p2.paragraph_format
        pf2.space_before = Pt(0)
        pf2.space_after = Pt(0)
        pf2.line_spacing = Cm(box_h_cm)

        # ③ 签字行
        p3 = cell.add_paragraph()
        p3.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p3.paragraph_format.space_before = Pt(4)
        p3.paragraph_format.space_after = Pt(4)
        set_font(p3.add_run("签字：＿＿＿＿＿＿＿＿　　　日期：　　年　　月　　日"),
                 SONG, 10.5, False, GREY)
        _para_border(p3, "top")

    t.columns[0].width = Cm(TEXT_W)
    n = len(t.rows)
    for i, row in enumerate(t.rows):
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        # 栏间仍整块绑定：支持的渲染器里整块换页，不支持的至少不会断在栏内
        if i < n - 1:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.keep_with_next = True
                    p.paragraph_format.keep_together = True
    _table_spacer(doc)


def render_blocks(doc, blocks):
    """按 blocks 描述渲染章节内容。

    支持：("p", text) / ("h2", text) / ("fig", file, caption[, width])
          / ("table", header, rows[, widths]) / ("kv", items)
    """
    for b in blocks:
        kind = b[0]
        if kind == "p":
            text = b[1]
            indent = b[2] if len(b) > 2 else True
            size = b[3] if len(b) > 3 else 12
            # 引导句自动绑定后文，避免「……如下：」孤零零留在页底
            keep = b[4] if len(b) > 4 else text.rstrip().endswith(("：", ":"))
            para(doc, text, size=size, first_indent=indent, keep_next=keep)
        elif kind == "h2":
            h2(doc, b[1])
        elif kind == "fig":
            figure(doc, b[1], b[2], b[3] if len(b) > 3 else 15.2)
        elif kind == "table":
            table(doc, b[1], b[2],
                  b[3] if len(b) > 3 else None,
                  b[4] if len(b) > 4 else False,
                  b[5] if len(b) > 5 else None)
        elif kind == "kv":
            kv_table(doc, b[1])
        else:
            raise ValueError(f"未知 block 类型：{kind}")
