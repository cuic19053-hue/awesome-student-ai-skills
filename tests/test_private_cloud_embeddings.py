"""Private cloud RAG must never send text without project-scoped consent."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from proposal.cloudflare_free import CloudflareFreeClient
from proposal.private_embeddings import CloudPrivateEmbedder, private_embedding_consent, private_embedding_project
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store


def configure(monkeypatch):
    for key, value in {
        "RAG_PRIVATE_CF_ENABLED": "true", "RAG_DB_SEARCH_ENABLED": "true",
        "RAG_CF_FREE_PLAN_CONFIRMED": "true", "RAG_CF_ACCOUNT_ID": "a" * 32,
        "RAG_CF_API_TOKEN": "not-a-real-token", "RAG_PRIVATE_CF_MODEL_REVISION": "cloudflare:bge-m3:test",
    }.items():
        monkeypatch.setenv(key, value)


def fake_cloud(monkeypatch):
    sent = []

    def request(self, path, data=None):
        if path == "":
            return {"success": True, "result": {"id": "a" * 32, "type": "standard"}}
        if path.startswith("/subscriptions"):
            return {"success": True, "result": [], "result_info": {"total_count": 0, "page": 1}}
        assert path == "/ai/v1/embeddings"
        sent.append(data["input"])
        return {"data": [{"index": i, "embedding": [1.0] + [0.0] * 1023}
                         for i, _ in enumerate(data["input"])]}

    monkeypatch.setattr(CloudflareFreeClient, "_request", request)
    return sent


def test_private_adapter_requires_consent_and_valid_free_configuration(monkeypatch):
    configure(monkeypatch)
    sent = fake_cloud(monkeypatch)
    client = CloudflareFreeClient("a" * 32, "token", free_plan_confirmed=True)
    assert client.embed_private(["secret"]) is None
    assert not sent
    monkeypatch.setenv("RAG_CF_FREE_PLAN_CONFIRMED", "false")
    token = private_embedding_consent.set(True)
    try:
        assert CloudPrivateEmbedder().embed(["secret"]) is None
        assert not sent
    finally:
        private_embedding_consent.reset(token)


def test_consent_is_project_scoped_and_index_and_search_use_same_revision(monkeypatch, tmp_path):
    configure(monkeypatch)
    sent = fake_cloud(monkeypatch)
    store = Store(tmp_path)
    project, other = store.create_project(), store.create_project()
    document = store.add_document(project["id"], "资料.txt", str(tmp_path / "a"), "source", "text/plain")
    store.update_document_extraction(document["id"], "已确认的私有资料", "ready",
                                     confirmed=True, confirmed_by_user=True)
    retriever = ProjectRetriever(store, CloudPrivateEmbedder())
    consent_token = private_embedding_consent.set(True)
    project_token = private_embedding_project.set(other["id"])
    try:
        assert retriever.index_document_result(document["id"], "已确认的私有资料")[1] == "keyword_fallback"
        assert sent == []
        private_embedding_project.set(project["id"])
        assert retriever.index_document_result(document["id"], "已确认的私有资料")[1] == "vector"
        assert store.chunks_for_project(project["id"])[0]["embedding_revision"] == "cloudflare:bge-m3:test"
        result = retriever.search(project["id"], "完全不同的问题")
        assert result["retrieval_mode"] == "hybrid"
        assert result["results"][0]["text"] == "已确认的私有资料"
        sent_before = len(sent)
        retriever.search(other["id"], "另一个项目")
        assert len(sent) == sent_before
    finally:
        private_embedding_project.reset(project_token)
        private_embedding_consent.reset(consent_token)


def test_http_consent_does_not_leak_between_requests_or_projects(monkeypatch, tmp_path):
    import app
    configure(monkeypatch)
    sent = fake_cloud(monkeypatch)
    store = Store(tmp_path)
    retriever = ProjectRetriever(store, CloudPrivateEmbedder())
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "CLOUD_MODE", True)

    async def bypass_auth(request, call_next):
        return await call_next(request)

    monkeypatch.setattr(app, "_require_supabase_session", bypass_auth)
    project, other = store.create_project(), store.create_project()
    doc = store.add_document(project["id"], "秘密.txt", str(tmp_path / "doc"), "source", "text/plain")
    store.update_document_extraction(doc["id"], "需要保护的项目资料", "ready")
    headers = {"X-Private-RAG-Consent": "cloudflare-bge-m3-v1", "X-Private-RAG-Project": project["id"]}
    with TestClient(app.app) as client:
        url = f"/api/documents/{doc['id']}/confirm"
        assert client.patch(url, json={"confirmed": True}).json()["index_mode"] == "keyword_fallback"
        assert sent == []
        wrong = {**headers, "X-Private-RAG-Project": other["id"]}
        assert client.patch(url, headers=wrong, json={"confirmed": True}).json()["index_mode"] == "keyword_fallback"
        assert sent == []
        assert client.patch(url, headers=headers, json={"confirmed": True}).json()["index_mode"] == "vector"
        assert len(sent) == 1
        search = f"/api/projects/{project['id']}/search/materials"
        assert client.post(search, json={"query": "其他问题"}).json()["retrieval_mode"] == "keyword_fallback"
        assert len(sent) == 1
        result = client.post(search, headers=headers, json={"query": "其他问题"}).json()
        assert result["retrieval_mode"] == "hybrid"
        assert len(sent) == 2
        client.post(f"/api/projects/{other['id']}/search/materials", headers=headers, json={"query": "其他问题"})
        assert len(sent) == 2

        class EvidenceAgent:
            def chat_stream(self, project_id, _text):
                result = retriever.search(project_id, "其他问题")
                yield {"type": "done", "retrieval_mode": result["retrieval_mode"]}

        monkeypatch.setattr(app, "agent", EvidenceAgent())
        chat = f"/api/projects/{project['id']}/chat"
        streamed = client.post(chat, headers=headers, json={"message": "国家奖学金申请条件是什么？", "stream": True})
        assert '"retrieval_mode": "hybrid"' in streamed.text
        assert len(sent) == 3
        streamed = client.post(chat, json={"message": "国家奖学金申请条件是什么？", "stream": True})
        assert '"retrieval_mode": "keyword_fallback"' in streamed.text
        assert len(sent) == 3


def test_worker_snapshot_is_restricted_to_the_exact_project_and_query(tmp_path):
    from material_worker import SnapshotRetriever
    store = Store(tmp_path)
    project, other = store.create_project(), store.create_project()
    snapshot = {"query": "测试问题", "result": {"retrieval_mode": "hybrid", "results": [{"text": "秘密"}]}}
    retriever = SnapshotRetriever(store, project["id"], snapshot)
    assert retriever.search(project["id"], "测试问题")["results"][0]["text"] == "秘密"
    assert not retriever.search(other["id"], "测试问题")["results"]
    assert not retriever.search(project["id"], "其他问题")["results"]
