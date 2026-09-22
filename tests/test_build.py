# -*- coding: utf-8 -*-
"""端到端构建测试：抽样赛道用 --demo 生成真实 .docx（覆盖「文档可运行」这一主张）。"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# 抽样：覆盖奖学金类 / 政治身份类 / 科研类，且包含体积最小与最大的文档
SAMPLE_SKILLS = ["national_scholarship", "summary_report", "innovation_research"]


@pytest.mark.parametrize("skill", SAMPLE_SKILLS)
def test_build_demo_creates_docx(skill, tmp_path):
    out = tmp_path / f"{skill}.docx"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "subskills" / skill / "build.py"), "--demo", "--out", str(out)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"build.py 失败：{proc.stderr[-800:]}"
    assert out.exists(), "未生成 docx"
    assert out.stat().st_size > 0, "生成的 docx 为空文件"


def test_school_template_option(tmp_path):
    """--school 应能套用版式且不报错。"""
    out = tmp_path / "pku.docx"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "subskills" / "summary_report" / "build.py"),
         "--demo", "--out", str(out), "--school", "pku"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"--school 失败：{proc.stderr[-800:]}"
    assert out.stat().st_size > 0
