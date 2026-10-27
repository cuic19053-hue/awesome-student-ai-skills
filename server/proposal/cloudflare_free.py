"""Fail-closed Cloudflare Workers AI adapter for explicitly free-only accounts.

Only public corpus may be indexed. Project query text may be sent only when the
caller supplies explicit, per-request consent. No paid plan or AI Gateway route
is ever selected by this client. A billing-readable token is required to check
that the account has no subscriptions before each inference call.
"""
from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request
from typing import Any

from .rag_models import _NoRedirect

EMBEDDING_MODEL = "@cf/baai/bge-m3"
RERANK_MODEL = "@cf/baai/bge-reranker-base"


class CloudflareFreeClient:
    def __init__(self, account_id: str, token: str, *, free_plan_confirmed: bool = False):
        if not free_plan_confirmed or not re.fullmatch(r"[0-9a-f]{32}", account_id) or not token:
            raise ValueError("免费模型服务的账户或令牌配置无效。")
        self.account_id = account_id
        self.base = f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
        self.token = token

    def _request(self, path: str, data: dict | None = None) -> dict[str, Any] | None:
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(data, ensure_ascii=False).encode() if data is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=5) as response:
                result = json.loads(response.read(4_000_000).decode("utf-8"))
            return result if isinstance(result, dict) else None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None

    def _free_only_verified(self) -> bool:
        # Enterprise billing may be contracted outside ordinary subscriptions;
        # require a positively identified standard account and reject unknowns.
        account = self._request("")
        if (not account or account.get("success") is not True
                or not isinstance(account.get("result"), dict)
                or account["result"].get("id") != self.account_id
                or account["result"].get("type") != "standard"):
            return False
        # Reject all subscriptions, even unrelated ones, rather than guessing
        # which subscription can permit overage. Pagination must prove complete.
        response = self._request("/subscriptions?per_page=100")
        if not response or response.get("success") is not True:
            return False
        result, info = response.get("result"), response.get("result_info")
        return (isinstance(result, list) and not result and isinstance(info, dict)
                and info.get("total_count") == 0 and info.get("page") == 1)

    def embed(self, texts: list[str], *, scope: str, query_consent: bool = False) -> list[list[float]] | None:
        if scope not in {"public", "query"} or (scope == "query" and query_consent is not True):
            return None
        if not texts:
            return []
        if not self._free_only_verified():
            return None
        response = self._request("/ai/v1/embeddings", {"model": EMBEDDING_MODEL, "input": texts})
        try:
            data = sorted(response["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in data]
            if (len(vectors) != len(texts) or [item["index"] for item in data] != list(range(len(texts)))
                    or any(not isinstance(v, list) or len(v) != 1024 or not any(v) for v in vectors)
                    or any(type(n) not in (int, float) or not math.isfinite(n) for v in vectors for n in v)):
                return None
            return vectors
        except (KeyError, TypeError, ValueError):
            return None

    def rerank(self, query: str, documents: list[str], *, query_consent: bool = False) -> list[int] | None:
        if query_consent is not True:
            return None
        if not documents:
            return []
        if len(documents) > 30 or not self._free_only_verified():
            return None
        response = self._request("/ai/run/" + RERANK_MODEL, {
            "query": query[:300], "contexts": [{"text": text[:400]} for text in documents],
            "top_k": len(documents),
        })
        try:
            result = response["result"]["response"]
            if any(not math.isfinite(float(item["score"])) for item in result):
                return None
            ranked = sorted(result, key=lambda item: -float(item["score"]))
            ids = [item["id"] for item in ranked]
            if len(ids) == len(documents) and all(type(i) is int for i in ids) and set(ids) == set(range(len(ids))):
                return ids
        except (KeyError, TypeError, ValueError):
            pass
        return None
