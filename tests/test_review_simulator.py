"""Regression tests for configured review pass thresholds."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from utils.review_simulator import DimensionScore, ReviewSimulator, compare_applicants


ROOT = Path(__file__).resolve().parent.parent
NATIONAL_APPLICANT = {
    "gpa_rank_percent": 5,
    "comprehensive_rank_percent": 5,
    "papers": [{"level": "SCI", "author_order": 1}],
    "volunteer_hours": 100,
}


def test_real_score_below_national_threshold_fails():
    sim = ReviewSimulator("national_project_eval", applicant_data=NATIONAL_APPLICANT)

    result = sim.simulate_review()

    assert sim.skill_config["threshold_pass"] == 85
    assert result.total_score == 84.5
    assert result.grade == "B"
    assert not result.veto_triggered
    assert result.passed is False
    assert "\u672a\u901a\u8fc7\u9884\u5ba1" in result.overall_comment
    assert "\u5efa\u8bae\u901a\u8fc7" not in result.overall_comment


def test_real_score_above_transfer_threshold_passes():
    sim = ReviewSimulator("major_transfer", applicant_data={"gpa_rank_percent": 20})

    result = sim.simulate_review()

    assert sim.skill_config["threshold_pass"] == 75
    assert result.total_score == 77.85
    assert result.grade == "C"
    assert not result.veto_triggered
    assert result.passed is True
    assert "\u53ef\u6b63\u5f0f\u63d0\u4ea4" in result.overall_comment
    assert "\u5f85\u5b9a" not in result.overall_comment


@pytest.mark.parametrize(
    "configured_threshold,score,expected_pass,expected_grade",
    [
        (85, 84.99, False, "B"),
        (85, 85, True, "B"),
        (85, 85.01, True, "B"),
        (75, 74.99, False, "C"),
        (75, 75, True, "C"),
        (75, 75.01, True, "C"),
        (None, 79.99, False, "C"),
        (None, 80, True, "B"),
        (None, 80.01, True, "B"),
    ],
)
def test_threshold_boundaries(
    monkeypatch, configured_threshold, score, expected_pass, expected_grade
):
    sim = ReviewSimulator("national_project_eval", applicant_data=NATIONAL_APPLICANT)
    if configured_threshold is None:
        sim.skill_config.pop("threshold_pass")
    else:
        sim.skill_config["threshold_pass"] = configured_threshold
    monkeypatch.setattr(
        sim,
        "_score_dimensions",
        lambda: [DimensionScore("score", 100, 100, score, score)],
    )

    result = sim.simulate_review()

    assert not result.veto_triggered
    assert result.total_score == score
    assert result.passed is expected_pass
    assert result.grade == expected_grade


def test_veto_overrides_score_above_threshold():
    applicant = {**NATIONAL_APPLICANT, "has_discipline_record": True}
    sim = ReviewSimulator("national_project_eval", applicant_data=applicant)
    sim.skill_config["threshold_pass"] = 50

    result = sim.simulate_review()

    assert result.veto_triggered
    assert result.total_score > sim.skill_config["threshold_pass"]
    assert result.grade == "D"
    assert result.passed is False


def test_cli_returns_failure_below_configured_threshold(tmp_path):
    data_path = tmp_path / "applicant.json"
    data_path.write_text(json.dumps(NATIONAL_APPLICANT), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "utils/review_simulator.py",
            "--skill",
            "national_project_eval",
            "--data",
            str(data_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )

    assert proc.returncode == 1, proc.stderr
    result = json.loads(proc.stdout)
    assert result["total_score"] == 84.5
    assert result["grade"] == "B"
    assert result["passed"] is False


def test_compare_applicants_uses_configured_pass_results():
    comparison = compare_applicants(
        [
            {"skill_name": "national_project_eval", "applicant_data": NATIONAL_APPLICANT},
            {"skill_name": "major_transfer", "applicant_data": {"gpa_rank_percent": 20}},
        ]
    )

    ranking = comparison["ranking"]
    assert [entry["original_index"] for entry in ranking] == [1, 0]
    assert [entry["passed"] for entry in ranking] == [True, False]


def test_cli_plain_output_does_not_recommend_pass_below_threshold(tmp_path):
    data_path = tmp_path / "applicant.json"
    data_path.write_text(json.dumps(NATIONAL_APPLICANT), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "utils/review_simulator.py",
            "--skill",
            "national_project_eval",
            "--data",
            str(data_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )

    assert proc.returncode == 1, proc.stderr
    assert "84.5/100" in proc.stdout
    assert "B - \u826f" in proc.stdout
    assert "\u672a\u901a\u8fc7\u9884\u5ba1" in proc.stdout
    assert "\u5efa\u8bae\u901a\u8fc7" not in proc.stdout
    assert "\u63a8\u8350\u901a\u8fc7" not in proc.stdout
