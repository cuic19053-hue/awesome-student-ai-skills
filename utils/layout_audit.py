#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""layout_audit.py — 申报书排版硬指标审计器
====================================================

把「国奖级排版」拆成可机器验证的条款，任何 agent、任何宿主、任何模型
生成的 .docx 都能用同一把尺子量。规范条文见 `references/layout_standard.md`。

设计取舍
--------
1. **静态优先**：只用 python-docx 读 XML，不依赖 LibreOffice。CI（Ubuntu
   runner 无 soffice）也能跑，因此「结构/闭环/元数据」三类指标永不失效。
2. **渲染可选**：加 `--render` 才调 soffice 转 PDF，再用 PyMuPDF 查跨页表、
   图注分离、页底留白。这几项只有真正排版后才能看见，属于加分项而非门禁。
3. **可解释**：每条 FAIL 附带 `fix` 提示，直接给出该改哪个 API，避免
   agent 知道不合格却不知道从哪下手。
4. **不乱判**：无图、无表、无参考文献的文档（入团申请书、思想汇报）不在
   对应条款上扣分，规则自动 skip。

用法
----
    python utils/layout_audit.py examples/demos
    python utils/layout_audit.py out.docx --render
    python utils/layout_audit.py examples/demos --json --min-score 90

退出码：0 达标 / 1 未达标（有 FAIL，或 --strict 下有 WARN）

作者：awesome-student-ai-skills
版本：1.0.0
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

# ============================================================
# 阈值（改这里即可整体升降标准松紧）
# ============================================================

MIN_SCORE = 90              # 达标线
FAIL_PENALTY = 12           # 每条 FAIL 扣分
WARN_PENALTY = 3            # 每条 WARN 扣分
BIG_TABLE_ROWS = 8          # 超过此行数视为「大表」，必须有表头重复标记
TAIL_GAP_CM = 8.0           # 末页留白容忍上限
PAGE_GAP_CM = 9.0           # 中间页底部留白容忍上限（A4 版心 24.7cm，9cm≈版心 1/3）
PAGE_GAP_RATIO = 0.40       # 超出 PAGE_GAP_CM 的页面占比上限
                            # 封面（第 1 页）与末页不计入——两者另有 R05 与封面条款
                            #
                            # 为什么放到 1/3 版心：整图/整表换页必然在上一页留白，
                            # 7~9cm 是「一张图放不下」的正常结果。卡到 6cm 会与
                            # R01（表不跨页）、R02（图注不分家）直接打架，
                            # 逼着 agent 把图压小或把表拆开——那才是真的错。

CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

CAP_FIG = re.compile(r"^图\s*(\d+)\u3000")     # 图注：编号后必须是全角空格
CAP_TAB = re.compile(r"^表\s*(\d+)\u3000")
REF_ITEM = re.compile(r"^\[(\d+)\]")
H1 = re.compile(r"^([一二三四五六七八九十]+)、")
H2 = re.compile(r"^(\d+)\.(\d+)")
CITE_FIG = re.compile(r"(?<![意试企地蓝构])图\s*(\d+)(?!\d)")
CITE_TAB = re.compile(r"(?<![发代图报仪外])表\s*(\d+)(?!\d)")
CITE_REF = re.compile(r"\[(\d+)\]")
PLACEHOLDER = re.compile(r"(TODO|FIXME|XXX|xxx|待填|待补充|\{\{.*?\}\}|\[待|占位)")


def cn_int(s: str) -> int:
    """中文序号转整数（只处理 1~99，足够覆盖申报书章节）。"""
    if s in CN_DIGITS:
        return CN_DIGITS[s]
    if s.startswith("十"):
        return 10 + CN_DIGITS.get(s[1:], 0)
    if "十" in s:
        a, _, b = s.partition("十")
        return CN_DIGITS.get(a, 0) * 10 + (CN_DIGITS.get(b, 0) if b else 0)
    return 0


# ============================================================
# 结果模型
# ============================================================

@dataclass
class Issue:
    rule: str
    level: str          # FAIL / WARN
    detail: str
    fix: str = ""


@dataclass
class Report:
    path: str
    issues: List[Issue] = field(default_factory=list)
    passed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def fails(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "FAIL"]

    @property
    def warns(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "WARN"]

    @property
    def score(self) -> int:
        return max(0, 100 - FAIL_PENALTY * len(self.fails) - WARN_PENALTY * len(self.warns))


# ============================================================
# 基础读取
# ============================================================

def iter_blocks(doc):
    """按文档顺序产出 ('p', Paragraph) / ('t', Table)，用于判断题注与主体的位置关系。"""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield "p", Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield "t", Table(child, doc)


def para_has_drawing(p: Paragraph) -> bool:
    return bool(p._p.findall(".//" + qn("w:drawing")))


def keep_with_next(p: Paragraph) -> bool:
    pPr = p._p.find(qn("w:pPr"))
    return pPr is not None and pPr.find(qn("w:keepNext")) is not None


def row_cant_split(row) -> bool:
    trPr = row._tr.find(qn("w:trPr"))
    return trPr is not None and trPr.find(qn("w:cantSplit")) is not None


def row_is_header(row) -> bool:
    trPr = row._tr.find(qn("w:trPr"))
    return trPr is not None and trPr.find(qn("w:tblHeader")) is not None


def text_of(p: Paragraph) -> str:
    return p.text.strip()


# ============================================================
# 结构类：章号 / 节号 / 图表编号
# ============================================================

def check_chapter_sequence(rep: Report, blocks) -> None:
    seen: List[Tuple[int, str]] = []
    for kind, blk in blocks:
        if kind != "p":
            continue
        t = text_of(blk)
        m = H1.match(t)
        if m:
            seen.append((cn_int(m.group(1)), t))
    if len(seen) < 2:
        rep.skipped.append("L01 章号连续（章数不足 2）")
        return
    nums = [n for n, _ in seen]
    bad = [(i + 1, nums[i], nums[i + 1]) for i in range(len(nums) - 1) if nums[i + 1] != nums[i] + 1]
    if bad:
        first = bad[0]
        rep.issues.append(Issue(
            "L01", "FAIL",
            f"章号不连续：第 {first[0]} 个章标题是「{dict((n, t) for n, t in seen).get(first[1], first[1])}」"
            f"（{first[1]}）后接「{dict((n, t) for n, t in seen).get(first[2], first[2])}」（{first[2]}），"
            f"共 {len(bad)} 处跳号/重号",
            "章标题用 `h1()` 按顺序输出，不要手写序号；补章后用 renumber_subheads() 统一重排小节号"))
    else:
        rep.passed.append("L01 章号连续")


def check_section_sequence(rep: Report, blocks) -> None:
    cur_ch, expect, bad = 0, 1, []
    for kind, blk in blocks:
        if kind != "p":
            continue
        t = text_of(blk)
        m1 = H1.match(t)
        if m1:
            cur_ch, expect = cn_int(m1.group(1)), 1
            continue
        m2 = H2.match(t)
        if not m2 or not cur_ch:
            continue
        ch, seq = int(m2.group(1)), int(m2.group(2))
        if ch != cur_ch or seq != expect:
            bad.append((t[:24], f"应为 {cur_ch}.{expect}"))
        expect += 1
    if not cur_ch:
        rep.skipped.append("L02 节号连续（无编号小节）")
        return
    if bad:
        rep.issues.append(Issue(
            "L02", "FAIL",
            f"{len(bad)} 处小节编号与所属章不符，例：「{bad[0][0]}」{bad[0][1]}",
            "小节号由 renumber_subheads(doc) 按「所在章.序」自动重排，不要人工维护"))
    else:
        rep.passed.append("L02 节号连续")


def check_numbering_gap(rep: Report, blocks) -> None:
    figs, tabs = [], []
    for kind, blk in blocks:
        if kind != "p":
            continue
        t = text_of(blk)
        m = CAP_FIG.match(t)
        if m:
            figs.append(int(m.group(1)))
        m = CAP_TAB.match(t)
        if m:
            tabs.append(int(m.group(1)))
    problems = []
    for name, seq in (("图", figs), ("表", tabs)):
        if not seq:
            continue
        dup = {n for n in seq if seq.count(n) > 1}
        if dup:
            problems.append(f"{name}编号重复：{sorted(dup)}")
        if seq != list(range(1, len(seq) + 1)):
            problems.append(f"{name}编号不连续：{seq[:12]}{'…' if len(seq) > 12 else ''}")
    rep.stats["figs"] = len(figs)
    rep.stats["tabs"] = len(tabs)
    if problems:
        rep.issues.append(Issue(
            "L03", "FAIL", "；".join(problems),
            "编号由计数器统一分配（_next_tab_no / 图注模板），不要写死数字"))
    elif figs or tabs:
        rep.passed.append(f"L03 编号连续（图 {len(figs)} · 表 {len(tabs)}）")
    else:
        rep.skipped.append("L03 编号连续（无编号图表）")


# ============================================================
# 闭环类：图表引用 / 参考文献
# ============================================================

def check_citation_closure(rep: Report, blocks) -> None:
    caps_fig, caps_tab, cited_fig, cited_tab = [], [], set(), set()
    for kind, blk in blocks:
        if kind != "p":
            continue
        t = text_of(blk)
        mf, mt = CAP_FIG.match(t), CAP_TAB.match(t)
        if mf:
            caps_fig.append(int(mf.group(1)))
            continue                      # 题注本身不算正文引用
        if mt:
            caps_tab.append(int(mt.group(1)))
            continue
        if para_has_drawing(blk):
            continue
        cited_fig.update(int(x) for x in CITE_FIG.findall(t))
        cited_tab.update(int(x) for x in CITE_TAB.findall(t))
    if not caps_fig and not caps_tab:
        rep.skipped.append("L04 图表引用闭环（无编号图表）")
        return

    orphan_fig = [n for n in caps_fig if n not in cited_fig]
    orphan_tab = [n for n in caps_tab if n not in cited_tab]
    over_fig = [n for n in cited_fig if caps_fig and n > max(caps_fig)]
    over_tab = [n for n in cited_tab if caps_tab and n > max(caps_tab)]
    msgs = []
    if orphan_fig:
        msgs.append(f"图 {orphan_fig} 从未被正文引用")
    if orphan_tab:
        msgs.append(f"表 {orphan_tab} 从未被正文引用")
    if over_fig:
        msgs.append(f"正文引用了不存在的 图 {over_fig}")
    if over_tab:
        msgs.append(f"正文引用了不存在的 表 {over_tab}")
    if msgs:
        rep.issues.append(Issue(
            "L04", "FAIL", "；".join(msgs),
            "图表输出时回改前一段正文，补「如图 N 所示」/「（见表 N）」，"
            "见 docx_kit._cite_prev()"))
    else:
        rep.passed.append(f"L04 图表引用闭环（{len(caps_fig)} 图 / {len(caps_tab)} 表，全部有引用）")


def check_references(rep: Report, blocks) -> None:
    items: List[int] = []
    in_ref = False
    body_cites: set = set()
    for kind, blk in blocks:
        if kind != "p":
            continue
        t = text_of(blk)
        if re.match(r"^[一二三四五六七八九十]+、\s*参考文献", t) or t.strip() == "参考文献":
            in_ref = True
            continue
        if in_ref:
            m = REF_ITEM.match(t)
            if m:
                items.append(int(m.group(1)))
                continue
            if H1.match(t):           # 参考文献之后又起了新章，说明已离开该节
                in_ref = False
        body_cites.update(int(x) for x in CITE_REF.findall(t))
    rep.stats["refs"] = len(items)
    if not items:
        rep.skipped.append("L05 参考文献（本文档无参考文献列表）")
        return
    problems = []
    if items != list(range(1, len(items) + 1)):
        problems.append(f"文献编号不连续/重复：{items[:12]}")
    missing = [n for n in items if n not in body_cites]
    if missing:
        problems.append(f"{len(missing)} 条文献正文从未引用（如 [{missing[0]}]）")
    if problems:
        rep.issues.append(Issue("L05", "FAIL", "；".join(problems),
                                "文献表用递增编号生成，正文按 [n] 挂载"))
    else:
        rep.passed.append(f"L05 参考文献（{len(items)} 条，全部被正文引用）")


# ============================================================
# 版式类（静态）
# ============================================================

def check_page_field(rep: Report, doc) -> None:
    joined = []
    for sec in doc.sections:
        for p in sec.footer.paragraphs:
            joined.append(p._p.xml)
    xml = "".join(joined)
    has_page = "PAGE" in xml
    has_total = "NUMPAGES" in xml
    first_diff = any(sec.different_first_page_header_footer for sec in doc.sections)
    if not has_page:
        rep.issues.append(Issue("L06", "FAIL", "页脚没有 PAGE 域，打印后无法定位页码",
                                "用 add_page_number(doc)，字段域需 begin/instrText/separate/end 三段"))
    elif not has_total:
        rep.issues.append(Issue("L06", "WARN", "页脚只有 PAGE，缺「共 N 页」（NUMPAGES 域）",
                                "文案写成「第 PAGE 页　共 NUMPAGES 页」"))
    elif not first_diff:
        rep.issues.append(Issue("L06", "WARN", "封面也显示了页码",
                                "sec.different_first_page_header_footer = True"))
    else:
        rep.passed.append("L06 页码（第 N 页 共 M 页 · 封面不显示）")


def cover_zone_end(blocks) -> int:
    """封面区 = 第一个分页符之前。封面信息表不该被要求配表题。"""
    for i, (kind, blk) in enumerate(blocks):
        if kind == "p" and 'w:type="page"' in blk._p.xml:
            return i
    return 0


def check_table_layout(rep: Report, blocks) -> None:
    body = [(i, k, b) for i, (k, b) in enumerate(blocks)]
    cover_end = cover_zone_end(blocks)
    no_split, no_hdr, no_cap = [], [], []
    n_tab = 0
    for idx, kind, blk in body:
        if kind != "t":
            continue
        n_tab += 1
        rows = blk.rows
        if len(rows) <= 1:
            continue
        if not all(row_cant_split(r) for r in rows):
            no_split.append(f"第 {n_tab} 张（{len(rows)} 行）")
        if len(rows) >= BIG_TABLE_ROWS and not row_is_header(rows[0]):
            no_hdr.append(f"第 {n_tab} 张（{len(rows)} 行）")
        # 表题：紧邻上一个块是「表 n　…」段落，且该段 keepNext
        prev = body[idx - 1] if idx > 0 else None
        has_cap = False
        if prev and prev[1] == "p":
            t = text_of(prev[2])
            if CAP_TAB.match(t) and keep_with_next(prev[2]):
                has_cap = True
        # 豁免：封面区信息表、单列表（签字栏/意见栏）、键值信息表（首列「标签：」）
        first_k = rows[0].cells[0].text.strip()
        is_kv = first_k.endswith(("：", ":"))
        if (not has_cap and len(blk.columns) >= 2 and idx > cover_end
                and first_k and not is_kv):
            no_cap.append(f"第 {n_tab} 张（{len(rows)}×{len(blk.columns)}）")
    rep.stats["table_instances"] = n_tab
    if no_split:
        rep.issues.append(Issue(
            "L07", "FAIL", f"{len(no_split)} 张表未设行级不可拆分，会被从中间撕到两页：{no_split[:4]}",
            "每行 trPr 加 w:cantSplit；整表 ≤13 行时再给除末行外的段落加 keep_with_next"))
    elif n_tab:
        rep.passed.append(f"L07 表格不可拆行（{n_tab} 张）")
    if no_hdr:
        rep.issues.append(Issue("L08", "WARN", f"长表未设表头重复：{no_hdr[:4]}",
                                "首行 trPr 加 w:tblHeader，跨页时表头自动重复"))
    if no_cap:
        rep.issues.append(Issue("L09", "WARN", f"{len(no_cap)} 张正文表格上方缺少表题：{no_cap[:4]}",
                                "表题写在表格之上、黑体五号居中，并设 keep_with_next 与表绑定"))


def check_figure_binding(rep: Report, blocks) -> None:
    lst = [(k, b) for k, b in blocks]
    loose = []
    n_fig = 0
    for i, (kind, blk) in enumerate(lst):
        if kind != "p" or not para_has_drawing(blk):
            continue
        n_fig += 1
        nxt = lst[i + 1] if i + 1 < len(lst) else None
        bound = keep_with_next(blk)
        cap_ok = bool(nxt and nxt[0] == "p" and CAP_FIG.match(text_of(nxt[1])))
        if not (bound and cap_ok):
            loose.append(f"第 {n_fig} 张图")
    rep.stats["figures"] = n_fig
    if not n_fig:
        rep.skipped.append("L10 图注绑定（无图）")
    elif loose:
        rep.issues.append(Issue(
            "L10", "FAIL", f"{len(loose)} 张图的图注未与图绑定，会图在一页、注在下一页：{loose[:4]}",
            "图片段落 keep_with_next=True，紧随其后输出「图 n　说明」图注段"))
    else:
        rep.passed.append(f"L10 图注与图同页（{n_fig} 张）")


def check_metadata(rep: Report, doc, blocks) -> None:
    cp = doc.core_properties
    author = (cp.author or "").strip()
    if not author or "python-docx" in author.lower():
        rep.issues.append(Issue("L11", "FAIL", f"文档属性作者为「{author or '空'}」，是模板残留",
                                "cp.author = '示例文档'；同时设 title/subject/last_modified_by"))
    else:
        rep.passed.append(f"L11 文档属性（作者：{author}）")

    hits = []
    for kind, blk in blocks:
        if kind != "p":
            continue
        t = text_of(blk)
        m = PLACEHOLDER.search(t)
        if m:
            hits.append(f"「{m.group(0)}」")
    if hits:
        rep.issues.append(Issue("L12", "FAIL", f"残留占位符 {len(hits)} 处：{'、'.join(hits[:5])}",
                                "交付前全文搜索 TODO/XXX/待填/{{ }}，逐个替换成真实内容或删掉"))


def has_outline_level(p: Paragraph) -> bool:
    pPr = p._p.find(qn("w:pPr"))
    return pPr is not None and pPr.find(qn("w:outlineLvl")) is not None


def check_heading_styles(rep: Report, blocks) -> None:
    total, styled = 0, 0
    for kind, blk in blocks:
        if kind != "p":
            continue
        t = text_of(blk)
        if not (H1.match(t) or H2.match(t)):
            continue
        total += 1
        by_style = (blk.style.name or "").lower().startswith(("heading", "标题"))
        if by_style or has_outline_level(blk):
            styled += 1
    if not total:
        return
    if styled == 0:
        rep.issues.append(Issue(
            "L13", "WARN", f"{total} 个章/节标题全部是普通段落，Word 导航窗格为空、目录无法自动生成",
            "套 Heading 1/2 样式，或只写 w:outlineLvl（0=章、1=节），后者视觉零变化"))
    else:
        rep.passed.append(f"L13 标题结构（{styled}/{total} 有 Heading 样式或大纲级别）")


# ============================================================
# 渲染类（可选）
# ============================================================

def render_pdf(docx_path: Path, outdir: Path) -> Optional[Path]:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    subprocess.run([soffice, "--headless", "--norestore", "--convert-to", "pdf",
                    "--outdir", str(outdir), str(docx_path)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    pdf = outdir / (docx_path.stem + ".pdf")
    return pdf if pdf.exists() else None


def check_rendered(rep: Report, pdf_path: Path) -> None:
    try:
        import pymupdf
    except ImportError:
        rep.skipped.append("R01-R04 渲染检查（未安装 pymupdf）")
        return

    d = pymupdf.open(pdf_path)
    rep.stats["pages"] = d.page_count
    cross, cap_sep, tail_rows = [], [], []
    big_gap_pages = 0
    content_pages = 0

    for i, page in enumerate(d):
        H = page.rect.height
        # ① 跨页表：本页表格触底 + 次页表格触顶
        try:
            tabs = page.find_tables().tables
        except Exception:
            tabs = []
        for _t in tabs:
            if _t.bbox[3] > H - 80 and i + 1 < d.page_count:
                try:
                    nxt = d[i + 1].find_tables().tables
                except Exception:
                    nxt = []
                if nxt and min(x.bbox[1] for x in nxt) < 90:
                    cross.append(i + 1)
        # ② 图注与图分离：图注块上方 60pt 内既无位图也无矢量绘制
        blocks = [b for b in page.get_text("blocks") if b[4].strip()]
        imgs = page.get_image_info()
        draws = page.get_drawings()
        bold_spans = set()
        for blk in page.get_text("dict")["blocks"]:
            for line in blk.get("lines", []):
                for span in line["spans"]:
                    if span["flags"] & 16:          # PyMuPDF flags bit4 = bold
                        bold_spans.add(span["text"].strip())
        for b in blocks:
            if not CAP_FIG.match(b[4].strip()):
                continue
            top = b[1]
            has_img = any(0 <= top - im["bbox"][3] < 70 for im in imgs)
            has_vec = any(0 <= top - dr["rect"].y1 < 70 and dr["rect"].width > 120 for dr in draws)
            if not (has_img or has_vec):
                cap_sep.append(f"p{i + 1}「{b[4].strip()[:14]}」")
        # ③ 页底孤行标题 / ④ 底部留白
        body = [b for b in blocks if b[3] < H - 62]      # 剔除页脚带
        is_inner = 0 < i < d.page_count - 1              # 封面与末页不参与填充度统计
        if body:
            bottom = max(b[3] for b in body)
            gap_cm = (H - 72 - bottom) / 28.35
            last = max(body, key=lambda b: b[3])
            txt = last[4].strip()
            # 只有「加粗短行」才算标题：参考文献页码、图注、正文断行都不是标题
            is_bold = txt in bold_spans
            if (i + 1 < d.page_count and gap_cm < 1.0 and len(txt) < 22
                    and is_bold and not CAP_FIG.match(txt) and not CAP_TAB.match(txt)
                    and not txt.endswith(("。", "：", "，", "；"))):
                tail_rows.append(f"p{i + 1}「{txt[:16]}」")
            if is_inner:
                content_pages += 1
                if gap_cm > PAGE_GAP_CM:
                    big_gap_pages += 1
            if gap_cm > PAGE_GAP_CM and i + 1 < d.page_count:
                big_gap_pages += 1

    # 末页留白
    last_page = d[d.page_count - 1]
    bl = [b for b in last_page.get_text("blocks") if b[4].strip() and b[3] < last_page.rect.height - 62]
    tail_gap = (last_page.rect.height - 72 - max(b[3] for b in bl)) / 28.35 if bl else 24.0

    if cross:
        rep.issues.append(Issue("R01", "FAIL", f"{len(cross)} 张表被拆到两页（起始页 {cross[:5]}）",
                                "行级 cantSplit + 整表 ≤13 行时行间 keep_with_next，使整表换页"))
    else:
        rep.passed.append("R01 无跨页表")
    if cap_sep:
        rep.issues.append(Issue("R02", "FAIL", f"{len(cap_sep)} 处图注与图分离：{cap_sep[:4]}",
                                "图段 keep_with_next，图注紧随其后；图不要跨页拆分"))
    else:
        rep.passed.append("R02 图注未与图分离")
    if tail_rows:
        rep.issues.append(Issue("R03", "WARN", f"页底孤立标题 {len(tail_rows)} 处：{tail_rows[:4]}",
                                "标题段 keep_with_next=True，并 keep_together"))
    if content_pages:
        ratio = big_gap_pages / content_pages
        if ratio > PAGE_GAP_RATIO:
            rep.issues.append(Issue(
                "R04", "WARN", f"{big_gap_pages}/{content_pages} 页底部留白 >{PAGE_GAP_CM}cm（{ratio:.0%}）",
                "多为整表/整图整体换页造成：拆小表、缩短表行高，或允许表格随文流动"))
        else:
            rep.passed.append(f"R04 页面填充度（{big_gap_pages}/{content_pages} 页留白偏大）")
    if tail_gap > TAIL_GAP_CM:
        rep.issues.append(Issue("R05", "WARN", f"末页留白 {tail_gap:.1f}cm（上限 {TAIL_GAP_CM}cm）",
                                "审核意见栏按剩余空间加高，或让末章内容回流到末页"))
    else:
        rep.passed.append(f"R05 末页留白 {tail_gap:.1f}cm")


# ============================================================
# 单文件审计
# ============================================================

def audit(path: Path, render: bool = False) -> Report:
    rep = Report(path=str(path))
    doc = Document(str(path))
    blocks = list(iter_blocks(doc))

    check_chapter_sequence(rep, blocks)
    check_section_sequence(rep, blocks)
    check_numbering_gap(rep, blocks)
    check_citation_closure(rep, blocks)
    check_references(rep, blocks)
    check_page_field(rep, doc)
    check_table_layout(rep, blocks)
    check_figure_binding(rep, blocks)
    check_metadata(rep, doc, blocks)
    check_heading_styles(rep, blocks)

    if render:
        with tempfile.TemporaryDirectory() as td:
            pdf = render_pdf(path, Path(td))
            if pdf is None:
                rep.skipped.append("R01-R05 渲染检查（未找到 soffice，安装 LibreOffice 后可用）")
            else:
                check_rendered(rep, pdf)
    else:
        rep.skipped.append("R01-R05 渲染检查（加 --render 启用）")
    return rep


# ============================================================
# 输出
# ============================================================

ICON = {"FAIL": "❌", "WARN": "⚠️ "}


def print_report(rep: Report, verbose: bool = True) -> None:
    name = Path(rep.path).name
    st = rep.stats
    meta = " · ".join(x for x in (
        f"{st['pages']} 页" if "pages" in st else "",
        f"{st.get('figures', 0)} 图",
        f"{st.get('tabs', 0)} 编号表",
        f"{st.get('refs', 0)} 文献" if st.get("refs") else "",
    ) if x)
    print(f"\n── {name} " + ("─" * max(0, 46 - len(name))))
    if meta:
        print(f"   {meta}")
    if verbose:
        for p in rep.passed:
            print(f"   ✅ {p}")
        for s in rep.skipped:
            print(f"   － {s}")
    for i in rep.issues:
        print(f"   {ICON[i.level]} [{i.rule}] {i.detail}")
        if i.fix:
            print(f"        修法：{i.fix}")
    tail = f"   得分 {rep.score} / 100 · FAIL {len(rep.fails)} · WARN {len(rep.warns)}"
    print(tail)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="申报书排版硬指标审计")
    ap.add_argument("targets", nargs="+", help="docx 文件或包含 docx 的目录")
    ap.add_argument("--render", action="store_true", help="启用 PDF 深度检查（需 LibreOffice + pymupdf）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--strict", action="store_true", help="WARN 也视为不通过")
    ap.add_argument("--min-score", type=int, default=MIN_SCORE, help=f"达标分数线（默认 {MIN_SCORE}）")
    ap.add_argument("--quiet", action="store_true", help="只打印问题与得分")
    args = ap.parse_args(argv)

    files: List[Path] = []
    for t in args.targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.docx")))
        elif p.suffix.lower() == ".docx":
            files.append(p)
    files = [f for f in files if not f.name.startswith("~$")]
    if not files:
        print("未找到 .docx 文件", file=sys.stderr)
        return 2

    reports = [audit(f, render=args.render) for f in files]

    if args.json:
        print(json.dumps([asdict(r) | {"score": r.score} for r in reports],
                         ensure_ascii=False, indent=2))
    else:
        for r in reports:
            print_report(r, verbose=not args.quiet)
        total_fail = sum(len(r.fails) for r in reports)
        total_warn = sum(len(r.warns) for r in reports)
        avg = round(sum(r.score for r in reports) / len(reports))
        print(f"\n══ 合计 {len(reports)} 份 · 平均 {avg} 分 · FAIL {total_fail} · WARN {total_warn}")

    bad = [r for r in reports if r.fails or (args.strict and r.warns) or r.score < args.min_score]
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
