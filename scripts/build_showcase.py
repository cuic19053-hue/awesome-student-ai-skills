#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成示例展示页（单文件 HTML，图片 base64 内嵌，可直接托管）。"""

from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "build" / "figures"
GEN = ROOT / "assets" / "generated"
OUT = ROOT / "examples" / "showcase" / "index.html"

COVER = GEN / "Flat_editorial_vector_illustra_2026-10-21T11-40-45.jpg"
BEFORE = GEN / "Flat_editorial_vector_illustra_2026-10-21T11-41-20.jpg"


def b64(p: Path, max_w: int = 1400, quality: int = 88, crop_bottom: float = 0.0) -> str:
    """压缩后转 data URI：控制单页体积，文字仍保持可读。

    crop_bottom > 0 时裁掉底部比例（用于去除生图模型的水印）。
    """
    from PIL import Image
    import io

    im = Image.open(p)
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, "white")
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    if crop_bottom > 0:
        im = im.crop((0, 0, im.width, int(im.height * (1 - crop_bottom))))
    if im.width > max_w:
        h = round(im.height * max_w / im.width)
        im = im.resize((max_w, h), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


FIGURES = [
    ("01_tech_roadmap.png", "技术路线图", "四阶段递进结构，阶段内任务与阶段间依赖一目了然"),
    ("02_gantt.png", "进度甘特图", "8 项任务分解，标注中期检查与结题验收节点"),
    ("03_budget.png", "经费预算结构", "3 万元预算按科目占比呈现，可直接用于答辩讲解"),
    ("04_compare.png", "方案对比图", "改进算法 vs 经典 A*，四项核心指标横向评测"),
    ("05_swot.png", "SWOT 分析矩阵", "四象限梳理内外部条件，结论落到风险对冲"),
    ("06_innovation.png", "创新逻辑链", "痛点 → 不足 → 创新 → 指标 → 成果，一条线讲完"),
]

TABLE_ROWS = [
    ("大创 · 创新训练", "技术路线图、甘特图、经费结构、方案对比、SWOT", "6 张"),
    ("大创 · 创业训练", "商业模式画布、市场分析、财务预测", "5 张"),
    ("挑战杯", "技术路线图、创新点逻辑链、文献分布", "4 张"),
    ("互联网+ 商业计划书", "商业模式闭环、5 年财务三表、股权结构", "7 张"),
    ("国家奖学金", "成果量化雷达图、成长曲线", "2 张"),
    ("保研推免", "能力雷达、学术成果时间轴", "3 张"),
]


def card(fname: str, title: str, desc: str) -> str:
    p = FIG / fname
    if not p.exists():
        return ""
    return f"""
      <figure class="card">
        <div class="thumb"><img src="{b64(p)}" alt="{title}" loading="lazy"></div>
        <figcaption>
          <h3>{title}</h3>
          <p>{desc}</p>
        </figcaption>
      </figure>"""


def build():
    figs = "".join(card(*f) for f in FIGURES)
    rows = "".join(
        f"<tr><td class='c1'>{a}</td><td>{b}</td><td class='num'>{c}</td></tr>"
        for a, b, c in TABLE_ROWS
    )
    cover = b64(COVER, crop_bottom=0.07) if COVER.exists() else ""
    before = b64(BEFORE, crop_bottom=0.07) if BEFORE.exists() else ""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>成果示例 · Awesome Student AI Skills</title>
<style>
  :root {{
    --ink:#111827; --sub:#6B7280; --line:#E5E7EB; --bg:#FFFFFF;
    --soft:#F9FAFB; --blue:#1D4ED8; --bluef:#EFF6FF;
    --amber:#B45309; --green:#15803D;
  }}
  * {{ box-sizing:border-box; }}
  html {{ -webkit-text-size-adjust:100%; }}
  body {{
    margin:0; background:var(--bg); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",
      "Microsoft YaHei","Source Han Sans CN",sans-serif;
    line-height:1.75; font-size:16px;
    -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:0 28px; }}

  /* ---------- Hero ---------- */
  .hero {{ padding:72px 0 56px; border-bottom:1px solid var(--line); }}
  .hero-grid {{
    display:grid; grid-template-columns:1.05fr .95fr; gap:56px; align-items:center;
  }}
  .eyebrow {{
    display:inline-block; font-size:13px; letter-spacing:.12em;
    color:var(--blue); background:var(--bluef); padding:5px 12px;
    border-radius:999px; font-weight:600; margin-bottom:22px;
  }}
  h1 {{
    font-size:44px; line-height:1.25; margin:0 0 20px;
    letter-spacing:-.02em; font-weight:700;
  }}
  h1 em {{ font-style:normal; color:var(--blue); }}
  .lede {{ font-size:17px; color:var(--sub); margin:0 0 32px; max-width:34em; }}
  .cta {{ display:flex; gap:14px; flex-wrap:wrap; }}
  .btn {{
    display:inline-flex; align-items:center; gap:8px;
    padding:12px 24px; border-radius:10px; font-size:15px;
    font-weight:600; text-decoration:none; transition:.18s;
  }}
  .btn-primary {{ background:var(--blue); color:#fff; }}
  .btn-primary:hover {{ background:#1E3A8A; transform:translateY(-1px); }}
  .btn-ghost {{
    background:#fff; color:var(--ink); border:1px solid var(--line);
  }}
  .btn-ghost:hover {{ border-color:#9CA3AF; }}
  .hero-art {{ position:relative; }}
  .hero-art img {{
    width:100%; display:block; border-radius:16px;
    box-shadow:0 20px 48px -20px rgba(17,24,39,.28);
  }}
  .hero-art::after {{
    content:""; position:absolute; inset:-1px; border-radius:16px;
    border:1px solid rgba(17,24,39,.06); pointer-events:none;
  }}

  /* ---------- Section ---------- */
  section {{ padding:64px 0; border-bottom:1px solid var(--line); }}
  .sec-head {{ margin-bottom:40px; }}
  .kicker {{
    font-size:13px; font-weight:700; letter-spacing:.14em;
    color:var(--sub); text-transform:uppercase; margin-bottom:10px;
  }}
  h2 {{ font-size:30px; margin:0 0 12px; letter-spacing:-.01em; }}
  .sec-head p {{ margin:0; color:var(--sub); max-width:44em; }}

  /* ---------- Figure grid ---------- */
  .grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:26px; align-items:stretch; }}
  .card {{
    margin:0; border:1px solid var(--line); border-radius:14px;
    overflow:hidden; background:#fff; transition:.2s;
    display:flex; flex-direction:column;
  }}
  .card:hover {{ box-shadow:0 12px 32px -16px rgba(17,24,39,.24); transform:translateY(-2px); }}
  .thumb {{
    background:var(--soft); padding:22px; flex:1;
    display:flex; align-items:center; justify-content:center; min-height:210px;
  }}
  .thumb img {{ width:100%; max-height:300px; object-fit:contain; display:block; border-radius:4px; }}
  figcaption {{ padding:18px 22px 22px; border-top:1px solid var(--line); }}
  figcaption h3 {{ margin:0 0 6px; font-size:16px; }}
  figcaption p {{ margin:0; font-size:14px; color:var(--sub); }}

  /* ---------- Before / After ---------- */
  .ba {{ display:grid; grid-template-columns:1fr; gap:28px; }}
  .ba img {{ width:100%; display:block; border-radius:14px; border:1px solid var(--line); }}
  .ba-labels {{ display:grid; grid-template-columns:1fr 1fr; gap:28px; margin-top:-6px; }}
  .ba-labels div {{ font-size:14px; color:var(--sub); }}
  .ba-labels b {{ display:block; color:var(--ink); font-size:15px; margin-bottom:2px; }}

  /* ---------- Table ---------- */
  table {{ width:100%; border-collapse:collapse; font-size:15px; }}
  thead th {{
    text-align:left; font-size:13px; letter-spacing:.06em; color:var(--sub);
    font-weight:600; padding:0 14px 12px; border-bottom:1px solid var(--line);
  }}
  tbody td {{ padding:14px; border-bottom:1px solid var(--line); }}
  tbody tr:last-child td {{ border-bottom:none; }}
  tbody tr:hover {{ background:var(--soft); }}
  .c1 {{ font-weight:600; }}
  .num {{ text-align:right; color:var(--blue); font-weight:600; white-space:nowrap; }}

  /* ---------- Note ---------- */
  .note {{
    background:var(--soft); border-left:3px solid var(--amber);
    padding:18px 22px; border-radius:0 10px 10px 0;
    font-size:14px; color:var(--sub); margin-top:32px;
  }}
  .note b {{ color:var(--ink); }}

  footer {{ padding:44px 0 64px; color:var(--sub); font-size:14px; }}
  footer a {{ color:var(--blue); text-decoration:none; }}
  footer a:hover {{ text-decoration:underline; }}

  @media (max-width:860px) {{
    .hero-grid {{ grid-template-columns:1fr; gap:36px; }}
    h1 {{ font-size:32px; }}
    .grid {{ grid-template-columns:1fr; }}
    .ba-labels {{ grid-template-columns:1fr; gap:12px; }}
    .wrap {{ padding:0 20px; }}
    section {{ padding:48px 0; }}
  }}
</style>
</head>
<body>

<div class="wrap">
  <div class="hero">
    <div class="hero-grid">
      <div>
        <span class="eyebrow">成果示例 · 虚构数据</span>
        <h1>不是一段文字，<br>是一份<em>能直接提交</em>的文档</h1>
        <p class="lede">
          技术路线图、甘特图、经费结构、方案对比、SWOT 矩阵——全部由代码渲染，
          矢量级清晰、数字可核对，直接嵌入 Word 正文。
        </p>
        <div class="cta">
          <a class="btn btn-primary" href="https://agent.stardust.website">在线试试 →</a>
          <a class="btn btn-ghost" href="https://github.com/cuic19053-hue/awesome-student-ai-skills">查看仓库</a>
        </div>
      </div>
      <div class="hero-art">
        <img src="{cover}" alt="AI 生成的情景插画：学生与文档图表">
      </div>
    </div>
  </div>
</div>

<section>
  <div class="wrap">
    <div class="sec-head">
      <div class="kicker">Figures</div>
      <h2>一份申报书里的六类标准配图</h2>
      <p>以下图片全部由 <code>utils/figgen.py</code> 代码生成，300 dpi，配色统一，可随项目数据自动更新——不是贴图，是数据可视化。</p>
    </div>
    <div class="grid">{figs}</div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="sec-head">
      <div class="kicker">Before / After</div>
      <h2>从一堆草稿，到一份规范文档</h2>
      <p>左边是大多数人现在的状态：模板东拼西凑、格式反复调整、不知道自己漏了哪个栏目。右边是工具输出的结果。</p>
    </div>
    <div class="ba">
      <img src="{before}" alt="对比插画：杂乱草稿与规范文档">
    </div>
    <div class="ba-labels">
      <div><b>过去：对着一份空白模板发愁</b>格式靠猜、栏目靠问、评审标准靠打听</div>
      <div><b>现在：回答几个问题，拿到成稿</b>结构、图表、排版一次到位，你只负责核对事实</div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="sec-head">
      <div class="kicker">Coverage</div>
      <h2>不同赛道，配图也不一样</h2>
      <p>每类申报书的评审关注点不同，配图逻辑也不同——项目类看技术路线与进度，商业类看财务与模式，评优类看成果量化。</p>
    </div>
    <table>
      <thead>
        <tr><th>赛道</th><th>典型配图</th><th style="text-align:right">数量</th></tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <div class="note">
      <b>关于本页数据：</b>示例中的项目主题、人物、指标数值均为虚构，仅用于展示输出格式与排版效果，
      不是任何真实申报材料。实际生成时，图表数据完全来自你填写的信息。
    </div>
  </div>
</section>

<div class="wrap">
  <footer>
    <a href="https://github.com/cuic19053-hue/awesome-student-ai-skills">Awesome Student AI Skills</a>
    　·　MIT License　·　配图由 Python 代码渲染 + AI 插画生成
  </footer>
</div>

</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    size = OUT.stat().st_size / 1024
    print(f"✓ 已生成 {OUT}（{size:.0f} KB）")
    return OUT


if __name__ == "__main__":
    build()
