"""校验试点资料本身的一致性；不代表模型效果或线上流程通过验收。"""

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pytest

DATA = (
    Path(__file__).resolve().parents[1]
    / "server/evals/fixtures/innovation_research/seu_2026"
)
RULES = json.loads((DATA / "rules.json").read_text(encoding="utf-8"))
CASES = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))


def test_official_rules_have_retrievable_sources():
    assert CASES["rules_id"] == RULES["id"]
    for source in RULES["sources"].values():
        assert urlparse(source["url"]).hostname == "jwc.seu.edu.cn"
        assert len(source["sha256"]) == 64
        int(source["sha256"], 16)
    for requirement in RULES["requirements"]:
        assert requirement["source"] in RULES["sources"]
        assert requirement["locator"] and requirement["rule"]
    assert date.fromisoformat(RULES["retrieved_date"]) > date(2026, 4, 20)


def test_synthetic_inputs_are_separate_from_official_sources():
    assert CASES["synthetic"] is True
    assert "不代表" in CASES["disclaimer"]
    inputs = CASES["simulated_inputs"]
    assert len({item["id"] for item in inputs}) == len(inputs)
    assert all(item["kind"] in {"idea", "plan"} for item in inputs)
    assert not ({item["id"] for item in inputs} & RULES["sources"].keys())
    assert {case["stage"] for case in CASES["cases"]} == {"idea", "partial", "draft"}


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda case: case["id"])
def test_each_stage_only_references_available_inputs_and_defined_checks(case):
    available = {item["id"] for item in CASES["simulated_inputs"]}
    assert set(case["input_ids"]) <= available
    assert set(case["expected_checks"]) <= CASES["acceptance_checks"].keys()
    assert {"scope", "eligibility", "missing_notice", "provenance"} <= set(case["expected_checks"])
    assert case["critical_unknowns"]
    if case["draft_path"]:
        path = (DATA / case["draft_path"]).resolve()
        assert path.is_relative_to(DATA.resolve()) and path.is_file()


def test_draft_has_all_template_sections_in_order():
    draft = (DATA / "draft.md").read_text(encoding="utf-8")
    assert "软件测试模拟初稿" in draft
    assert "不可直接提交" in draft
    assert "该批次已截止" in draft
    headings = [line for line in draft.splitlines() if line.startswith("## ")]
    assert [line.split("、", 1)[1] for line in headings] == RULES["top_level_sections"]
    rationale = [line.split(". ", 1)[1] for line in draft.splitlines() if line.startswith("### ")]
    assert rationale == [item["title"] for item in RULES["rationale_sections"]]
    for entity in ("指导教师", "院系", "学校"):
        assert f"【待{entity}审核" in draft
    assert "学校批准经费：【待审核】" in draft
    assert "600 | 600" in draft


@pytest.mark.parametrize("probe", CASES["adversarial_probes"], ids=lambda probe: probe["id"])
def test_adversarial_probes_are_not_mixed_into_source_facts(probe):
    assert probe["case_id"] in {case["id"] for case in CASES["cases"]}
    assert probe["expected_behavior"]
    assert bool(probe.get("user_request")) != bool(probe.get("untrusted_material"))
    assert probe["id"] not in {item["id"] for item in CASES["simulated_inputs"]}
