#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_skill_integrity.py — 改造后的完整性验收（Lead 用）。

在 6 个 Agent 并行改造 35 个 SKILL.md 之后，统一检查有没有改坏东西。

检查项
------
I1 受保护块   每个 SKILL.md 必须有且仅有 1 个 WRITING-STYLE START/END，且顺序正确
I2 索引块     REFERENCES-INDEX 若存在，其指针必须指向真实文件
I3 frontmatter name 必须与目录名一致（skills-ref 规范）
I4 无重复标题 同一 SKILL.md 内不得出现重复的 H2 标题（改造易产生重复章节）
I5 结构完整   每个 SKILL.md 至少含「质检清单」章节
I6 空章节     不得出现标题后紧跟另一个标题的空章节（改造误删内容会这样）

用法
----
    python3 scripts/verify_skill_integrity.py
    python3 scripts/verify_skill_integrity.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
SUBSKILLS = ROOT / "subskills"

PROTECT_START = "<!-- WRITING-STYLE:START -->"
PROTECT_END = "<!-- WRITING-STYLE:END -->"
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


@dataclass
class Problem:
    skill: str
    code: str
    detail: str


def check_skill(md_path: Path) -> List[Problem]:
    skill = md_path.parent.name
    problems: List[Problem] = []
    text = md_path.read_text(encoding="utf-8")

    # I1 受保护块
    n_start = text.count(PROTECT_START)
    n_end = text.count(PROTECT_END)
    if n_start != 1:
        problems.append(Problem(skill, "I1", f"WRITING-STYLE:START 出现 {n_start} 次（应为 1）"))
    if n_end != 1:
        problems.append(Problem(skill, "I1", f"WRITING-STYLE:END 出现 {n_end} 次（应为 1）"))
    if n_start == 1 and n_end == 1 and text.index(PROTECT_START) > text.index(PROTECT_END):
        problems.append(Problem(skill, "I1", "START 在 END 之后，顺序错误"))

    # I2 索引指针
    if "REFERENCES-INDEX" in text:
        for rel in re.findall(r"\(references/([a-z0-9_.-]+\.md)\)", text):
            if not (md_path.parent / "references" / rel).exists():
                problems.append(Problem(skill, "I2", f"索引指向不存在的 references/{rel}"))

    # I3 frontmatter name
    m = FRONTMATTER.match(text)
    if not m:
        problems.append(Problem(skill, "I3", "缺少 YAML 前置块"))
    else:
        nm = re.search(r"^name:\s*(\S+)", m.group(1), re.M)
        if not nm:
            problems.append(Problem(skill, "I3", "缺少 name"))
        elif nm.group(1) != skill:
            problems.append(Problem(skill, "I3", f"name={nm.group(1)} 与目录名 {skill} 不一致"))

    # I4 重复 H2
    titles = [t.strip() for t in H2_RE.findall(text)]
    seen: Dict[str, int] = {}
    for t in titles:
        seen[t] = seen.get(t, 0) + 1
    dups = [t for t, c in seen.items() if c > 1]
    if dups:
        problems.append(Problem(skill, "I4", f"重复 H2 标题 {len(dups)} 个：{dups[:3]}"))

    # I5 质检清单
    if "质检清单" not in text:
        problems.append(Problem(skill, "I5", "缺少「质检清单」章节"))

    # I6 空章节（标题后紧接另一个标题）
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not H2_RE.match(line):
            continue
        nxt = i + 1
        while nxt < len(lines) and not lines[nxt].strip():
            nxt += 1
        # 只有「## 标题后紧跟另一个 ## 标题」才算空章节；
        # 后接 ### 子标题是正常结构，不算空
        if nxt < len(lines) and re.match(r"^##\s", lines[nxt]):
            problems.append(Problem(skill, "I6", f"空章节：「{line.strip()[:40]}」"))

    return problems


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="35 个 SKILL.md 完整性验收")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    files = sorted(SUBSKILLS.glob("*/SKILL.md"))
    if not files:
        print("❌ 未找到 subskills/*/SKILL.md")
        return 2

    all_problems: List[Problem] = []
    for f in files:
        all_problems.extend(check_skill(f))

    if args.json:
        print(json.dumps({
            "passed": not all_problems,
            "skill_count": len(files),
            "problem_count": len(all_problems),
            "problems": [asdict(p) for p in all_problems],
        }, ensure_ascii=False, indent=2))
        return 0 if not all_problems else 1

    by_code: Dict[str, List[Problem]] = {}
    for p in all_problems:
        by_code.setdefault(p.code, []).append(p)

    labels = {
        "I1": "受保护块", "I2": "索引指针", "I3": "frontmatter name",
        "I4": "重复标题", "I5": "质检清单", "I6": "空章节",
    }

    print(f"验收 {len(files)} 个 SKILL.md\n")
    if not all_problems:
        print("✅ 全部通过（I1~I6 六项检查）")
        return 0

    for code in sorted(by_code):
        items = by_code[code]
        print(f"❌ [{code}] {labels.get(code, code)}：{len(items)} 项")
        for p in items[:10]:
            print(f"     {p.skill}: {p.detail}")
        if len(items) > 10:
            print(f"     …… 另有 {len(items) - 10} 项")
    print(f"\n共 {len(all_problems)} 项问题")
    return 1


if __name__ == "__main__":
    sys.exit(main())
