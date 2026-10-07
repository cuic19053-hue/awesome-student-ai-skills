# -*- coding: utf-8 -*-
"""端到端构建测试：抽样赛道用 --demo 生成真实 .docx（覆盖「文档可运行」这一主张）。"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# 抽样：覆盖奖学金类 / 政治身份类 / 科研类，且包含体积最小与最大的文档
SAMPLE_SKILLS = ["national-scholarship", "summary-report", "innovation-research"]


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
        [sys.executable, str(ROOT / "subskills" / "summary-report" / "build.py"),
         "--demo", "--out", str(out), "--school", "pku"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"--school 失败：{proc.stderr[-800:]}"
    assert out.stat().st_size > 0


def test_windows_gbk_encoding_safety(tmp_path):
    """验证 Issue #4：在严格 GBK 编码终端环境下运行 build.py 不触发 UnicodeEncodeError。"""
    import os
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "gbk:strict"
    out = tmp_path / "gbk_test.docx"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "subskills" / "innovation-research" / "build.py"),
         "--demo", "--out", str(out)],
        capture_output=True, env=env, cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"GBK 环境构建失败：{proc.stderr.decode('gbk', errors='replace')}"
    assert out.exists()


def test_scholarship_policy_181_compliance():
    """验证 Issue #5：国家奖助学金金额已同步财教〔2024〕181号新标准。"""
    import json
    idx = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
    skills_map = {s["name"]: s for s in idx["skills"]}

    # 国家奖学金 10000 元
    nat = skills_map.get("national-scholarship")
    assert nat is not None
    assert "10000" in nat["description"]
    assert "10000元" in nat["triggers"]

    # 国家励志奖学金 6000 元
    mot = skills_map.get("motivation-scholarship")
    assert mot is not None
    assert "6000" in mot["description"]
    assert "6000元" in mot["triggers"]

    # 国家助学金 2500-5000 自主范围
    grant = skills_map.get("grant-application")
    assert grant is not None
    assert "2500-5000" in grant["description"]
