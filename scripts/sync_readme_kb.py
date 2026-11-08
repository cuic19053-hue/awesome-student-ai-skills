#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_readme_kb.py — 把 README 赛道表的「内容量 KB」同步为 SKILL.md 实际字节数。

为什么需要
----------
`scripts/check_doc_consistency.py` 有硬门禁：README 标称 KB 与实际字节数
（/1000 四舍五入）相差 >1KB 即失败。向 35 个子 skill 注入写作规范后，
每个文件增长约 5~6KB，门禁必然全红。本脚本负责把数字同步回去。

口径与门禁完全一致：round(size_bytes / 1000)。

用法
----
    python3 scripts/sync_readme_kb.py --dry-run
    python3 scripts/sync_readme_kb.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
SUBSKILLS = ROOT / "subskills"

# 与 check_doc_consistency.README_ROW 保持一致
ROW_RE = re.compile(
    r"^(\|\s*\d+\s*\|\s*[^|]+?\s*\|\s*`([a-z0-9_-]+)`\s*\|\s*)(\d+)(\s*KB\s*\|)",
    re.M,
)


def actual_kb(code: str) -> int | None:
    md = SUBSKILLS / code / "SKILL.md"
    if not md.exists():
        return None
    return round(md.stat().st_size / 1000)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="同步 README 赛道表 KB 数字")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写盘")
    args = ap.parse_args(argv)

    if not README.exists():
        print(f"❌ README 不存在：{README}")
        return 2

    text = README.read_text(encoding="utf-8")
    changes: List[Tuple[str, int, int]] = []

    def _sub(m: re.Match) -> str:
        prefix, code, old_kb, suffix = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        new_kb = actual_kb(code)
        if new_kb is None:
            return m.group(0)
        if new_kb != old_kb:
            changes.append((code, old_kb, new_kb))
        return f"{prefix}{new_kb}{suffix}"

    new_text = ROW_RE.sub(_sub, text)

    if not changes:
        print("✅ README KB 数字已是最新，无需修改")
        return 0

    print(f"{'将更新' if args.dry_run else '已更新'} {len(changes)} 行：")
    for code, old, new in changes:
        print(f"  - {code}: {old}KB → {new}KB")

    if not args.dry_run:
        README.write_text(new_text, encoding="utf-8")
        print("\n请重跑门禁：python3 scripts/check_doc_consistency.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
