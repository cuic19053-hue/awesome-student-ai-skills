from __future__ import annotations
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server/evals"))
from local_model_coverage import current_fingerprint


def test_benchmark_fingerprint_changes_with_scope_and_artifact(tmp_path):
    artifact = tmp_path / "index.jsonl"
    artifact.write_text("first", encoding="utf-8")
    source = {"id": "source", "source_sha256": "a" * 64, "school": "甲大学",
              "application_year": 2026, "restrictions": {"education_level": ["本科"]},
              "chunks": [{"id": "chunk"}]}
    first = current_fingerprint({"source": source}, "qwen", "b" * 64, artifact)
    changed = copy.deepcopy(source)
    changed["restrictions"]["education_level"] = ["硕士"]
    assert current_fingerprint({"source": changed}, "qwen", "b" * 64, artifact) != first
    artifact.write_text("second", encoding="utf-8")
    assert current_fingerprint({"source": source}, "qwen", "b" * 64, artifact) != first
