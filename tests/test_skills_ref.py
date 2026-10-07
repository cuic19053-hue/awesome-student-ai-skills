# -*- coding: utf-8 -*-
"""Agent Skills 参考规范兼容性测试（Issue #8 验收用）。"""

from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
SUBSKILLS = ROOT / "subskills"


def test_all_35_skills_pass_skills_ref_validator():
    """验证 35 个子技能 100% 通过 skills-ref 参考格式校验，无任何报错。"""
    try:
        from skills_ref import validate
    except ImportError:
        pytest.skip("skills-ref 未安装")

    errors = {}
    for skill_dir in sorted(SUBSKILLS.iterdir()):
        if skill_dir.is_dir():
            errs = validate(skill_dir)
            if errs:
                errors[skill_dir.name] = errs

    assert not errors, f"以下子技能未通过 Agent Skills 参考规范校验：\n{errors}"
    assert len([d for d in SUBSKILLS.iterdir() if d.is_dir()]) == 35, "期望子技能数量为 35"
