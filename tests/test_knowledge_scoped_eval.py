from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "evals"))
from knowledge_scoped import evaluate


def test_source_linked_scope_probes_are_current():
    report = evaluate()
    assert report["skills"] == 35
    assert report["total"] == 175
    assert report["failures"] == []
    assert "not human-approved" in report["label"]
