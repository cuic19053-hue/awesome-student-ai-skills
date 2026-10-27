from __future__ import annotations
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_knowledge_review import FIELDS, rows
from evaluate_reviewed_knowledge import evaluate


def _write(path: Path, items):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(items)


def test_review_candidates_remain_unapproved_and_cannot_pass_gate(tmp_path):
    items = list(rows())
    assert len(items) == 175
    assert len({item["skill_id"] for item in items}) == 35
    assert all(item["review_status"] == "pending" for item in items)
    path = tmp_path / "cases.csv"
    _write(path, items)
    with pytest.raises(ValueError, match="人工审核"):
        evaluate(path)


def test_approved_fixture_never_certifies_claim_support_and_rejects_stale_source(tmp_path, monkeypatch):
    for key in ("RAG_LOCAL_VECTOR_INDEX", "RAG_LOCAL_RERANK_MODEL", "RAG_PUBLIC_DB_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    items = list(rows())
    for item in items:
        item["review_status"] = "approved"
        item["reviewer_id"] = "synthetic-test-only"
    path = tmp_path / "cases.csv"
    _write(path, items)
    report = evaluate(path)
    assert report["total"] == 175 and report["skills"] == 35
    assert report["claim_support_status"] == "not_reviewed"
    assert report["retrieval_modes"] == {"local_keyword": 175}
    assert report["reranked_count"] == 0
    assert all(row["human_claim_support_review"] == "not_reviewed" for row in report["results"])
    positive = next(item for item in items if item.get("expected_source_id"))
    positive["source_sha256"] = "0" * 64
    _write(path, items)
    with pytest.raises(ValueError, match="重新审核"):
        evaluate(path)
