"""Verify that the routing entry can load its advertised skills and API example."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
SKILLS = {skill["name"]: skill for skill in INDEX["skills"]}


def test_root_routing_paths_resolve_to_indexed_skills():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    names = re.findall(r"`subskills/([a-z0-9_-]+)/`", text)
    assert len(names) == len(SKILLS)
    assert set(names) == set(SKILLS)
    for name in names:
        skill = SKILLS[name]
        assert ROOT.joinpath(skill["skill_md_path"]).is_file()
        assert ROOT.joinpath(skill["build_py_path"]).is_file()


def test_root_manual_tree_covers_canonical_skill_names():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    blocks = re.findall(r"^```([^\n]*)\n(.*?)^```[ \t]*$", text, re.M | re.S)
    trees = [body for language, body in blocks if not language.strip()]
    assert trees, "The routing entry must include a manual decision tree"
    targets = re.findall(r"\u2192 ([a-z0-9_-]+)", "\n".join(trees))
    assert set(targets) == set(SKILLS)
    assert len(targets) == len(SKILLS)


def test_documented_dispatch_api_example_executes(capsys):
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    examples = re.findall(r"```python\n(.*?)\n```", text, re.S)
    assert examples, "The routing entry must include an executable Python example"
    namespace = {}
    for example in examples:
        exec(compile(example, str(ROOT / "SKILL.md"), "exec"), namespace)

    candidates = namespace["candidates"]
    assert isinstance(candidates, list) and candidates
    top = candidates[0]
    assert top["name"] == "national-project-eval"
    assert isinstance(top["score"], int) and top["score"] > 0
    assert top["matched"]
    assert top["skill_md_path"] == SKILLS[top["name"]]["skill_md_path"]
    assert ROOT.joinpath(top["skill_md_path"]).is_file()
    output = capsys.readouterr().out
    assert top["name"] in output
    assert top["skill_md_path"] in output


def test_english_quickstart_skill_paths_resolve():
    text = (ROOT / "README_EN.md").read_text(encoding="utf-8")
    paths = re.findall(r"`(subskills/[a-z0-9_-]+/SKILL\.md)`", text)
    assert paths
    indexed_paths = {skill["skill_md_path"] for skill in SKILLS.values()}
    for path in paths:
        assert path in indexed_paths
        assert ROOT.joinpath(path).is_file()


def test_subskill_navigation_lists_all_indexed_skills_once():
    page = ROOT / "subskills" / "README.md"
    text = page.read_text(encoding="utf-8")
    paths = re.findall(r"\]\(\./([a-z0-9_-]+/SKILL\.md)\)", text)
    assert len(paths) == len(SKILLS)
    assert {"subskills/" + path for path in paths} == {
        skill["skill_md_path"] for skill in SKILLS.values()
    }
    for path in paths:
        assert page.parent.joinpath(path).is_file()
