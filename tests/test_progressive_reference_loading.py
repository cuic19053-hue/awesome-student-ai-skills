"""Regression coverage for reference access from MCP and the chat runtime."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import server.app  # Registers the server module path.
from proposal.skills import invoke_discovery_tool, safe_skill_reference


def test_chat_can_load_filtered_intake_reference_and_reject_traversal():
    project = {"state": {"skill_id": "grant-application"}}
    first = invoke_discovery_tool("load_skill_guidance", {"skill_id": "grant-application"}, project)
    name = "references/intake-checklist.md"
    assert name in first["available_references"]
    result = invoke_discovery_tool("load_skill_guidance", {
        "skill_id": "grant-application", "reference": name,
    }, project)
    assert "difficulty_level" in result["guidance"]
    assert "difficulty_cert_no" in result["guidance"]
    assert "张三" not in result["guidance"]
    assert "GZ2024" not in result["guidance"]
    assert "error" in invoke_discovery_tool("load_skill_guidance", {
        "skill_id": "grant-application", "reference": "../../.env",
    }, project)
    assert "error" in invoke_discovery_tool("load_skill_guidance", {
        "skill_id": "challenge-cup", "reference": name,
    }, project)


def test_reference_symlink_cannot_escape_skill_directory(tmp_path):
    skill = tmp_path / "skill"
    (skill / "references").mkdir(parents=True)
    path = skill / "SKILL.md"
    path.write_text("[guide](references/intake-checklist.md)", encoding="utf-8")
    secret = tmp_path / "secret.md"
    secret.write_text("secret", encoding="utf-8")
    (skill / "references" / "intake-checklist.md").symlink_to(secret)
    assert safe_skill_reference(path, "references/intake-checklist.md") is None


@pytest.mark.skipif(importlib.util.find_spec("mcp") is None, reason="mcp not installed")
def test_mcp_requirements_include_real_externalized_intake():
    path = Path(__file__).resolve().parents[1] / "mcp_server.py"
    spec = importlib.util.spec_from_file_location("progressive_root_mcp", path)
    assert spec and spec.loader
    mcp_server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mcp_server)

    sections = mcp_server.get_skill_requirements("grant-application")["key_sections"]
    checklist = sections["信息采集参考：references/intake-checklist.md"]
    assert "difficulty_level" in checklist and "difficulty_cert_no" in checklist
    assert "张三" not in checklist and "GZ2024" not in checklist

    sections = mcp_server.get_skill_requirements("class-collective")["key_sections"]
    assert "class_name" in sections["信息采集参考：references/json-schema.md"]
