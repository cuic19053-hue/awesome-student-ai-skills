#!/usr/bin/env python3
"""Run one source-linked question per track with actual local embeddings/reranking.

This is an agent-curated smoke benchmark, not a human gold set or a production
latency claim. It never calls a cloud model or sends private project data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "server/evals"))
sys.path.insert(0, str(ROOT / "scripts"))
from proposal.knowledge import PublicKnowledgeRetriever, public_sources
from knowledge_scoped import QUESTIONS
from publish_public_knowledge import validate


def ollama_model_digest(model: str) -> str:
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
        data = json.load(response)
    names = {model} if ":" in model else {model, model + ":latest"}
    match = next((row for row in data.get("models", []) if row.get("name") in names), None)
    digest = (match or {}).get("digest", "")
    if len(digest) != 64:
        raise ValueError(f"本地模型 {model} 不可用或无法确认版本。")
    return digest


def current_fingerprint(sources: dict, model: str, model_digest: str, artifact: Path) -> str:
    metadata = [
        {"source": {key: value for key, value in source.items() if key != "chunks"},
         "chunks": [chunk["id"] for chunk in source["chunks"]]}
        for _, source in sorted(sources.items())
    ]
    code_paths = [
        Path(__file__), ROOT / "server/proposal/knowledge.py",
        ROOT / "server/proposal/local_public_vectors.py", ROOT / "server/proposal/local_reranker.py",
        ROOT / "server/proposal/retrieval.py",
    ]
    payload = {"sources": metadata, "reranker": model, "reranker_digest": model_digest,
               "questions": QUESTIONS,
               "code_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in code_paths},
               "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    artifact = args.index.expanduser().resolve()
    validate(artifact)
    digest = ollama_model_digest(args.model)
    sources = {s["id"]: s for s in public_sources() if s["kind"] in {"official", "institution_report"}}
    all_questions = dict(QUESTIONS)
    all_questions["henu-2024-college-research-review-report"] = "科创训练营项目答辩科学问题"
    fingerprint = current_fingerprint(sources, args.model, digest, artifact)
    previous = {}
    if args.output.exists():
        if not args.resume:
            raise SystemExit("输出已存在；为避免覆盖，请使用 --resume 或新路径。")
        with args.output.open(encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if record.get("fingerprint") != fingerprint:
                    raise SystemExit("来源、索引或模型版本已变化；请使用新输出文件。")
                previous[record["source_id"]] = record
    args.output.parent.mkdir(parents=True, exist_ok=True)
    old = {key: os.environ.pop(key, None) for key in ("RAG_LOCAL_VECTOR_INDEX", "RAG_LOCAL_RERANK_MODEL", "RAG_PUBLIC_DB_ENABLED", "RAG_CF_ENABLED")}
    results = []
    try:
        with args.output.open("a", encoding="utf-8") as handle:
            for number, (source_id, query) in enumerate(all_questions.items(), 1):
                if source_id in previous:
                    results.append(previous[source_id])
                    continue
                source = sources[source_id]
                filters = {key: values[0] for key, values in source.get("restrictions", {}).items()}
                searcher = PublicKnowledgeRetriever(object())
                os.environ.pop("RAG_LOCAL_VECTOR_INDEX", None)
                os.environ.pop("RAG_LOCAL_RERANK_MODEL", None)
                start = time.perf_counter()
                keyword = searcher.search(source["skill_id"], query, source["school"], source["application_year"],
                                          filters=filters, variant=source.get("variant", ""))
                keyword_ms = (time.perf_counter() - start) * 1000
                os.environ["RAG_LOCAL_VECTOR_INDEX"] = str(artifact)
                os.environ["RAG_LOCAL_RERANK_MODEL"] = args.model
                start = time.perf_counter()
                hybrid = searcher.search(source["skill_id"], query, source["school"], source["application_year"],
                                         filters=filters, variant=source.get("variant", ""))
                hybrid_ms = (time.perf_counter() - start) * 1000
                record = {"fingerprint": fingerprint, "source_id": source_id, "skill_id": source["skill_id"],
                          "query": query, "keyword_ms": round(keyword_ms, 2), "hybrid_ms": round(hybrid_ms, 2),
                          "keyword_source_found": source_id in {x["source_id"] for x in keyword.get("results", [])},
                          "hybrid_source_found": source_id in {x["source_id"] for x in hybrid.get("results", [])},
                          "retrieval_mode": hybrid.get("retrieval_mode"), "reranked": hybrid.get("reranked", False),
                          "fallback_reason": hybrid.get("fallback_reason", ""),
                          "review_status": "not_human_reviewed"}
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                results.append(record)
                print(f"[{number}/{len(all_questions)}] {source['skill_id']} mode={record['retrieval_mode']} reranked={record['reranked']} ms={record['hybrid_ms']}", flush=True)
        durations = sorted(item["hybrid_ms"] for item in results)
        summary = {"cases": len(results), "keyword_source_recall": round(sum(x["keyword_source_found"] for x in results)/len(results), 4),
                   "hybrid_source_recall": round(sum(x["hybrid_source_found"] for x in results)/len(results), 4),
                   "reranked": sum(x["reranked"] for x in results),
                   "fallbacks": sum(bool(x["fallback_reason"]) for x in results),
                   "latency_ms_p50": round(statistics.median(durations), 2),
                   "latency_ms_p95": durations[min(len(durations)-1, int(len(durations)*.95))],
                   "note": "本机来源关联合成用例；非人工金标准、非生产延迟。"}
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    finally:
        for key in ("RAG_LOCAL_VECTOR_INDEX", "RAG_LOCAL_RERANK_MODEL", "RAG_PUBLIC_DB_ENABLED", "RAG_CF_ENABLED"):
            if old[key] is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old[key]


if __name__ == "__main__":
    main()
