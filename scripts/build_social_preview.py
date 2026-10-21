#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成仓库社交预览图（1280×640，GitHub / 微信分享卡片尺寸）。

之前 assets/social-preview.png 是一张写着 "The image is generating..." 的
占位图，是生成中断留下的残件。本脚本用代码重做一张可复现的正式图：
左侧标题文案，右侧沿用展示页的封面插画。

用法：python scripts/build_social_preview.py
输出：assets/social-preview.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "assets" / "generated"
COVER = GEN / "Flat_editorial_vector_illustra_2026-10-21T11-40-45.jpg"
OUT = ROOT / "assets" / "social-preview.png"

W, H = 1280, 640
INK = (17, 24, 39)
GREY = (107, 114, 128)
BLUE = (29, 78, 216)
AMBER = (180, 83, 9)
LINE = (229, 231, 235)
BG = (255, 255, 255)

# PingFang.ttc 里的索引：3=Regular 7=Medium 11=Semibold
FONT_CANDIDATES = [
    ("/System/Library/AssetsV2/com_apple_MobileAsset_Font8/"
     "86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc",
     {3: 0, 7: 4, 11: 8}),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", {3: 0, 7: 0, 11: 0}),
]


def load_font(size: int, weight: int = 3) -> ImageFont.FreeTypeFont:
    for path, idx in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=idx.get(weight, 0))
            except Exception:
                continue
    raise SystemExit("找不到可用的中文字体，拒绝产出乱码图")


def rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *img.size), radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def build() -> Path:
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)

    # ---------------- 右侧插画（占 40% 宽，垂直居中）
    if COVER.exists():
        side = 400
        im = Image.open(COVER).convert("RGB")
        # 生图底部带水印条，先裁掉 7%（与展示页一致）
        im = im.crop((0, 0, im.width, int(im.height * 0.93)))
        # 居中裁成正方形
        s = min(im.size)
        im = im.crop(((im.width - s) // 2, (im.height - s) // 2,
                      (im.width + s) // 2, (im.height + s) // 2))
        im = im.resize((side, side), Image.LANCZOS)
        im = rounded(im, 28)

        x0, y0 = W - side - 72, (H - side) // 2
        # 柔和投影
        shadow = Image.new("RGBA", (side + 60, side + 60), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (30, 40, side + 30, side + 40), radius=28, fill=(17, 24, 39, 30))
        shadow = shadow.filter(ImageFilter.GaussianBlur(20))
        canvas.paste(shadow, (x0 - 30, y0 - 30), shadow)
        canvas.paste(im, (x0, y0), im)

    # ---------------- 左侧文案
    left = 72
    d.text((left, 92), "AWESOME STUDENT AI SKILLS", font=load_font(17, 7), fill=BLUE)
    d.line((left, 124, left + 46, 124), fill=BLUE, width=3)

    y = 156
    for line, size in (("中文申报书与公文", 54), ("让 AI 按格式写好", 54)):
        d.text((left, y), line, font=load_font(size, 11), fill=INK)
        y += 72

    y += 8
    d.text((left, y), "11 类赛道 · 一图一表 · 导出即交付",
           font=load_font(24, 3), fill=GREY)

    # 三个能力标签
    y += 62
    tags = ["大创 / 挑战杯", "国家奖学金", "保研 / 公派"]
    x = left
    for t in tags:
        f = load_font(18, 7)
        tw = int(d.textlength(t, font=f))
        d.rounded_rectangle((x, y, x + tw + 32, y + 42), radius=21,
                            outline=LINE, width=2)
        d.text((x + 16, y + 10), t, font=f, fill=INK)
        x += tw + 32 + 14

    # 底部信息条
    d.line((left, H - 96, W - 72, H - 96), fill=LINE, width=2)
    d.text((left, H - 72), "github.com/cuic19053-hue/awesome-student-ai-skills",
           font=load_font(19, 3), fill=GREY)
    d.text((left, H - 44), "39,285 字示例内容 · 44 张代码渲染配图 · 75 张表格",
           font=load_font(17, 3), fill=(156, 163, 175))

    canvas.save(OUT, "PNG", optimize=True)
    return OUT


if __name__ == "__main__":
    p = build()
    print(f"✓ {p}  ({p.stat().st_size / 1024:.0f} KB)")
