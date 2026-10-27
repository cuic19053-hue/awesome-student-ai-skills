from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from proposal.cloudflare_free import CloudflareFreeClient


def test_free_plan_requires_explicit_operator_confirmation():
    import pytest
    with pytest.raises(ValueError):
        CloudflareFreeClient("a" * 32, "test")


def test_provider_refuses_private_queries_and_paid_or_unknown_accounts():
    client = CloudflareFreeClient("a" * 32, "test", free_plan_confirmed=True)
    calls = []
    client._request = lambda path, data=None: calls.append((path, data)) or None
    assert client.embed(["秘密"], scope="query") is None
    assert client.embed(["秘密"], scope="private", query_consent=True) is None
    assert client.rerank("秘密", ["public"]) is None
    assert calls == []
    assert client.embed(["public"], scope="public") is None
    assert [c[0] for c in calls] == [""]
    for account in (None, {"success": True, "result": {"id": "a" * 32, "type": "enterprise"}},
                    {"success": True, "result": {"id": "b" * 32, "type": "standard"}}):
        client._request = lambda path, data=None, account=account: account
        assert not client._free_only_verified()
    for response in ({"success": True, "result": [{"price": 0}], "result_info": {"total_count": 1, "page": 1}},
                     {"success": True, "result": [], "result_info": {"total_count": 1, "page": 1}},
                     {"success": True, "result": []}):
        client._request = lambda path, data=None, response=response: (
            {"success": True, "result": {"id": "a" * 32, "type": "standard"}} if not path else response
        )
        assert not client._free_only_verified()


def test_free_provider_validates_embeddings_and_rerank_permutation():
    client = CloudflareFreeClient("a" * 32, "test", free_plan_confirmed=True)
    def fake(path, data=None):
        if not path:
            return {"success": True, "result": {"id": "a" * 32, "type": "standard"}}
        if path.startswith("/subscriptions"):
            return {"success": True, "result": [], "result_info": {"total_count": 0, "page": 1}}
        if path == "/ai/v1/embeddings":
            return {"data": [{"index": 0, "embedding": [0.1] * 1024}]}
        return {"result": {"response": [{"id": 1, "score": 0.9}, {"id": 0, "score": 0.1}]}}
    client._request = fake
    assert len(client.embed(["public"], scope="public")[0]) == 1024
    assert client.rerank("query", ["one", "two"], query_consent=True) == [1, 0]
    assert client.rerank("query", ["one", "two"]) is None
