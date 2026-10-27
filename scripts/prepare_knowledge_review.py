#!/usr/bin/env python3
"""Create a non-overwriting, explicitly unreviewed 35-track evidence review CSV."""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "server/evals"))
from proposal.knowledge import public_sources
from knowledge_scoped import QUESTIONS

FIELDS = ("case_id", "skill_id", "query", "school", "application_year", "education_level", "college",
          "political_stage", "variant", "expected_source_id", "expected_official_absence", "source_url",
          "source_sha256", "review_status", "reviewer_id", "review_notes")


def rows():
    sources = {s["id"]: s for s in public_sources() if s["kind"] == "official"}
    for source_id, query in QUESTIONS.items():
        s = sources[source_id]
        restrictions = {key: values[0] for key, values in s.get("restrictions", {}).items()}
        scopes = (("match", s["school"], str(s["application_year"]), False),
                  ("missing_school", "", str(s["application_year"]), True),
                  ("wrong_school", "测试用不相干大学", str(s["application_year"]), True),
                  ("missing_year", s["school"], "", True),
                  ("wrong_year", s["school"], str(s["application_year"] + 1), True))
        for probe, school, year, absent in scopes:
            yield {"case_id": s["skill_id"] + ":" + probe, "skill_id": s["skill_id"], "query": query,
                   "school": school, "application_year": year,
                   "education_level": restrictions.get("education_level", ""),
                   "college": restrictions.get("college", ""),
                   "political_stage": restrictions.get("political_stage", ""),
                   "variant": s.get("variant", ""), "expected_source_id": "" if absent else source_id,
                   "expected_official_absence": "yes" if absent else "no", "source_url": s["source_url"],
                   "source_sha256": s["source_sha256"], "review_status": "pending", "reviewer_id": "", "review_notes": ""}
    for index, query in enumerate(("院级科研项目申请条件", "院级科研申报资格", "院级科研评审标准", "院级项目名额限制", "院级科研报名截止时间"), 1):
        yield {"case_id": f"college-research:missing-{index}", "skill_id": "college-research", "query": query,
               "school": "测试用不相干大学", "application_year": "2026", "expected_source_id": "",
               "expected_official_absence": "yes", "review_status": "pending", "reviewer_id": "", "review_notes": ""}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="raise")
        writer.writeheader()
        count = 0
        for row in rows():
            writer.writerow(row)
            count += 1
    print(f"已生成 {count} 条待审核候选；未标记为人工通过，不代表评测已完成。")


if __name__ == "__main__":
    main()
