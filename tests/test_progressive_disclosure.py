# -*- coding: utf-8 -*-
"""渐进式披露重构工具的测试。

重点锁住一个已修复的真实缺陷：
重构时若把「写作规范块」内部的 `## ` 标题当作章节边界，
会把 START 标记卷进外移章节，导致规范块被截断、门禁失效。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from progressive_disclosure import (  # noqa: E402
    PROTECT_END,
    PROTECT_START,
    _split_sections,
    refactor_skill,
)

SCRIPT = ROOT / "scripts" / "progressive_disclosure.py"


# --- 章节切分：保护块不被切碎 ---

def test_protected_block_not_split_by_inner_headings():
    lines = [
        "## 一、正文\n",
        "内容\n",
        PROTECT_START + "\n",
        "## 块内标题（不应成为章节边界）\n",
        "### 子标题\n",
        "块内内容\n",
        PROTECT_END + "\n",
        "## 二、后续章节\n",
        "内容\n",
    ]
    sections = _split_sections(lines)
    titles = [s.title for s in sections]
    assert "块内标题（不应成为章节边界）" not in titles, "保护块内的标题被误判为章节"
    assert titles == ["一、正文", "二、后续章节"]


def test_section_range_truncated_at_protected_block():
    lines = [
        "## 一、大章节\n",
        "内容\n",
        PROTECT_START + "\n",
        "## 写作风格硬约束\n",
        "块内容\n",
        PROTECT_END + "\n",
        "## 二、下一章\n",
    ]
    sections = _split_sections(lines)
    first = sections[0]
    # 第一章必须止于保护块起点，不能把块吞进去
    assert first.end == 2, f"章节跨越了保护块，end={first.end}"
    assert PROTECT_START not in "".join(first.lines)


# --- 端到端：用真实 skill 的副本验证 ---

@pytest.fixture
def sandbox_skill(tmp_path, monkeypatch):
    """在临时目录构造一个含保护块的可重构 skill。"""
    import progressive_disclosure as pd

    sub = tmp_path / "subskills"
    sd = sub / "demo-skill"
    sd.mkdir(parents=True)
    md = sd / "SKILL.md"
    md.write_text(
        "---\nname: demo-skill\ndescription: 演示\n---\n\n"
        "## 一、适用场景\n内容\n\n"
        "## 三、信息采集清单\n"
        + "\n".join(f"- 字段 {i}" for i in range(60))
        + "\n\n"
        + PROTECT_START + "\n## 写作风格硬约束（去 AI 味 · 强制）\n"
        + "每个句子都必须能落到具体的人、事、时间、数字或对象上。\n"
        + "及格线 75。\n"
        + PROTECT_END + "\n\n"
        "## 二十、质检清单\n- 检查字数\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pd, "SUBSKILLS", sub)
    return md


def test_refactor_preserves_protected_block(sandbox_skill):
    result = refactor_skill("demo-skill", max_move=4, dry_run=False)
    assert result["moved"], "应至少外移一个章节"
    text = sandbox_skill.read_text(encoding="utf-8")
    assert text.count(PROTECT_START) == 1
    assert text.count(PROTECT_END) == 1
    assert "每个句子都必须能落到具体的人、事、时间、数字或对象上" in text, "保护块内容丢失"
    assert "及格线 75" in text


def test_refactor_moves_section_to_references(sandbox_skill):
    result = refactor_skill("demo-skill", max_move=4, dry_run=False)
    slugs = [m["slug"] for m in result["moved"]]
    assert "intake-checklist" in slugs
    ref = sandbox_skill.parent / "references" / "intake-checklist.md"
    assert ref.exists(), "references 文件未生成"
    assert "字段 0" in ref.read_text(encoding="utf-8"), "外移内容不完整"


def test_refactor_leaves_pointer(sandbox_skill):
    refactor_skill("demo-skill", max_move=4, dry_run=False)
    text = sandbox_skill.read_text(encoding="utf-8")
    assert "已外移至 references/intake-checklist.md" in text
    assert "何时阅读" in text


def test_refactor_dry_run_does_not_write(sandbox_skill):
    before = sandbox_skill.read_text(encoding="utf-8")
    result = refactor_skill("demo-skill", max_move=4, dry_run=True)
    assert result["moved"], "预览也应报告可外移章节"
    assert sandbox_skill.read_text(encoding="utf-8") == before, "dry-run 不应写盘"
    assert not (sandbox_skill.parent / "references").exists()


def test_refactor_skips_small_sections(sandbox_skill):
    """小于 min_lines 的章节不外移，避免碎片化。"""
    result = refactor_skill("demo-skill", max_move=4, dry_run=False, min_lines=1000)
    assert result["moved"] == []


def test_refactor_multiple_passes_preserves_existing_references(tmp_path, monkeypatch):
    """分批外移同类章节时，保留先前的内容和指针。"""
    import progressive_disclosure as pd

    sub = tmp_path / "subskills"
    skill_dir = sub / "demo-skill"
    skill_dir.mkdir(parents=True)
    md = skill_dir / "SKILL.md"
    md.write_text(
        "## 附录甲\n" + "原文甲\n" * 40
        + "## 附录乙\n" + "原文乙\n" * 40,
        encoding="utf-8",
    )
    monkeypatch.setattr(pd, "SUBSKILLS", sub)

    first = refactor_skill("demo-skill", max_move=1, dry_run=False)
    first_ref = skill_dir / "references" / "appendix.md"
    first_content = first_ref.read_text(encoding="utf-8")
    preview = refactor_skill("demo-skill", max_move=1, dry_run=True)
    second = refactor_skill("demo-skill", max_move=1, dry_run=False)

    assert first["moved"][0]["slug"] == "appendix"
    assert preview["moved"][0]["slug"] == second["moved"][0]["slug"] == "appendix-2"
    assert first_ref.read_text(encoding="utf-8") == first_content
    assert "原文甲" in first_content
    assert "原文乙" in (skill_dir / "references" / "appendix-2.md").read_text(encoding="utf-8")
    text = md.read_text(encoding="utf-8")
    assert "](references/appendix.md)" in text
    assert "](references/appendix-2.md)" in text


# --- CLI ---

def test_cli_dry_run_runs():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--skill", "challenge-cup", "--dry-run"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr


def test_cli_requires_target():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode != 0


# --- 全仓一致性（重构后）---

def test_all_skills_have_references_when_refactored():
    """重构后每个 skill 都应带 references 索引，且指针路径可达。"""
    subskills = ROOT / "subskills"
    problems = []
    for md in sorted(subskills.glob("*/SKILL.md")):
        text = md.read_text(encoding="utf-8")
        if "REFERENCES-INDEX" not in text:
            continue
        for rel in re.findall(r"\(references/([a-z0-9_-]+\.md)\)", text):
            if not (md.parent / "references" / rel).exists():
                problems.append(f"{md.parent.name}: 指针指向不存在的 {rel}")
    assert not problems, "指针断链：" + "；".join(problems)


def test_writing_style_block_survives_refactor_globally():
    """重构后 35 个 skill 的写作规范块必须仍然完整。"""
    subskills = ROOT / "subskills"
    broken = []
    for md in sorted(subskills.glob("*/SKILL.md")):
        text = md.read_text(encoding="utf-8")
        if text.count(PROTECT_START) != 1 or text.count(PROTECT_END) != 1:
            broken.append(md.parent.name)
    assert not broken, f"规范块被破坏：{broken}"


def test_no_reference_file_contains_style_markers():
    """外移文件里不应混入写作规范标记（防止块被切碎）。"""
    subskills = ROOT / "subskills"
    dirty = []
    for ref in subskills.glob("*/references/*.md"):
        content = ref.read_text(encoding="utf-8")
        if PROTECT_START in content or PROTECT_END in content:
            dirty.append(str(ref.relative_to(ROOT)))
    assert not dirty, f"references 混入规范标记：{dirty}"
