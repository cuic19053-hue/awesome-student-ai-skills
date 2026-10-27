from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "scripts"))
from proposal.knowledge import public_sources
from publish_public_knowledge import validate


def test_import_checks_all_sources_and_detects_tampered_text(tmp_path):
    import copy
    import json
    records = [{"source": {k: v for k, v in source.items() if k != "chunks"},
                "chunks": copy.deepcopy(source["chunks"])} for source in public_sources()]
    path = tmp_path / "public.jsonl"
    def write():
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in records), encoding="utf-8")
    write()
    assert len(validate(path, allow_keyword_only=True)) == len(public_sources())
    with pytest.raises(ValueError, match="缺少向量"):
        validate(path)
    records[0]["chunks"][0]["content"] += "伪造"
    write()
    with pytest.raises(ValueError, match="片段不匹配"):
        validate(path, allow_keyword_only=True)


def test_example_source_audit_blocks_local_and_private_networks(monkeypatch):
    import socket
    from audit_public_sources import _validate_public_https
    with pytest.raises(ValueError):
        _validate_public_https("http://example.org/data")
    with pytest.raises(ValueError):
        _validate_public_https("https://localhost/data")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.2", 443))])
    with pytest.raises(ValueError):
        _validate_public_https("https://example.org/data")


def test_candidate_report_never_exposes_private_fields(tmp_path, monkeypatch):
    import json
    from list_example_candidates import candidates
    review = tmp_path / "rag" / "review"
    review.mkdir(parents=True)
    (review / "sample-rights-review.json").write_text(json.dumps({
        "record_id": "record-1", "status": "pending", "approved": False,
        "raw_text": "private body", "api_key": "secret", "author_name": "private",
    }), encoding="utf-8")
    monkeypatch.setenv("PROPOSAL_AGENT_DATA_DIR", str(tmp_path))
    result = candidates()
    assert len(result) == 1 and result[0]["record_id"] == "record-1"
    assert "private" not in repr(result) and "secret" not in repr(result)


def test_offline_public_embedding_fails_if_model_changes(monkeypatch):
    import build_public_knowledge as builder
    calls = iter(["expected-revision", "different-revision"])
    monkeypatch.setattr(builder, "revision", lambda: next(calls))
    monkeypatch.setattr(builder, "post", lambda *_args: {"embeddings": [[0.1] * 1024]})
    with pytest.raises(RuntimeError, match="版本发生变化"):
        builder.embed_chunks([{"id": "x", "content": "公开内容", "source_ref": "一"}],
                             "expected-revision")


def test_admin_transport_does_not_follow_redirects_or_forward_secret(monkeypatch):
    import httpx
    import urllib.error
    import urllib.request
    from proposal import supabase_http
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://other.example/collect"})
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    monkeypatch.setattr(supabase_http, "_client", client)
    request = urllib.request.Request("https://db.example/rest/v1/test",
                                     headers={"Authorization": "Bearer private-test-key"})
    with pytest.raises(urllib.error.HTTPError):
        supabase_http.supabase_urlopen(request)
    assert seen == ["https://db.example/rest/v1/test"]
    client.close()
