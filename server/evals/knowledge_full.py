#!/usr/bin/env python3
"""Deterministic synthetic evidence-recall smoke test; not human-labelled validation."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from proposal.knowledge import PublicKnowledgeRetriever, is_policy_question, public_sources


def build_cases() -> list[dict]:
    samples = []
    for source in public_sources():
        if source["kind"] != "skill_guidance":
            continue
        used = set()
        for chunk in source["chunks"]:
            for line in chunk["content"].splitlines():
                if not re.match(r"^#{2,3}\s", line):
                    continue
                question = re.sub(r"^#{2,3}\s*", "", line).strip()
                question = re.sub(r"^[一二三四五六七八九十\d.、]+\s*", "", question).strip()
                question = re.sub(r"\s*（.*?）", "", question).strip()
                if len(question) < 4 or len(question) > 60 or question in used or is_policy_question(question):
                    continue
                used.add(question)
                samples.append({"skill_id": source["skill_id"], "query": question,
                                "expected_chunk_id": chunk["id"], "category": "heading_lookup"})
                break
            if len(used) == 5:
                break
        if len(used) != 5:
            raise ValueError(f"来源 {source['id']} 可用标题不足 5 条。")
    return samples


def evaluate() -> dict:
    # Reproducible/offline: do not contact Ollama or change the caller's env.
    old = {key: os.environ.pop(key, None) for key in ("RAG_LOCAL_VECTOR_INDEX", "RAG_LOCAL_RERANK_MODEL", "RAG_PUBLIC_DB_ENABLED")}
    try:
        searcher = PublicKnowledgeRetriever(object())
        samples = build_cases()
        failures = []
        for case in samples:
            result = searcher.search(case["skill_id"], case["query"], top_k=6)
            found = [item["id"] for item in result["results"]]
            if case["expected_chunk_id"] not in found:
                failures.append({**case, "returned_chunk_ids": found})
        return {"source": "synthetic non-policy headings from repository guidance; not official or human-labelled",
                "total": len(samples), "skills": len({s["skill_id"] for s in samples}),
                "recall_at_6": round((len(samples)-len(failures))/len(samples), 4), "failures": failures}
    finally:
        for key, value in old.items():
            if value is not None:
                os.environ[key] = value


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["recall_at_6"] >= .90 else 1)
