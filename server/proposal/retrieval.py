from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
import urllib.parse
from typing import Any

from .documents import split_into_chunks
from .storage import Store


def outline_material_query(project: dict[str, Any]) -> str:
    from .skills import normalize_skill_id, registry
    skill_id = normalize_skill_id(project.get("state", {}).get("skill_id", "innovation-research"))
    if skill_id == "innovation-research":
        return "研究问题 研究内容 方法 创新点"
    skill = registry.get(skill_id) or {}
    return f"{skill.get('display_name') or skill_id} 申请 事实 要求"


def section_material_query(project: dict[str, Any], section_id: str) -> str:
    section = next((item for item in project.get("outline", []) if item.get("id") == section_id), {})
    return f"{section.get('title', '')} {project.get('discipline', '')}"


def diagram_material_query(title: str) -> str:
    return title + " 方法 流程"


def plan_diagram_title(project: dict[str, Any]) -> str:
    from .skills import normalize_skill_id
    skill_id = normalize_skill_id(project.get("state", {}).get("skill_id", "innovation-research"))
    return "研究流程与技术路线" if skill_id == "innovation-research" else "材料流程与要点"


class Embedder:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "bge-m3"):
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("项目私有材料的本地嵌入服务必须使用本机回环地址。")
        self.base_url = base_url.rstrip("/")
        self.model = model

    def revision(self) -> str:
        """Bind stored vectors to the exact installed Ollama model digest."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
            accepted = {self.model}
            if ":" not in self.model:
                accepted.add(self.model + ":latest")
            for item in body.get("models", []):
                digest = item.get("digest", "")
                if item.get("name") in accepted and re.fullmatch(r"[0-9a-f]{64}", digest):
                    return f"ollama:{self.model}:sha256:{digest}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            pass
        return ""

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
            if (isinstance(vectors, list) and len(vectors) == len(texts)
                    and all(isinstance(v, list) and 0 < len(v) <= 4096 and any(v)
                            and all(type(n) in (int, float) and math.isfinite(n) for n in v)
                            for v in vectors)
                    and len({len(v) for v in vectors}) == 1):
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
    def __init__(self, store: Store, embedder: Embedder | None = None, reranker=None):
        self.store = store
        self.embedder = embedder or Embedder()
        # Rerankers are injected by trusted server code, never selected by a user.
        # No remote reranker is configured by default for private project materials.
        self.reranker = reranker

    def _embed_verified(self, texts: list[str], project_id: str = "") -> tuple[list[list[float]] | None, str]:
        authorized_for = getattr(self.embedder, "authorized_for", None)
        if callable(authorized_for) and not authorized_for(project_id):
            return None, ""
        revision_fn = getattr(self.embedder, "revision", None)
        if not callable(revision_fn):
            return None, ""
        try:
            before = revision_fn()
            if not before:
                return None, ""
            vectors = self.embedder.embed(texts)
            # A model update during embedding invalidates the entire batch.
            if not vectors or revision_fn() != before:
                return None, ""
        except Exception:
            return None, ""
        return vectors, before

    def index_document(self, document_id: str, extracted_text: str) -> int:
        return self.index_document_result(document_id, extracted_text)[0]

    def index_document_result(self, document_id: str, extracted_text: str) -> tuple[int, str]:
        document = self.store.get_document(document_id)
        if (not document or not document.get("confirmed") or document.get("kind") == "template"
                or document.get("confirmation_origin") != "user"):
            return 0, "not_indexed"
        if extracted_text != document.get("extracted_text", ""):
            from .materials import MaterialConflict
            raise MaterialConflict("材料在索引前已发生变化，请重新核对。")
        chunks = split_into_chunks(extracted_text)
        vectors, embedding_revision = self._embed_verified([chunk for chunk in chunks], document["project_id"])
        items = []
        # Preserve page/paragraph references when they are present in extracted text.
        for index, chunk in enumerate(chunks):
            source_ref = f"片段 {index + 1}"
            match = re.search(r"\[(第\s*\d+\s*页|段落\s*\d+|表格\s*\d+\s*第\s*\d+\s*行|行\s*\d+|图片 OCR)\]", chunk)
            if match:
                source_ref = match.group(1)
            items.append(
                {
                    "content": chunk,
                    "source_ref": source_ref,
                    "embedding": vectors[index] if vectors else [],
                    "embedding_model": getattr(self.embedder, "model", ""),
                    "embedding_revision": embedding_revision,
                }
            )
        self.store.replace_chunks(document_id, items, expected_text=extracted_text)
        return len(items), "vector" if vectors else "keyword_fallback"

    def search(self, project_id: str, query: str, top_k: int = 5) -> dict[str, Any]:
        query_embedding, query_revision = self._embed_verified([query[:1000]], project_id)
        query_vector = query_embedding[0] if query_embedding else None
        terms = sorted(_tokens(query), key=lambda term: (-len(term), term))[:80]
        db_search = (
            os.environ.get("RAG_DB_SEARCH_ENABLED", "").lower() == "true"
            and callable(getattr(self.store, "search_project_chunks", None))
        )
        failure = ""
        if db_search:
            try:
                chunks = self.store.search_project_chunks(
                    project_id, terms, query_vector, getattr(self.embedder, "model", "bge-m3"), query_revision
                )
            except (RuntimeError, OSError, ValueError):
                # Migration or database-side search may not yet be available.
                failure = "数据库检索暂不可用，已使用兼容模式。"
                db_search = False
        if not db_search:
            chunks = self.store.chunks_for_project(project_id)
        if not chunks:
            return {
                "results": [],
                "retrieval_mode": "empty",
                "reranked": False,
                "fallback_reason": failure,
                "message": "未找到匹配的已确认项目资料，请补充材料或调整问题。",
            }
        model = getattr(self.embedder, "model", "")
        have_vectors = bool(query_vector) and any(
            (c.get("vector_score", 0) if db_search
             else c.get("embedding") and model and c.get("embedding_model") == model
             and query_revision and c.get("embedding_revision") == query_revision)
            for c in chunks
        )
        mode = "hybrid" if have_vectors else "keyword_fallback"
        if not have_vectors and not failure:
            failure = getattr(self.embedder, "fallback_notice", "")
        query_tokens = _tokens(query)
        lexical, semantic = [], []
        for index, chunk in enumerate(chunks):
            tokens = _tokens(chunk["content"])
            lexical_score = (
                float(chunk.get("lexical_score", 0)) if db_search
                else len(query_tokens & tokens) / math.sqrt(max(len(tokens), 1))
            )
            vector_score = (
                float(chunk.get("vector_score", 0)) if db_search
                else _cosine(query_vector or [], chunk.get("embedding", []))
                if (model and chunk.get("embedding_model") == model and query_revision
                    and chunk.get("embedding_revision") == query_revision) else 0.0
            )
            if lexical_score > 0:
                lexical.append((lexical_score, index))
            if have_vectors and vector_score > 0:
                semantic.append((vector_score, index))
        lexical.sort(key=lambda row: (-row[0], row[1]))
        semantic.sort(key=lambda row: (-row[0], row[1]))
        fused: dict[int, float] = {}
        for ranking in (lexical[:30], semantic[:30]):
            for rank, (_, index) in enumerate(ranking, 1):
                fused[index] = fused.get(index, 0) + 1 / (60 + rank)
        scored = sorted(((score, chunks[index]) for index, score in fused.items()),
                        key=lambda item: -item[0])[:30]
        reranked = False
        if self.reranker and scored:
            try:
                # A reranker returns indices into the candidate list. Never accept
                # arbitrary text from a model as a new source.
                indices = self.reranker.rerank(query, [chunk["content"] for _, chunk in scored])
                if (isinstance(indices, list) and len(indices) == len(scored)
                        and all(type(index) is int for index in indices)
                        and set(indices) == set(range(len(scored)))):
                    scored = [scored[index] for index in indices]
                    reranked = True
                else:
                    failure = "重排结果无效，已使用融合排序。"
            except Exception:
                failure = "重排服务不可用，已使用融合排序。"
        results = [
            {
                "source_name": item["source_name"],
                "document_id": item.get("document_id", ""),
                "chunk_id": item.get("id", ""),
                "source_ref": item["source_ref"],
                "text": item["content"],
                "score": round(score, 6),
            }
            for score, item in scored[: max(1, min(top_k, 10))]
            if score > 0
        ]
        return {
            "results": results,
            "retrieval_mode": mode,
            "reranked": reranked,
            "fallback_reason": failure,
            "message": (
                "已从当前项目材料中检索；请将这些片段作为依据，不要超出材料推断事实。"
                if results
                else "没有找到明确依据；不要猜测，请向学生追问或标为待补充。"
            ),
        }
