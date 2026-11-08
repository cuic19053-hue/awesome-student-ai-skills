#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_skill_description.py — 按 Anthropic 官方最佳实践校验 SKILL.md 的 description。

为什么需要
----------
官方文档（Skill authoring best practices）明确：技能启动时**只有 name 和
description 被预加载进系统提示**，它是唯一的「第一层渐进式披露」。
description 写坏了，技能就永远不会被触发；写太长了，35 个技能会白占
系统提示预算。

本仓现状（2026-11-08 基线）：35 个 description 合计 7750 字符，平均 221，
19 个超 200 字符，且部分把「栏目清单」写进了 description（那是正文该管的）。

校验项（对应官方原文）
----------------------
D1 长度       description 建议 ≤ 300 字符（硬上限 500）
D2 何时使用   必须说明「什么时候用」（中文：当/用于/适用于/需要/要写；
              英文：Use when / Use this skill when）
D3 触发词     metadata.triggers 至少 3 个，且与 description 有交集
D4 唯一性     与同名/近义 skill 的 description 不重复（Jaccard > 0.8 报警）
D5 结构      description 不应包含大段栏目清单（≥6 个「、」连缀）
D6 name 规范  name 必须小写 kebab-case，且与目录名一致

用法
----
    python3 scripts/check_skill_description.py
    python3 scripts/check_skill_description.py --json
    python3 scripts/check_skill_description.py --strict   # 警告也算失败
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SUBSKILLS = ROOT / "subskills"

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
NAME_RE = re.compile(r"^name:\s*(\S+)", re.M)
DESC_RE = re.compile(r"^description:\s*(.+?)(?=\n[a-z_]+:|\Z)", re.S | re.M)
TRIGGERS_RE = re.compile(r"^metadata:\s*\n(?:.*\n)*?\s*triggers:\s*\n((?:\s*-\s*.+\n)+)", re.M)

WHEN_MARKERS_ZH = ("当", "用于", "适用于", "需要", "要写", "生成", "撰写", "处理")
WHEN_MARKERS_EN = ("use when", "use this skill", "when the user", "trigger")

MAX_DESC_LEN = 300
HARD_DESC_LEN = 500
MIN_TRIGGERS = 3


@dataclass
class Issue:
    skill: str
    code: str
    severity: str   # "error" | "warning"
    message: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass
class SkillInfo:
    skill_id: str
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)

    @property
    def desc_len(self) -> int:
        return len(self.description)


def parse_skill(md_path: Path) -> SkillInfo | None:
    text = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER.match(text)
    if not m:
        return None
    fm = m.group(1)
    nm = NAME_RE.search(fm)
    dm = DESC_RE.search(fm)
    tm = TRIGGERS_RE.search(fm)

    triggers: List[str] = []
    if tm:
        triggers = [
            line.strip().lstrip("-").strip()
            for line in tm.group(1).splitlines()
            if line.strip().startswith("-")
        ]

    return SkillInfo(
        skill_id=md_path.parent.name,
        name=nm.group(1) if nm else "",
        description=dm.group(1).strip() if dm else "",
        triggers=triggers,
    )


def _jaccard(a: str, b: str, n: int = 3) -> float:
    def grams(s: str) -> set:
        s = re.sub(r"\s+", "", s)
        return {s[i:i + n] for i in range(len(s) - n + 1)} if len(s) >= n else {s}

    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def check(root: Path = ROOT) -> Tuple[List[Issue], List[SkillInfo]]:
    skills_dir = root / "subskills"
    issues: List[Issue] = []
    infos: List[SkillInfo] = []

    for md in sorted(skills_dir.glob("*/SKILL.md")):
        info = parse_skill(md)
        if info is None:
            issues.append(Issue(md.parent.name, "D0", "error", "缺少 YAML 前置块"))
            continue
        infos.append(info)
        sid = info.skill_id

        # D6 name 规范
        if not info.name:
            issues.append(Issue(sid, "D6", "error", "缺少 name"))
        elif info.name != sid:
            issues.append(Issue(sid, "D6", "error", f"name={info.name} 与目录名 {sid} 不一致"))
        elif not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", info.name):
            issues.append(Issue(sid, "D6", "error", f"name={info.name} 不符合 kebab-case"))

        # D1 长度
        if info.desc_len > HARD_DESC_LEN:
            issues.append(Issue(sid, "D1", "error", f"description {info.desc_len} 字符，超硬上限 {HARD_DESC_LEN}"))
        elif info.desc_len > MAX_DESC_LEN:
            issues.append(Issue(sid, "D1", "warning", f"description {info.desc_len} 字符，超建议上限 {MAX_DESC_LEN}"))

        # D2 何时使用
        low = info.description.lower()
        has_when = any(k in info.description for k in WHEN_MARKERS_ZH) or any(
            k in low for k in WHEN_MARKERS_EN
        )
        if not has_when:
            issues.append(Issue(sid, "D2", "warning", "description 未说明「何时使用」"))

        # D3 触发词
        if len(info.triggers) < MIN_TRIGGERS:
            issues.append(Issue(sid, "D3", "error", f"triggers 仅 {len(info.triggers)} 个，少于 {MIN_TRIGGERS}"))
        else:
            overlap = [t for t in info.triggers if t and t in info.description]
            if not overlap:
                issues.append(Issue(sid, "D3", "warning", "triggers 与 description 无任何交集（触发可能不稳）"))

        # D5 结构：栏目清单堆砌
        if info.description.count("、") >= 6:
            issues.append(Issue(sid, "D5", "warning", "description 含大段栏目清单，建议移到正文"))

    # D4 唯一性
    for i, a in enumerate(infos):
        for b in infos[i + 1:]:
            sim = _jaccard(a.description, b.description)
            if sim > 0.8:
                issues.append(
                    Issue(a.skill_id, "D4", "warning",
                          f"与 {b.skill_id} 的 description 相似度 {sim:.2f}，可能互相误触发")
                )

    return issues, infos


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SKILL.md description 官方最佳实践校验")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--strict", action="store_true", help="警告也视为失败")
    args = ap.parse_args(argv)

    issues, infos = check()
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    total_chars = sum(i.desc_len for i in infos)
    avg = total_chars / len(infos) if infos else 0

    if args.json:
        print(json.dumps({
            "passed": not errors and (not args.strict or not warnings),
            "skill_count": len(infos),
            "description_total_chars": total_chars,
            "description_avg_chars": round(avg, 1),
            "errors": [i.to_dict() for i in errors],
            "warnings": [i.to_dict() for i in warnings],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"共校验 {len(infos)} 个 skill")
        print(f"description 总字符 {total_chars}，平均 {avg:.0f}（预加载预算）\n")
        for w in warnings:
            print(f"⚠️  [{w.skill}] {w.code}: {w.message}")
        for e in errors:
            print(f"❌ [{e.skill}] {e.code}: {e.message}")
        print()
        if errors:
            print(f"{len(errors)} 项错误、{len(warnings)} 项警告 —— 未通过")
        elif args.strict and warnings:
            print(f"{len(warnings)} 项警告（--strict 视为失败）")
        else:
            print(f"✅ 通过（{len(warnings)} 项警告）")

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
