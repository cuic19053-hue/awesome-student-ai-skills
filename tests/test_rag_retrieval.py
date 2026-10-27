"""Safe hybrid retrieval, routing metadata, and failure behaviour."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from proposal.retrieval import ProjectRetriever
from utils.skill_cards import build_skill_cards, infer_task_type


class MemoryStore:
    def __init__(self, rows):
        self.rows = rows

    def chunks_for_project(self, project_id):
        return [r for r in self.rows if r["project_id"] == project_id and r.get("confirmed", True)]


def chunk(id, text, vector, model="bge-m3", project="one", confirmed=True, revision="model-rev-1"):
    return {"id": id, "project_id": project, "confirmed": confirmed, "content": text,
            "source_name": "材料", "source_ref": "段落 1", "document_id": id,
            "embedding": vector, "embedding_model": model, "embedding_revision": revision}


class Embed:
    model = "bge-m3"

    def revision(self):
        return "model-rev-1"

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def test_rrf_combines_keyword_and_embedding_and_respects_project_scope():
    store = MemoryStore([
        chunk("lexical", "项目预算用途", [0.0, 1.0]),
        chunk("semantic", "经费分配", [1.0, 0.0]),
        chunk("other", "项目预算用途", [1.0, 0.0], project="other"),
        chunk("unconfirmed", "项目预算用途", [1.0, 0.0], confirmed=False),
    ])
    result = ProjectRetriever(store, Embed()).search("one", "项目预算")
    assert result["retrieval_mode"] == "hybrid"
    assert {r["chunk_id"] for r in result["results"]} == {"lexical", "semantic"}


def test_unversioned_or_wrong_model_vectors_are_not_compared():
    store = MemoryStore([chunk("x", "其他内容", [1.0, 0.0], model="old-model"),
                         chunk("y", "另外内容", [1.0, 0.0], revision="old-revision"),
                         chunk("z", "其他说明", [1.0, 0.0], revision="")])
    result = ProjectRetriever(store, Embed()).search("one", "项目预算")
    assert result["retrieval_mode"] == "keyword_fallback"
    assert result["results"] == []


def test_model_change_during_embedding_is_fail_closed():
    class Changing(Embed):
        calls = 0
        def revision(self):
            self.calls += 1
            return "version-one" if self.calls == 1 else "version-two"
    store = MemoryStore([chunk("x", "其他内容", [1.0, 0.0], revision="version-one")])
    result = ProjectRetriever(store, Changing()).search("one", "完全不同查询")
    assert result["retrieval_mode"] == "keyword_fallback"
    assert result["results"] == []


def test_reranker_reorders_only_existing_candidates_and_degrades_on_failure():
    store = MemoryStore([chunk("a", "项目经费", []), chunk("b", "项目预算", [])])

    class Rerank:
        def rerank(self, query, documents):
            return list(reversed(range(len(documents))))

    first = ProjectRetriever(store, Embed()).search("one", "项目")
    second = ProjectRetriever(store, Embed(), Rerank()).search("one", "项目")
    assert second["reranked"] is True
    assert [r["chunk_id"] for r in second["results"]] == list(reversed([r["chunk_id"] for r in first["results"]]))

    class Broken:
        def rerank(self, query, documents):
            raise TimeoutError("failed")

    fallback = ProjectRetriever(store, Embed(), Broken()).search("one", "项目")
    assert fallback["reranked"] is False
    assert fallback["fallback_reason"]
    assert fallback["results"] == first["results"]


def test_routing_cards_cover_catalog_without_inventing_eligibility():
    skills = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))["skills"]
    cards = build_skill_cards(skills)
    assert len(cards) == 35
    assert {card["id"] for card in cards} == {skill["name"] for skill in skills}
    assert all(card["aliases"] and not card["eligibility"] for card in cards)
    assert infer_task_type("国家奖学金和励志奖学金有什么区别") == "compare"
    assert infer_task_type("润色这份申请书") == "revise"


def test_database_failure_falls_back_without_losing_scope(monkeypatch):
    class Store(MemoryStore):
        def search_project_chunks(self, *args):
            raise RuntimeError("unavailable")

    monkeypatch.setenv("RAG_DB_SEARCH_ENABLED", "true")
    store = Store([chunk("a", "项目经费", []), chunk("b", "项目经费", [], project="other")])
    result = ProjectRetriever(store, Embed()).search("one", "项目")
    assert [r["chunk_id"] for r in result["results"]] == ["a"]
    assert result["fallback_reason"]


def test_remote_adapter_refuses_private_data_and_invalid_free_configuration(monkeypatch):
    import urllib.request
    import pytest
    from proposal.rag_models import PublicModelClient

    with pytest.raises(ValueError):
        PublicModelClient("https://provider.example/v1", "key", "model")
    with pytest.raises(ValueError):
        PublicModelClient("http://provider.example/v1", "key", "model", free_tier_verified=True)
    client = PublicModelClient("https://provider.example/v1", "key", "model", free_tier_verified=True)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not send private data"))
    assert client.embed_public(["private"], scope="private") is None
    assert client.rerank_public("private", ["private"], scope="private") is None


def test_indexing_requires_exact_explicitly_confirmed_text(tmp_path):
    from proposal.storage import Store
    store = Store(tmp_path)
    project = store.create_project()
    doc = store.add_document(project["id"], "data.txt", str(tmp_path / "data.txt"), "source", "text/plain")
    store.update_document_extraction(doc["id"], "用户核对的文字", "ready", confirmed=False)
    retriever = ProjectRetriever(store, Embed())
    assert retriever.index_document(doc["id"], "用户核对的文字") == 0
    store.update_document_extraction(doc["id"], "用户核对的文字", "ready", confirmed=True, confirmed_by_user=True)
    import pytest
    from proposal.materials import MaterialConflict
    with pytest.raises(MaterialConflict):
        retriever.index_document(doc["id"], "被替换的文字")
    assert retriever.index_document(doc["id"], "用户核对的文字") == 1
    assert store.chunks_for_project(project["id"])[0]["content"] == "用户核对的文字"
