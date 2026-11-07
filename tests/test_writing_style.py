# -*- coding: utf-8 -*-
"""写作规范注入链路的一致性测试。

锁住三件事：
1. 35 个子 skill 都注入了写作规范块，且只有一个块
2. 注入块内容与 docs/design/WRITING_STYLE.md 的核心判据一致
3. README 的 KB 数字与 SKILL.md 实际大小一致（门禁口径）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SUBSKILLS = ROOT / "subskills"
STYLE_DOC = ROOT / "docs" / "design" / "WRITING_STYLE.md"
README = ROOT / "README.md"

START_MARK = "<!-- WRITING-STYLE:START -->"
END_MARK = "<!-- WRITING-STYLE:END -->"

SKILL_FILES = sorted(SUBSKILLS.glob("*/SKILL.md"))
SKILL_IDS = [p.parent.name for p in SKILL_FILES]

ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*`([a-z0-9_-]+)`\s*\|\s*(\d+)\s*KB\s*\|", re.M
)


def test_all_35_subskills_present():
    assert len(SKILL_FILES) == 35, f"子 skill 数量应为 35，实际 {len(SKILL_FILES)}"


@pytest.mark.parametrize("skill_id", SKILL_IDS)
def test_writing_style_block_injected(skill_id: str):
    """每个子 skill 必须恰好包含一个写作规范块。"""
    text = (SUBSKILLS / skill_id / "SKILL.md").read_text(encoding="utf-8")
    assert text.count(START_MARK) == 1, f"{skill_id}: START 标记数量异常"
    assert text.count(END_MARK) == 1, f"{skill_id}: END 标记数量异常"
    assert text.index(START_MARK) < text.index(END_MARK), f"{skill_id}: 标记顺序错误"


@pytest.mark.parametrize("skill_id", SKILL_IDS)
def test_writing_style_block_precedes_qa_section(skill_id: str):
    """规范块必须出现在「质检清单」章节之前（写正文前先读到约束）。"""
    text = (SUBSKILLS / skill_id / "SKILL.md").read_text(encoding="utf-8")
    qa = re.search(r"^##\s.*质检清单.*$", text, re.M)
    assert qa is not None, f"{skill_id}: 缺少质检清单章节"
    assert text.index(START_MARK) < qa.start(), f"{skill_id}: 规范块位于质检清单之后"


@pytest.mark.parametrize("skill_id", SKILL_IDS)
def test_block_contains_core_rules(skill_id: str):
    """规范块必须包含六条硬约束与及格线，防止被误删。"""
    text = (SUBSKILLS / skill_id / "SKILL.md").read_text(encoding="utf-8")
    block = text[text.index(START_MARK):text.index(END_MARK)]
    for must_have in (
        "每个句子都必须能落到具体的人、事、时间、数字或对象上",
        "及格线 75",
        "ai_flavor_check.py",
        "plagiarism_checker.py",
        "review_simulator.py",
        "反模式",
    ):
        assert must_have in block, f"{skill_id}: 规范块缺少关键内容「{must_have}」"


def test_style_doc_exists_and_covers_six_dimensions():
    assert STYLE_DOC.exists(), "写作规范文档缺失"
    doc = STYLE_DOC.read_text(encoding="utf-8")
    for dim in ("空话套话", "排比对仗", "抽象名词", "具体性", "句长", "模板首尾"):
        assert dim in doc, f"规范文档缺少维度「{dim}」"
    assert "替换动作" in doc
    assert "反模式" in doc


def test_style_doc_forbids_known_cliches():
    """规范文档必须把已知套话列为禁用。"""
    doc = STYLE_DOC.read_text(encoding="utf-8")
    for phrase in ("具有重要意义", "高度重视", "不懈努力", "时光荏苒", "迈上新台阶"):
        assert phrase in doc, f"规范文档未收录禁用短语「{phrase}」"


def test_readme_kb_matches_actual_size():
    """README 的 KB 数字必须与 SKILL.md 实际大小一致（门禁口径）。"""
    rows = ROW_RE.findall(README.read_text(encoding="utf-8"))
    assert rows, "未能解析 README 赛道表"
    mismatches = []
    for _, _, code, kb in rows:
        md = SUBSKILLS / code / "SKILL.md"
        if not md.exists():
            mismatches.append(f"{code}: 目录缺失")
            continue
        actual = round(md.stat().st_size / 1000)
        if abs(actual - int(kb)) > 1:
            mismatches.append(f"{code}: 标称 {kb}KB，实际 {actual}KB")
    assert not mismatches, "README KB 未同步：" + "；".join(mismatches)


def test_inject_script_is_idempotent():
    """注入脚本必须幂等：再跑一次不应产生任何改动。"""
    import subprocess

    script = ROOT / "scripts" / "inject_writing_style.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
