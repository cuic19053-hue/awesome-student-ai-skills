"""Opt-in local-only vector index for approved public knowledge.

The artifact is an offline build product. User queries go only to loopback
Ollama; Vercel/cloud never depends on this host.
"""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any

from .retrieval import Embedder


@lru_cache(maxsize=2)
def _load_index(path: str, mtime_ns: int, size: int) -> dict[str, dict[str, Any]]:
    if size > 200_000_000:
        raise ValueError("向量索引超过大小上限。")
    with open(path, encoding="utf-8") as handle:
        data = [json.loads(line) for line in handle if line.strip()]
    return {item["source"]["id"]: item for item in data}


def _local_revision() -> str:
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as response:
        data = json.load(response)
    model = next((m for m in data.get("models", []) if m.get("name") in ("bge-m3", "bge-m3:latest")), {})
    digest = model.get("digest", "")
    if len(digest) != 64:
        raise ValueError("本地 bge-m3 模型版本不可用。")
    return "ollama:bge-m3:sha256:" + digest


def local_vector_candidates(sources: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Return only vectors bound to current content and the running model digest."""
    configured = os.environ.get("RAG_LOCAL_VECTOR_INDEX", "").strip()
    if not configured:
        return []
    path = Path(configured).expanduser().resolve()
    stat = path.stat()
    index = _load_index(str(path), stat.st_mtime_ns, stat.st_size)
    revision = _local_revision()
    embeddings = Embedder(base_url="http://127.0.0.1:11434", model="bge-m3").embed([query])
    if not embeddings or len(embeddings[0]) != 1024 or _local_revision() != revision:
        raise ValueError("查询向量不可用。")
    query_vector = embeddings[0]
    query_norm = math.sqrt(sum(float(x) * float(x) for x in query_vector))
    if not query_norm:
        raise ValueError("查询向量无效。")
    scores = []
    for source in sources:
        record = index.get(source["id"])
        metadata = {k: v for k, v in source.items() if k != "chunks"}
        if not record or record.get("source") != metadata:
            continue
        expected = {c["id"]: c for c in source["chunks"]}
        for item in record.get("chunks", []):
            chunk = expected.get(item.get("id"))
            if (not chunk or item.get("content") != chunk["content"]
                    or item.get("source_ref") != chunk["source_ref"]
                    or item.get("embedding_model") != "bge-m3"
                    or item.get("embedding_revision") != revision):
                continue
            vector = item.get("embedding")
            if (not isinstance(vector, list) or len(vector) != 1024
                    or any(not isinstance(n, (float, int)) or not math.isfinite(n) for n in vector)):
                continue
            norm = math.sqrt(sum(float(x) * float(x) for x in vector))
            if not norm:
                continue
            score = sum(float(x) * float(y) for x, y in zip(query_vector, vector)) / (query_norm * norm)
            if score > 0:
                scores.append({**metadata, **chunk, "source_id": source["id"],
                               "lexical_score": 0.0, "vector_score": score})
    scores.sort(key=lambda item: (-item["vector_score"], item["id"]))
    return scores[:30]
