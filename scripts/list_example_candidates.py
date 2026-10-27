#!/usr/bin/env python3
"""List local example-review metadata; never approve, publish, or read private documents."""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def candidates() -> list[dict]:
    data_dir = Path(os.environ.get("PROPOSAL_AGENT_DATA_DIR") or ROOT / ".agent-data").expanduser().resolve()
    review_dir = data_dir / "rag" / "review"
    records = []
    if not review_dir.is_dir():
        return records
    for path in sorted(review_dir.glob("*-rights-review.json")):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 50_000:
            continue
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(item, dict):
            continue
        # Deliberately omit names, raw excerpts, credentials and local file paths.
        records.append({key: item.get(key) for key in (
            "record_id", "record_url", "declared_license", "candidate_track", "cross_track_note",
            "rights_conflict", "status", "reviewed_by_human", "privacy_reviewed", "approved")})
    return records


if __name__ == "__main__":
    items = candidates()
    print(json.dumps({"count": len(items), "candidates": items,
                      "note": "候选仅供人工审查；任何候选都不会自动进入公共 RAG。"}, ensure_ascii=False, indent=2))
