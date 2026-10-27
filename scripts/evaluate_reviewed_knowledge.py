#!/usr/bin/env python3
"""Evaluate only reviewer-approved source labels; never certify claim support automatically."""
from __future__ import annotations
import argparse
import collections
import csv
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from proposal.knowledge import PublicKnowledgeRetriever, public_sources
from proposal.skills import registry


def evaluate(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [row.get("case_id", "").strip() for row in rows]
    skills = {item["name"] for item in registry.skills}
    if len(rows) < 175 or len(ids) != len(set(ids)) or not all(ids):
        raise ValueError("需至少175条唯一的审核用例。")
    counts = collections.Counter(row.get("skill_id", "") for row in rows)
    if set(counts) != skills or any(counts[skill] < 5 for skill in skills):
        raise ValueError("每个赛道须至少5条审核用例。")
    if any(row.get("review_status") != "approved" or
           not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", row.get("reviewer_id", "")) for row in rows):
        raise ValueError("所有用例须由人工审核并填写非敏感审核编号；候选默认未审核。")
    searcher = PublicKnowledgeRetriever(object())
    official_sources = {source["id"]: source for source in public_sources() if source["kind"] == "official"}
    results = []
    for row in rows:
        query = row.get("query", "").strip()
        year_text = row.get("application_year", "").strip()
        if not query or (year_text and not re.fullmatch(r"(?:19|20|21)\d{2}", year_text)):
            raise ValueError(f"用例 {row['case_id']} 的问题或年度无效。")
        absence = row.get("expected_official_absence", "").strip().lower()
        expected = row.get("expected_source_id", "").strip()
        if absence not in {"yes", "no"} or (absence == "no" and not expected) or (absence == "yes" and expected):
            raise ValueError(f"用例 {row['case_id']} 的期望来源与拒答标记冲突。")
        reference_url = row.get("source_url", "").strip()
        reference_hash = row.get("source_sha256", "").strip()
        if expected:
            source = official_sources.get(expected)
            if (not source or source["skill_id"] != row["skill_id"]
                    or source["source_sha256"] != reference_hash
                    or source["source_url"] != reference_url):
                raise ValueError(f"用例 {row['case_id']} 的来源或版本已变化，须重新审核。")
        elif reference_url and not any(
            source["skill_id"] == row["skill_id"] and source["source_url"] == reference_url
            and source["source_sha256"] == reference_hash for source in official_sources.values()
        ):
            raise ValueError(f"用例 {row['case_id']} 的参考来源或版本已变化，须重新审核。")
        result = searcher.search(row["skill_id"], query, row.get("school", ""),
                                 int(year_text) if year_text else None, top_k=6,
                                 variant=row.get("variant", ""), filters={
                                     k: row.get(k, "") for k in ("education_level", "college", "political_stage")})
        official = [item for item in result.get("results", []) if item.get("kind") == "official"]
        found = {item.get("source_id") for item in official}
        passed = (not found if absence == "yes" else expected in found)
        results.append({"case_id": row["case_id"], "skill_id": row["skill_id"], "passed": passed,
                        "expected_source_id": expected, "found_source_ids": sorted(found),
                        "retrieval_mode": result.get("retrieval_mode", "unknown"),
                        "reranked": bool(result.get("reranked")),
                        "fallback_reason": result.get("fallback_reason", ""),
                        "human_claim_support_review": "not_reviewed"})
    return {"total": len(results), "skills": len(counts), "reviewer_claim": "self-reported; audit externally",
            "source_decision_accuracy": round(sum(item["passed"] for item in results) / len(results), 4),
            "retrieval_modes": dict(collections.Counter(item["retrieval_mode"] for item in results)),
            "reranked_count": sum(item["reranked"] for item in results),
            "fallback_count": sum(bool(item["fallback_reason"]) for item in results),
            "claim_support_status": "not_reviewed", "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(evaluate(args.input), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
