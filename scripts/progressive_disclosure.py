#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""progressive_disclosure.py — 把 SKILL.md 中「按需加载」的大章节外移到 references/。

为什么
------
Anthropic 官方最佳实践（Skill authoring best practices）：

  > The context window is a public good.
  > Default assumption: Claude is already very smart.
  > 只加 Claude 不知道的信息；挑战每一条信息的 token 成本。

官方推荐三层渐进式披露：
  第 1 层  name + description（始终预加载）
  第 2 层  SKILL.md 正文（技能被判定相关时加载）
  第 3 层  references/ 等附加文件（真正需要时才读）

本仓现状（2026-11-08 基线）：
  35 个 SKILL.md 合计 47,049 行 / 1.26 MB，平均 1,344 行，
  全部超官方 500 行建议，最大 2,521 行。其中大量内容属于第 3 层：
  完整 JSON Schema、逐条信息采集清单、数学公式规范、配图规范、
  FAQ、版本记录、案例对照——模型在写正文时并不需要全部读完。

做法
----
按「章节标题关键词」识别可外移章节，移动到
`subskills/<id>/references/<slug>.md`，并在原位置留一个
「按需阅读」的指针（含触发条件），保证信息不丢失、路径可达。

安全约束
--------
- 只移动**明确匹配**的章节；不猜、不动正文核心章节
- 保留原文到 references/，原文一字不改
- 原地留下指针块，含「何时该读」的条件
- --dry-run 默认开启预览；--check 校验是否已重构
- 单文件最多外移 --max-move 个章节，防止把 SKILL.md 掏空

用法
----
    python3 scripts/progressive_disclosure.py --skill challenge-cup --dry-run
    python3 scripts/progressive_disclosure.py --skill challenge-cup
    python3 scripts/progressive_disclosure.py --all --dry-run
    python3 scripts/progressive_disclosure.py --skill challenge-cup --check
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SUBSKILLS = ROOT / "subskills"

H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)

# 受保护块：这些标记之间的内容不参与章节切分与外移
PROTECT_START = "<!-- WRITING-STYLE:START -->"
PROTECT_END = "<!-- WRITING-STYLE:END -->"

# 章节标题关键词 → (slug, 中文说明, 何时阅读)
# 只匹配明确的「资料型」章节，不碰撰写规范/工作流/质检这些核心指令
MOVABLE: List[Tuple[str, str, str, str]] = [
    ("JSON Schema", "json-schema", "完整 JSON Schema 定义",
     "构造 --data 输入文件、或 build.py 报字段校验错误时"),
    ("信息采集清单", "intake-checklist", "逐字段信息采集清单",
     "需要逐条向用户提问采集信息时"),
    ("数学公式规范", "math-formulas", "数学公式书写与排版规范",
     "正文含公式、需要按规范排版时"),
    ("配图规范", "figures", "配图与图表规范",
     "需要生成或插入技术路线图、对比表、统计图时"),
    ("答辩 PPT 框架", "defense-ppt", "答辩 PPT 框架",
     "用户要求配套答辩 PPT 时"),
    ("案例对照", "case-reference", "案例对照与范文",
     "需要参考完整范例、或用户要求对齐某个案例时"),
    ("版本记录", "changelog", "版本变更记录",
     "排查历史行为差异、或维护该 skill 时"),
    ("附录", "appendix", "附录与 FAQ",
     "遇到正文未覆盖的边界问题、或查常见疑问时"),
    ("与其他竞赛对比", "comparison", "与其他赛道的对比说明",
     "用户在多赛道之间犹豫、需要对比选择时"),
    ("备赛时间线", "timeline", "备赛时间线建议",
     "用户询问排期、或需要倒推时间计划时"),
    ("学校差异处理", "school-differences", "学校格式差异处理",
     "用户指定了具体学校、需要适配格式时"),
    # 第二轮：参考资料型大章节（范例 / 详解 / 案例），不含核心写作指令
    ("案例规范", "case-spec", "案例规范详解",
     "需要参考完整案例、或用户要求对齐某个案例时"),
    ("详细撰写范例", "writing-examples", "按章节展开的详细撰写范例",
     "需要参考某一段落的具体写法示例时"),
    ("撰写范例", "writing-examples", "撰写范例",
     "需要参考具体写法示例时"),
    ("docx 生成调用方式", "build-usage", "docx 生成调用方式",
     "需要调用 build.py 生成文档、或排查生成参数时"),
    ("build.py 接口", "build-usage", "build.py 接口说明",
     "需要调用 build.py 或了解接口参数时"),
]


@dataclass
class Section:
    title: str
    start: int          # 行号（0-based，含 ## 行）
    end: int            # 结束行号（不含）
    lines: List[str]

    @property
    def size(self) -> int:
        return self.end - self.start


def _split_sections(lines: List[str]) -> List[Section]:
    """按 H2 切分章节。

    关键：受保护块（写作规范块）内部即使出现 `## ` 标题，也不作为章节边界，
    否则会把块切碎、把 START 标记卷进别的章节一起外移。
    """
    # 先算出受保护块的行区间
    protected: List[Tuple[int, int]] = []
    in_block = False
    block_start = 0
    for i, l in enumerate(lines):
        s = l.strip()
        if s == PROTECT_START:
            in_block = True
            block_start = i
        elif s == PROTECT_END and in_block:
            protected.append((block_start, i))
            in_block = False

    def _is_protected(i: int) -> bool:
        return any(a <= i <= b for a, b in protected)

    idx = [
        (i, m.group(1))
        for i, l in enumerate(lines)
        if (m := H2_RE.match(l)) and not _is_protected(i)
    ]
    out: List[Section] = []
    for k, (i, title) in enumerate(idx):
        end = idx[k + 1][0] if k + 1 < len(idx) else len(lines)
        # 章节范围不得跨越受保护块：截断到块起点
        for a, _b in protected:
            if i < a < end:
                end = a
                break
        if end > i:
            out.append(Section(title=title, start=i, end=end, lines=lines[i:end]))
    return out


def _match_movable(title: str) -> Optional[Tuple[str, str, str]]:
    for keyword, slug, desc, when in MOVABLE:
        if keyword in title:
            return slug, desc, when
    return None


def _pointer_block(slug: str, desc: str, when: str, orig_title: str) -> str:
    return (
        f"## {orig_title}（已外移至 references/{slug}.md）\n\n"
        f"> 📎 **{desc}** 已移至 [`references/{slug}.md`](references/{slug}.md)，"
        f"保持 SKILL.md 精简。\n"
        f"> **何时阅读**：{when}。\n"
        f"> 其余情况下不需要读取该文件。\n"
    )


def refactor_skill(
    skill_id: str,
    *,
    max_move: int = 4,
    dry_run: bool = True,
    min_lines: int = 40,
) -> Dict[str, object]:
    """重构单个 skill。返回操作摘要。"""
    md_path = SUBSKILLS / skill_id / "SKILL.md"
    if not md_path.exists():
        return {"skill": skill_id, "error": "SKILL.md 不存在"}

    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    sections = _split_sections(lines)

    movable: List[Tuple[Section, str, str, str]] = []
    for sec in sections:
        m = _match_movable(sec.title)
        if m and sec.size >= min_lines:
            slug, desc, when = m
            movable.append((sec, slug, desc, when))
        if len(movable) >= max_move:
            break

    if not movable:
        return {"skill": skill_id, "moved": [], "before_lines": len(lines),
                "after_lines": len(lines), "note": "无可外移章节"}

    ref_dir = SUBSKILLS / skill_id / "references"
    moved_info = []

    # slug 去重：同一 skill 内多个章节命中同一关键词时（如多个「附录」），
    # 追加序号，避免相互覆盖
    used_slugs: Dict[str, int] = {}

    def _unique_slug(base: str) -> str:
        if base not in used_slugs:
            used_slugs[base] = 1
            return base
        used_slugs[base] += 1
        return f"{base}-{used_slugs[base]}"

    # 从后往前替换，避免行号漂移
    new_lines = list(lines)
    for sec, slug, desc, when in sorted(movable, key=lambda x: -x[0].start):
        slug = _unique_slug(slug)
        ref_path = ref_dir / f"{slug}.md"
        ref_content = (
            f"# {sec.title}\n\n"
            f"> 从 `subskills/{skill_id}/SKILL.md` 外移而来（渐进式披露）。\n"
            f"> 何时阅读：{when}。\n\n"
            + "".join(sec.lines[1:]).lstrip("\n")
        )
        pointer = _pointer_block(slug, desc, when, sec.title)
        new_lines[sec.start:sec.end] = [pointer + "\n"]
        try:
            ref_display = str(ref_path.relative_to(ROOT))
        except ValueError:
            # 非默认根目录（如测试沙箱）时退回绝对路径，避免崩溃
            ref_display = str(ref_path)
        moved_info.append({
            "slug": slug,
            "title": sec.title,
            "lines": sec.size,
            "ref": ref_display,
        })
        if not dry_run:
            ref_dir.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(ref_content, encoding="utf-8")

    result_text = "".join(new_lines)

    # 在 SKILL.md 顶部附近插入 references 索引（幂等）
    index_marker = "<!-- REFERENCES-INDEX -->"
    if index_marker not in result_text and moved_info:
        idx_block = (
            f"{index_marker}\n"
            "> 📚 **按需加载的参考资料**（渐进式披露，不需要时不要读）：\n"
            + "".join(
                f"> - [`references/{m['slug']}.md`](references/{m['slug']}.md) — {m['title']}\n"
                for m in moved_info
            )
            + "\n"
        )
        # 插到第一个 ## 之前
        first_h2 = re.search(r"^##\s", result_text, re.M)
        if first_h2:
            result_text = result_text[:first_h2.start()] + idx_block + result_text[first_h2.start():]
        else:
            result_text += "\n" + idx_block

    if not dry_run:
        md_path.write_text(result_text, encoding="utf-8")

    return {
        "skill": skill_id,
        "moved": moved_info,
        "before_lines": len(lines),
        "after_lines": len(result_text.splitlines()),
        "saved_lines": len(lines) - len(result_text.splitlines()),
    }


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SKILL.md 渐进式披露重构（大章节外移到 references/）")
    ap.add_argument("--skill", help="单个 skill id")
    ap.add_argument("--all", action="store_true", help="处理全部 35 个")
    ap.add_argument("--dry-run", action="store_true", help="只预览（默认行为）")
    ap.add_argument("--apply", action="store_true", help="实际写盘")
    ap.add_argument("--max-move", type=int, default=4, help="每个 skill 最多外移章节数")
    ap.add_argument("--check", action="store_true", help="校验是否已重构（存在大章节即失败）")
    args = ap.parse_args(argv)

    targets: List[str]
    if args.skill:
        targets = [args.skill]
    elif args.all:
        targets = sorted(p.parent.name for p in SUBSKILLS.glob("*/SKILL.md"))
    else:
        ap.error("需要 --skill <id> 或 --all")

    dry_run = not args.apply

    if args.check:
        offenders = []
        for sid in targets:
            md = SUBSKILLS / sid / "SKILL.md"
            if not md.exists():
                continue
            sections = _split_sections(md.read_text(encoding="utf-8").splitlines(keepends=True))
            big = [
                s for s in sections
                if _match_movable(s.title) and s.size >= 40
                and "已外移至" not in s.title
            ]
            if big:
                offenders.append((sid, [(s.title, s.size) for s in big]))
        if offenders:
            for sid, items in offenders:
                print(f"❌ {sid}:")
                for title, size in items:
                    print(f"     {size:>4} 行  {title}")
            print(f"\n{len(offenders)} 个 skill 仍有可外移的大章节")
            return 1
        print("✅ 无待外移的大章节")
        return 0

    total_saved = 0
    for sid in targets:
        r = refactor_skill(sid, max_move=args.max_move, dry_run=dry_run)
        if r.get("error"):
            print(f"❌ {sid}: {r['error']}")
            continue
        moved = r["moved"]
        if not moved:
            continue
        total_saved += r["saved_lines"]
        print(f"{'[预览]' if dry_run else '[已改]'} {sid}: "
              f"{r['before_lines']} → {r['after_lines']} 行（-{r['saved_lines']}）")
        for m in moved:
            print(f"     - {m['lines']:>4} 行  {m['title']} → references/{m['slug']}.md")

    if total_saved:
        print(f"\n合计精简 {total_saved} 行")
        if dry_run:
            print("（--dry-run，未写盘；加 --apply 执行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
