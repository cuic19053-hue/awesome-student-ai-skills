"""Bounded figure specifications. Models supply data, never executable code."""
from __future__ import annotations

import html
import math
import textwrap
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Overlay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=100)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: int = Field(ge=0, le=23)
    target: int = Field(ge=0, le=23)


class FigureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    section_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=100)
    renderer: Literal["svg", "python", "gpt", "overlay", "upload"] = "svg"
    chart: Literal["flow", "bar", "line", "gantt"] = "flow"
    anchor: int = Field(default=-1, ge=-1, le=1000)
    nodes: list[str] = Field(default_factory=list, max_length=24)
    edges: list[Edge] = Field(default_factory=list, max_length=60)
    labels: list[str] = Field(default_factory=list, max_length=24)
    values: list[float] = Field(default_factory=list, max_length=24)
    starts: list[float] = Field(default_factory=list, max_length=24)
    data_status: Literal["planned", "measured"] = "planned"
    source: str = Field(default="", max_length=500)
    source_ids: list[str] = Field(default_factory=list, max_length=30)
    document_id: str = Field(default="", pattern=r"^[a-f0-9]{32}$|^$")
    prompt: str = Field(default="", max_length=1700)
    scene_text: list[str] = Field(default_factory=list, max_length=12)
    overlays: list[Overlay] = Field(default_factory=list, max_length=12)
    base_asset_job: str = Field(default="", pattern=r"^[a-f0-9]{32}$|^$")
    confirmed: bool = False
    text_confirmed: bool = False

    @model_validator(mode="after")
    def bounded_data(self):
        texts = self.nodes + self.labels + self.scene_text
        if any(not x.strip() or len(x) > 160 for x in texts):
            raise ValueError("图中文字不能为空，且每项最多 160 字")
        if any(not math.isfinite(x) or abs(x) > 1e12 for x in self.values + self.starts):
            raise ValueError("图表数值无效")
        if self.renderer == "python":
            if not self.labels or len(self.labels) != len(self.values) or not self.source.strip():
                raise ValueError("数据图需要等长标签和数值，以及数据来源")
            if self.chart == "gantt" and (
                len(self.starts) != len(self.values) or any(v <= 0 for v in self.values)
            ):
                raise ValueError("甘特图需要每项开始时间与正数持续时间")
        if self.renderer == "svg" and not self.nodes:
            raise ValueError("流程图需要节点")
        if any(e.source >= len(self.nodes) or e.target >= len(self.nodes) or e.source == e.target for e in self.edges):
            raise ValueError("连接关系引用无效节点")
        if self.renderer == "gpt" and not self.prompt.strip():
            raise ValueError("概念图需要描述")
        if self.renderer == "gpt" and len(self.prompt) + sum(map(len, self.scene_text)) > 1700:
            raise ValueError("生图描述与场景文字合计最多 1700 字，请缩短；不会截掉关键文字")
        if self.renderer == "overlay" and (not self.base_asset_job or not self.overlays):
            raise ValueError("局部排字需要原始资产及文字")
        if self.renderer == "upload" and not self.document_id:
            raise ValueError("请选择当前项目的真实上传图片")
        return self


def image_prompt(spec: FigureSpec, project: dict) -> str:
    base = "生成项目概念示意，不得冒充已完成实验、真实照片或证明文件。\n" + spec.prompt
    base += ("\n允许出现的场景文字仅限以下原文，请逐字呈现：" + "；".join(spec.scene_text)
             if spec.scene_text else "\n不要生成任何文字、数字、标志或水印。")
    state = project.get("state", {})
    context = f"项目：{project.get('title', '')}；计划方法：{state.get('method', '')}"
    # Preserve the entire user text contract; optional context is explicitly an excerpt.
    space = 2000 - len(base) - 35
    if space > 0:
        base += "\n已确认项目背景（节选，仅供视觉参考）：" + context[:space]
    if len(base) > 2000:
        raise ValueError("完整生图描述超限，请缩短后再试")
    return base


def font_path() -> str:
    import os
    candidates = [
        os.environ.get("MATERIAL_FONT_PATH", ""),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/droid/DroidSansFallback.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]
    found = next((p for p in candidates if p and Path(p).is_file()), "")
    if not found:
        raise RuntimeError("中文字体不可用，拒绝生成可能乱码的图片")
    return found


def check_glyphs(texts: list[str]) -> None:
    from fontTools.ttLib import TTFont
    font = TTFont(font_path(), fontNumber=0, lazy=True)
    try:
        supported = {point for table in font["cmap"].tables for point in table.cmap}
        missing = sorted({c for text in texts for c in text if not c.isspace() and ord(c) not in supported})
    finally:
        font.close()
    if missing:
        raise ValueError("指定字体缺少图表所需字形，请更换有授权的完整中文字体")


def render_svg(spec: FigureSpec, folder: Path) -> Path:
    """No caller-supplied HTML, CSS, JS, URL or SVG is accepted."""
    from playwright.sync_api import sync_playwright
    font = Path(font_path())
    check_glyphs([spec.title, *spec.nodes])
    rows = (len(spec.nodes) + 1) // 2
    heights = [max(110, 42 + 32 * max(len(textwrap.wrap(s, 16))
               for s in spec.nodes[i:i+2])) for i in range(0, len(spec.nodes), 2)]
    ys, cursor = [], 100
    for h in heights:
        ys.append(cursor)
        cursor += h + 55
    height = cursor + 30
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#1D4ED8"/></marker></defs>',
             f'<text x="600" y="55" text-anchor="middle" font-size="30" fill="#111827">{html.escape(spec.title)}</text>']
    positions = []
    for index in range(len(spec.nodes)):
        row, col = divmod(index, 2)
        if row % 2:
            col = 1-col
        positions.append((80+col*560, ys[row], heights[row]))
    edges = [(e.source, e.target) for e in spec.edges] or [(i,i+1) for i in range(len(spec.nodes)-1)]
    for a,b in edges:
        x,y,h = positions[a]; xx,yy,hh = positions[b]
        if y == yy:
            start, end = (x+490,xx-10) if xx > x else (x-10,xx+490)
            cy = y+h/2
            parts.append(f'<path d="M {start} {cy} H {end}" marker-end="url(#arrow)" stroke="#1D4ED8" stroke-width="3" fill="none"/>')
        else:
            start_y,end_y = (y+h+6,yy-9) if yy>y else (y-6,yy+hh+9)
            parts.append(f'<path d="M {x+240} {start_y} L {xx+240} {end_y}" marker-end="url(#arrow)" stroke="#1D4ED8" stroke-width="3" fill="none"/>')
    for index, label in enumerate(spec.nodes):
        x,y,h = positions[index]
        parts.append(f'<rect x="{x}" y="{y}" width="480" height="{h}" rx="14" fill="#EFF6FF" stroke="#1D4ED8" stroke-width="2"/>')
        for j, line in enumerate(textwrap.wrap(label, 16)):
            parts.append(f'<text x="{x+240}" y="{y+38+j*32}" text-anchor="middle" font-size="28" fill="#111827">{html.escape(line)}</text>')
    parts.append("</svg>")
    svg = "".join(parts)
    # Font embedded; no file:// or network access from the page.
    import base64
    encoded = base64.b64encode(font.read_bytes()).decode()
    document = f'<style>@font-face{{font-family:Material;src:url(data:font/ttf;base64,{encoded})}}body{{margin:0;font-family:Material}}text{{font-family:Material}}</style>{svg}'
    (folder / "source.svg").write_text(svg, encoding="utf-8")
    (folder / "source.html").write_text(document, encoding="utf-8")
    with sync_playwright() as pw:
        import os
        browser = pw.chromium.launch(headless=True, **(
            {"executable_path": os.environ["MATERIAL_CHROMIUM_PATH"]}
            if os.environ.get("MATERIAL_CHROMIUM_PATH") else {}
        ))
        page = browser.new_page(viewport={"width": 1200, "height": height}, device_scale_factor=2)
        page.route("**/*", lambda route: route.abort())
        page.set_content(document)
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(folder / "figure.png"))
        browser.close()
    return folder / "figure.png"


def render_python(spec: FigureSpec, folder: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font = FontProperties(fname=font_path())
    check_glyphs([spec.title, *spec.labels])
    fig, ax = plt.subplots(figsize=(8, max(3.5, len(spec.labels) * .5)))
    font.set_size(14)
    if spec.chart == "gantt":
        ax.barh(range(len(spec.labels)), spec.values, left=spec.starts, color="#2563EB")
        ax.set_yticks(range(len(spec.labels)), spec.labels, fontproperties=font)
    elif spec.chart == "line":
        ax.plot(range(len(spec.labels)), spec.values, color="#2563EB", marker="o")
        ax.set_xticks(range(len(spec.labels)), spec.labels, fontproperties=font)
    else:
        if len(spec.labels) > 5 or max(map(len, spec.labels)) > 8:
            ax.barh(range(len(spec.labels)), spec.values, color="#2563EB")
            ax.set_yticks(range(len(spec.labels)), ["\n".join(textwrap.wrap(x, 12)) for x in spec.labels], fontproperties=font)
        else:
            ax.bar(range(len(spec.labels)), spec.values, color="#2563EB")
            ax.set_xticks(range(len(spec.labels)), spec.labels, fontproperties=font)
    ax.set_title(spec.title + ("（计划值）" if spec.data_status == "planned" else "（实测值）"), fontproperties=font)
    ax.grid(axis="y", alpha=.2)
    fig.tight_layout()
    target = folder / "figure.png"
    fig.savefig(target, dpi=220, facecolor="white")
    plt.close(fig)
    return target


def compose_text(base: Path, spec: FigureSpec, folder: Path) -> Path:
    """Add labels on a NEW footer panel; never blindly cover scene pixels."""
    from PIL import Image, ImageDraw, ImageFont
    original = Image.open(base).convert("RGB")
    if original.width * original.height > 25_000_000:
        raise ValueError("图片尺寸超限")
    labels = [o.text for o in spec.overlays]
    check_glyphs(labels)
    lines = [line for text in labels for line in textwrap.wrap(text, 30)]
    size = max(20, original.width // 35)
    output = Image.new("RGB", (original.width, original.height + (len(lines) + 1) * (size + 12)), "white")
    output.paste(original, (0, 0))
    draw, font = ImageDraw.Draw(output), ImageFont.truetype(font_path(), size=size)
    for i, text in enumerate(lines):
        draw.text((30, original.height + 20 + i * (size + 12)), text, fill="#111827", font=font)
    output.save(folder / "figure.png")
    return folder / "figure.png"


def check_scene_text(image: Path, expected: list[str]) -> dict:
    if not expected:
        return {"status": "passed", "method": "no_scene_text"}
    try:
        from .documents import _ocr_image
        text, low = _ocr_image(image.read_bytes())
        import re
        normalize = lambda x: re.sub(r"\s+", "", x)
        missing = [s for s in expected if normalize(s) not in normalize(text)]
        return {"status": "needs_review", "ocr_match": not missing and not low,
                "missing": missing, "notice": "OCR 仅辅助，场景文字仍需人工核对"}
    except Exception:
        return {"status": "not_checked", "notice": "OCR 不可用，场景文字需人工核对"}
