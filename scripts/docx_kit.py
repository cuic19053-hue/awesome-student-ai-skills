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
# 版心可用高度：A4 29.7cm − 上 2.5 − 下 2.5 = 24.7cm，再扣章标题与间距约 1.7cm
_SIGN_AVAIL_CM = 23.0
# 调试用：强制栏高（cm），0 表示按公式自适应
_SIGN_FORCE_CM = 0.0

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
    # 文档属性：默认会留下 "python-docx" 的作者名，正式材料里像模板残留
    cp = doc.core_properties
    cp.author = "示例文档"
    cp.last_modified_by = "示例文档"
    cp.comments = "虚构示例，仅用于展示申报书排版与图表规范"
    cp.keywords = "学生申报书; 示例; 排版规范"
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


def _outline(p, lvl: int):
    """给标题段打大纲级别，让 Word 导航窗格 / 自动目录能识别结构。

    不套内置 Heading 样式是刻意的：Heading 1/2 自带字体、颜色、段前后与行距，
    会把已经调好的版式全部推翻（字号变小、行距变 1.08、标题变蓝）。
    只写 w:outlineLvl，视觉零变化，但结构信息完整。
    """
    pPr = p._p.get_or_add_pPr()
    el = OxmlElement("w:outlineLvl")
    el.set(qn("w:val"), str(lvl))
    pPr.insert_element_before(el, "w:rPr", "w:sectPr")


def h1(doc, text, size=15):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(14)
    pf.space_after = Pt(7)
    pf.line_spacing = 1.5
    pf.keep_with_next = True          # 标题不与正文分离
    pf.keep_together = True
    set_font(p.add_run(text), HEI, size, True)
    _outline(p, 0)
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
    _outline(p, 1)
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
    no = _next_tab_no(doc)
    _cite_prev(doc, "表", no)           # 正文补「如表 N 所示」
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(6)
    pf.space_after = Pt(2)
    pf.line_spacing = 1.2
    pf.keep_with_next = True        # 表题不与表格分离
    pf.keep_together = True
    set_font(p.add_run(f"表 {no}　{text}"), HEI, 10.5, False, INK)
    return p


def figure(doc, filename, caption, width_cm=14.8, max_h_cm=7.0):
    path = FIG / filename
    if not path.exists():
        print(f"  ⚠ 缺少配图 {filename}，跳过")
        return

    # 图号自动生成：调用方若已写「图 N　」，剥掉后重新编号
    caption = re.sub(r"^图\s*\d+[　\s]*", "", caption)
    no = _next_fig_no(doc)
    caption = f"图 {no}　{caption}"
    _cite_prev(doc, "图", no)           # 正文补「如图 N 所示」

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


def _set_para_text(p, text):
    """整段替换文本（保留段落格式与首个 run 的字体）。"""
    runs = p.runs
    if not runs:
        return
    runs[0].text = text
    for r in runs[1:]:
        r.text = ""


_CAPTION_RE = re.compile(r"^[图表] \d+　")


def _cite_prev(doc, kind, no):
    """在图表之前的那段正文里补上编号引用。

    国标要求图表既有编号、又在正文中被引用。原来的稿子全用「如下图」这类
    无编号指代，等于编号形同虚设——读者在十几页里没法凭正文定位到第几张图。
    这里只改紧邻的那一段：以冒号收尾的引导句换成「如图 N 所示：」，
    否则在句末补「（见图 N）」。
    """
    for p in reversed(doc.paragraphs):
        t = p.text.strip()
        if not t:
            continue
        if _CAPTION_RE.match(t):          # 上一张图的图注，不住回改
            return
        if not p.runs or p.runs[0].bold:  # 标题不回改
            return
        # 正文已经点了这张图/表的号（如「构成见图 7、明细见表 5」），不再重复补
        if re.search(rf"{kind}\s*{no}(?!\d)", t):
            return
        cite = f"如{kind} {no} 所示"
        if t.endswith(("：", ":")):
            head = t[:-1]
            head = re.sub(r"[，,]?\s*(如下|见下|以下|下面)$", "", head)
            _set_para_text(p, f"{head}{cite}：")
        elif t.endswith(("。", "！", "？")):
            _set_para_text(p, f"{t[:-1]}（见{kind} {no}）。")
        else:
            _set_para_text(p, f"{t}（见{kind} {no}）")
        return


# 正文引用：排除「发表 14 篇」「代表 3 项」这类词内假阳性
_CITE_FIG_RE = re.compile(r"(?<![意试企地蓝构])图\s*(\d+)(?!\d)")
_CITE_TAB_RE = re.compile(r"(?<![发代图报仪外])表\s*(\d+)(?!\d)")
_CAP_ANY_RE = re.compile(r"^([图表])\s*(\d+)[\s　]")


def _append_cite(p, kind, no):
    """在段末补/并引用括号。已有同类括号时并入，避免「（见表 4）（见表 5）」。"""
    t = p.text.rstrip()
    m = re.search(rf"（见{kind}\s*([\d、]+)）\s*$", t)
    if m:
        nums = m.group(1).split("、")
        if str(no) not in nums:
            nums.append(str(no))
            _set_para_text(p, t[:m.start()] + f"（见{kind} {'、'.join(nums)}）")
        return
    if t.endswith(("。", "！", "？")):
        _set_para_text(p, t[:-1] + f"（见{kind} {no}）{t[-1]}")
    elif t.endswith(("：", ":")):
        _set_para_text(p, t[:-1] + f"（见{kind} {no}）：")
    else:
        _set_para_text(p, f"{t}（见{kind} {no}）")


def cite_all(doc) -> list:
    """构建收尾统一补齐图表引用——任何编号图/表都必须被正文提及至少一次。

    `_cite_prev()` 只在输出图表的那一刻回改紧邻的上一段，遇到三种结构就补不上：
    ① 章标题后直接接表（上一段是加粗标题）；② 图后紧跟表（上一段是图注）；
    ③ 连续两张表（上一块是表格）。这三种在申报书里都很常见。

    这里改为在全文层面兜底：从图表位置向前找最近的一段正文（跳过空段、题注、
    图、表），若先撞上标题，则退到该标题之后的第一段正文补。补引用时按标点
    选「（见表 N）。」或「见表 N：」，同段已有同类括号则并入，不叠第二个括号。

    返回补齐记录，便于构建日志核对。
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = list(doc.element.body.iterchildren())
    anchors = []          # (kind, no, idx)
    texts = {}            # idx -> Paragraph
    for i, ch in enumerate(body):
        if ch.tag != qn("w:p"):
            continue
        p = Paragraph(ch, doc)
        t = p.text.strip()
        if not t:
            continue
        m = _CAP_ANY_RE.match(t)
        if m:
            anchors.append((m.group(1), int(m.group(2)), i))
            continue
        texts[i] = p

    cited = {"图": set(), "表": set()}
    for p in texts.values():
        cited["图"].update(int(x) for x in _CITE_FIG_RE.findall(p.text))
        cited["表"].update(int(x) for x in _CITE_TAB_RE.findall(p.text))

    log = []
    for kind, no, idx in anchors:
        if no in cited[kind]:
            continue
        target, head = None, None
        j = idx - 1
        while j >= 0:
            ch = body[j]
            if ch.tag == qn("w:tbl"):
                j -= 1
                continue
            p = Paragraph(ch, doc)
            t = p.text.strip()
            if not t or _CAP_ANY_RE.match(t) or p._p.findall(".//" + qn("w:drawing")):
                j -= 1
                continue
            if not p.runs or p.runs[0].bold:      # 撞到标题
                head = j
                break
            target = p
            break
        if target is None and head is not None:
            # 标题下直接接图表：改从图表之后找本篇第一段正文（跨过表体/空段），
            # 遇到下一个标题就停——否则会把「见表 N」补到下一章的正文里。
            j = idx + 1
            while j < len(body):
                ch = body[j]
                if ch.tag == qn("w:p"):
                    p = Paragraph(ch, doc)
                    t = p.text.strip()
                    if t and not _CAP_ANY_RE.match(t) and not p._p.findall(".//" + qn("w:drawing")):
                        if p.runs and p.runs[0].bold:
                            break
                        target = p
                        break
                j += 1
        if target is None:
            continue
        _append_cite(target, kind, no)
        cited[kind].add(no)
        log.append(f"{kind} {no}")
    return log



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
        row = t.add_row()
        # 行级不可拆分：信息表行数少，一旦跨页会把「项目负责人」和姓名拆到两页
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        cells = row.cells
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


def _spacer(doc, h_cm: float):
    """定高占位段。用精确行距撑高，不用空段落——空段落的高度随正文字号/行距漂移。"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Cm(h_cm)
    p.add_run("")
    return p


def cover(doc, org: str, doc_kind: str, title: str, subtitle: str = "",
          info=None, red_header: bool = False):
    """封面：机构名 + 文档类型 + 项目名 + 信息表。

    顶部留白用定高占位段控制。实测原「3 个空段落」版本，11 份封面的信息表
    底边落在页面 55%～60% 处，下半页留白 42%～46%，视觉上明显上重下空。
    改为按内容高度给不同留白，使上下留白接近（红头版内容更高，留白相应减小）。
    """
    _spacer(doc, 6.0 if red_header else 7.0)

    if red_header:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(24)
        set_font(p.add_run(org), HEI, 30, True, RED)
    else:
        # 红头版已用 30pt 红字打了机构全称，此处不再重复一遍——早期版本两行文字
        # 完全相同（红→黑各一行），是封面最扎眼的冗余。
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(10)
        set_font(p.add_run(org), HEI, 22, True)

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


def signature_block(doc, titles, box_h_cm=None):
    """审核意见区：每个意见栏压成「一行」，保证整栏不可被拆到两页。

    早期做法是一栏 = 标题条 / 书写区 / 签字行 三行，靠 keep_with_next 把三行
    粘起来。但 keep_with_next 是段落属性，对「表格行之间」的约束在不同渲染器
    里实现不一——LibreOffice/Word 会整块换页，腾讯文档预览之类的渲染器不认，
    于是出现「学院审核意见」标题孤零零留在页底、书写区和签字行被甩到下一页。

    改成一栏一行、栏内三个段落（栏内分隔线用段落边框画），
    配合行级 cantSplit：任何渲染器都无法在栏内断开，
    最坏情况退化为「整栏移到下一页」，每栏仍是完整的签字单元。

    栏高按栏数反算，使整块约占总版心的 90%：早期固定 1.8cm 时，
    2 栏版本在末页只占三分之一页、下面半页全空，且栏高不够手写评语。
    """
    t = doc.add_table(rows=0, cols=1)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False

    if box_h_cm is None:
        n = max(1, len(titles))
        box_h_cm = min(7.0, max(3.0, (_SIGN_AVAIL_CM * 0.85 - 2.4 * n) / n))
    if _SIGN_FORCE_CM:
        box_h_cm = _SIGN_FORCE_CM

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
