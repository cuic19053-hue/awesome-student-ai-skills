# -*- coding: utf-8 -*-
"""文档一致性测试：35 个赛道文档、README 声称量、索引数量三者必须自洽。"""

import os
from pathlib import Path

from scripts.check_doc_consistency import check

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "subskills"


def test_doc_consistency():
    errors, _ = check()
    assert not errors, "文档一致性问题：\n" + "\n".join(errors)


def test_all_subskills_have_skill_md():
    dirs = sorted(d.name for d in SKILLS.iterdir() if d.is_dir())
    missing = [d for d in dirs if not (SKILLS / d / "SKILL.md").exists()]
    assert not missing, f"缺少 SKILL.md 的赛道：{missing}"
    assert len(dirs) == 35, f"期望 35 个赛道，实际 {len(dirs)}"


def test_all_subskills_have_build_py():
    dirs = sorted(d.name for d in SKILLS.iterdir() if d.is_dir())
    missing = [d for d in dirs if not (SKILLS / d / "build.py").exists()]
    assert not missing, f"缺少 build.py 的赛道：{missing}"


def test_readme_table_row_count():
    import re

    rows = re.findall(
        r"^\|\s*\d+\s*\|\s*[^|]+?\s*\|\s*`[a-z_]+`\s*\|\s*\d+\s*KB\s*\|",
        (ROOT / "README.md").read_text(encoding="utf-8"),
        re.M,
    )
    assert len(rows) == 35, f"README 赛道表 {len(rows)} 行，期望 35"
