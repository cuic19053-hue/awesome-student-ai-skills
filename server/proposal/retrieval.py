from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
from typing import Any

from .documents import split_into_chunks
from .storage import Store


class Embedder:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "bge-m3"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not texts:
            return []
        payload = json.dumps({"model": self.model, "input": texts}).encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                body = json.loads(response.read().decode("utf-8"))
            vectors = body.get("embeddings")
            if isinstance(vectors, list) and len(vectors) == len(texts):
                return vectors
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None
        return None


def _tokens(text: str) -> set[str]:
    # Chinese bigrams plus Latin/numeric words give a useful offline fallback.
    normalized = text.lower()
    words = set(re.findall(r"[a-z0-9][a-z0-9_.+-]*", normalized))
    chinese = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for run in chinese:
        words.update(run[i : i + 2] for i in range(max(len(run) - 1, 1)))
        if len(run) == 1:
            words.add(run)
    return words


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


class ProjectRetriever:
    def __init__(self, store: Store, embedder: Embedder | None = None):
        self.store = store
        self.embedder = embedder or Embedder()

    def index_document(self, document_id: str, extracted_text: str) -> int:
        chunks = split_into_chunks(extracted_text)
        vectors = self.embedder.embed([chunk for chunk in chunks])
        items = []
        document = self.store.get_document(document_id)
        if not document:
            return 0
        # Preserve page/paragraph references when they are present in extracted text.
        for index, chunk in enumerate(chunks):
            source_ref = f"片段 {index + 1}"
            match = re.search(r"\[(第 \d+ 页|段落 \d+|表格 \d+ 第 \d+ 行|图片 OCR)\]", chunk)
            if match:
                source_ref = match.group(1)
            items.append(
                {
                    "content": chunk,
                    "source_ref": source_ref,
                    "embedding": vectors[index] if vectors else [],
                }
            )
        self.store.replace_chunks(document_id, items)
        return len(items)

    def search(self, project_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
        chunks = self.store.chunks_for_project(project_id)
        if not chunks:
            return {
                "results": [],
                "retrieval_mode": "empty",
                "message": "当前项目没有已确认的资料。先上传材料并确认识别结果后再检索。",
            }
        query_embedding = self.embedder.embed([query])
        mode = "bge-m3" if query_embedding and any(c.get("embedding") for c in chunks) else "keyword_fallback"
        query_tokens = _tokens(query)
        scored = []
        for chunk in chunks:
            if mode == "bge-m3":
                score = _cosine(query_embedding[0], chunk.get("embedding", []))
            else:
                tokens = _tokens(chunk["content"])
                score = len(query_tokens & tokens) / math.sqrt(max(len(tokens), 1))
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = [
            {
                "source_name": item["source_name"],
                "source_ref": item["source_ref"],
                "text": item["content"],
                "score": round(score, 4),
            }
            for score, item in scored[: max(1, min(top_k, 10))]
            if score > 0
        ]
        return {
            "results": results,
            "retrieval_mode": mode,
            "message": (
                "已从当前项目已确认材料中检索；请将这些片段作为依据，不要超出材料推断事实。"
                if results
                else "没有找到明确依据；不要猜测，请向学生追问或标为待补充。"
            ),
        }
