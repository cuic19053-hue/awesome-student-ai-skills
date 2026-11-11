"""Every advertised track can be reviewed without borrowing another track's identity."""
import json
from pathlib import Path

import pytest
from docx import Document

import utils.review_simulator as review


ROOT = Path(__file__).resolve().parents[1]
NEW_HEURISTICS = (
    "military_enlistment", "csc_scholarship", "exchange_program",
    "internet_plus_red_tour", "outstanding_thesis", "youth_league_conversion",
    "national_project_eval",
)


def test_every_catalogue_track_has_a_review_configuration():
    catalogue = json.loads((ROOT / "index.json").read_text())
    for item in catalogue["skills"]:
        skill = item["name"].replace("-", "_")
        simulator = review.ReviewSimulator(skill)
        assert simulator.skill_config["name"]
        assert sum(d["weight"] for d in simulator.skill_config["dimensions"]) == 100


@pytest.mark.parametrize("skill", NEW_HEURISTICS)
def test_new_profiles_need_text_instead_of_automatic_baseline_scores(skill, monkeypatch):
    monkeypatch.setattr(review, "check_plagiarism", None)
    sim = review.ReviewSimulator(skill)
    empty = sim.simulate_review()
    assert empty.total_score == 0
    assert not empty.passed
    assert "正式" in empty.review_scope
    assert not empty.veto_triggered  # Missing prose does not establish ineligibility.

    # Cover exactly this track's declared writing signals; these are not facts.
    sim.application_text = "。".join(group[0] for d in sim.skill_config["dimensions"]
                                    for group in d["text_signals"])
    covered = sim.simulate_review()
    assert covered.total_score == 100
    assert covered.passed
    assert "可正式提交" not in covered.overall_comment
    assert "关键词出现不证明" in covered.dimensions[0].comment
    assert all(item in covered.improvements for item in sim.skill_config["manual_review"])


def test_project_logic_and_national_scholarship_are_distinct_reviews():
    project = review.ReviewSimulator("national_project_eval")
    scholarship = review.ReviewSimulator("national_scholarship")
    assert project.skill_config["name"] == "国家级项目立项逻辑评测"
    assert scholarship.skill_config["name"] == "国家奖学金"
    assert not project.skill_config["hard_gates"]
    assert "gpa_rank_top" in scholarship.skill_config["hard_gates"]
    assert {d["name"] for d in project.skill_config["dimensions"]} != {
        d["name"] for d in scholarship.skill_config["dimensions"]}


def test_new_review_notice_survives_json_and_word_export(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "check_plagiarism", None)
    sim = review.ReviewSimulator("outstanding_thesis", application_text="论文题目：一个实验课题。")
    result = sim.simulate_review()
    assert json.loads(result.to_json())["review_scope"] == result.review_scope
    sim.generate_review_report(str(tmp_path / "review.docx"))
    text = "\n".join(p.text for p in Document(tmp_path / "review.docx").paragraphs)
    assert result.review_scope in text
    assert sim.skill_config["manual_review"][0] in text
