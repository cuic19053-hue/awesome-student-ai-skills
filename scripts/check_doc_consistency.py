#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档一致性门禁（CI 用）。

必须通过（不一致则非零退出）：
  1. subskills/<id>/SKILL.md 必须存在
  2. SKILL.md 前置块须含 name / description / triggers，且 name 与目录名一致
  3. README 赛道表的「内容量 KB」与 SKILL.md 实际字节数（/1000 四舍五入）相差须 ≤ 1KB
  4. README 赛道表行数 == subskills 目录数 == index.json 的 total_skills

仅告警（不影响退出码，属已知待办）：
  - version.json 的 total_skills / skills 列表长度与实际不符

用法：
    python scripts/check_doc_consistency.py
    python scripts/check_doc_consistency.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent

README_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*`([a-z_]+)`\s*\|\s*(\d+)\s*KB\s*\|", re.M
)
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def check(root: Path = ROOT) -> Tuple[List[str], List[str]]:
    """返回 (errors, warnings)；errors 非空即门禁失败。"""
    errors: List[str] = []
    warnings: List[str] = []

    skills_dir = root / "subskills"
    if not skills_dir.is_dir():
        return ["subskills/ 目录不存在"], warnings
    dirs = sorted(d.name for d in skills_dir.iterdir() if d.is_dir())
    if not dirs:
        return ["subskills/ 下没有任何赛道目录"], warnings

    # --- 1 & 2: 文件存在 + 前置块合法 ---
    for name in dirs:
        md = skills_dir / name / "SKILL.md"
        if not md.exists():
            errors.append(f"[缺文件] subskills/{name}/SKILL.md 不存在")
            continue
        m = FRONTMATTER.match(md.read_text(encoding="utf-8"))
        if not m:
            errors.append(f"[前置块] subskills/{name}/SKILL.md 缺少 --- 前置块")
            continue
        fm = m.group(1)
        nm = re.search(r"^name:\s*(\S+)", fm, re.M)
        if not nm:
            errors.append(f"[前置块] subskills/{name}/SKILL.md 缺少 name")
        elif nm.group(1) != name:
            errors.append(f"[前置块] subskills/{name} 的 name={nm.group(1)} 与目录名不一致")
        if "description:" not in fm:
            errors.append(f"[前置块] subskills/{name}/SKILL.md 缺少 description")
        if "triggers:" not in fm:
            errors.append(f"[前置块] subskills/{name}/SKILL.md 缺少 triggers")

    # --- 3: README 声称内容量 vs 实际字节数 ---
    readme = root / "README.md"
    rows = README_ROW.findall(readme.read_text(encoding="utf-8")) if readme.exists() else []
    if not rows:
        errors.append("[README] 未能解析出赛道表（表格格式可能已变）")
    for _, _, code, kb in rows:
        md = skills_dir / code / "SKILL.md"
        if not md.exists():
            errors.append(f"[README] 表中 {code} 没有对应目录")
            continue
        actual = round(md.stat().st_size / 1000)
        if abs(actual - int(kb)) > 1:
            errors.append(f"[README] {code} 标称 {kb}KB，实际 {actual}KB（差 {abs(actual - int(kb))}KB）")

    # --- 4: 三处数量一致 ---
    idx_path = root / "index.json"
    if idx_path.exists():
        idx_total = json.loads(idx_path.read_text(encoding="utf-8")).get("total_skills")
        if idx_total is not None and idx_total != len(dirs):
            errors.append(f"[index.json] total_skills={idx_total}，磁盘目录数 {len(dirs)}，不一致")
    if rows and len(rows) != len(dirs):
        errors.append(f"[README] 赛道表 {len(rows)} 行，磁盘目录数 {len(dirs)}，不一致")

    # --- 告警：version.json 元数据（已知待更新，不阻断）---
    ver_path = root / "version.json"
    if ver_path.exists():
        ver = json.loads(ver_path.read_text(encoding="utf-8"))
        vt = ver.get("total_skills")
        if vt is not None and vt != len(dirs):
            warnings.append(f"[version.json] total_skills={vt}，实际 {len(dirs)}（元数据待更新）")
        vs = ver.get("skills")
        if isinstance(vs, list) and vs and len(vs) != len(dirs):
            warnings.append(f"[version.json] skills 列表 {len(vs)} 条，实际 {len(dirs)}（元数据待更新）")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="文档一致性门禁")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args()

    errors, warnings = check()
    if args.json:
        print(json.dumps(
            {"passed": not errors, "errors": errors, "warnings": warnings},
            ensure_ascii=False, indent=2,
        ))
    else:
        for w in warnings:
            print(f"⚠️  {w}")
        for e in errors:
            print(f"❌ {e}")
        if errors:
            print(f"\n共 {len(errors)} 项不一致 —— 门禁未通过")
        else:
            print(f"✅ 文档一致性检查通过（{len(warnings)} 条告警）")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
