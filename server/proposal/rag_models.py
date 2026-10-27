"""Opt-in adapters for externally hosted, independently verified free services.

These adapters are not wired into the private project retriever.  Only approved
public knowledge may be sent, and callers must separately enforce provider quotas.
A configuration flag is not proof that a provider is actually free.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Provider credentials must never be forwarded to a redirected origin.
        return None


class PublicModelClient:
    def __init__(self, base_url: str, api_key: str, model: str, *, free_tier_verified: bool = False):
        parsed = urllib.parse.urlsplit(base_url)
        if (not free_tier_verified or parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("须使用已核实的免费 HTTPS 模型服务。")
        if not api_key or not model:
            raise ValueError("模型服务需要显式配置密钥及模型。")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def _post(self, endpoint: str, payload: dict[str, Any], *, scope: str) -> dict[str, Any] | None:
        if scope != "public":
            # Refuse before creating or sending a request. Per-user consent is not
            # implemented yet; configuration is not a substitute for consent.
            return None
        request = urllib.request.Request(
            self.base_url + endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=8) as response:
                data = json.loads(response.read(2_000_000).decode("utf-8"))
            return data if isinstance(data, dict) else None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None

    def embed_public(self, texts: list[str], *, scope: str) -> list[list[float]] | None:
        if not texts:
            return []
        response = self._post("/embeddings", {"model": self.model, "input": texts}, scope=scope)
        if not response:
            return None
        try:
            items = sorted(response["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in items]
            if (len(vectors) != len(texts) or [item["index"] for item in items] != list(range(len(texts)))
                    or not vectors[0] or any(len(v) != len(vectors[0]) for v in vectors)
                    or any(not isinstance(n, (float, int)) or not math.isfinite(n) for v in vectors for n in v)):
                return None
            return vectors
        except (KeyError, TypeError, IndexError):
            return None

    def rerank_public(self, query: str, documents: list[str], *, scope: str) -> list[int] | None:
        if not documents:
            return []
        response = self._post("/rerank", {"model": self.model, "query": query,
                                          "documents": documents, "top_n": len(documents)}, scope=scope)
        if not response:
            return None
        try:
            indices = [item["index"] for item in response["results"]]
            if (len(indices) == len(documents) and all(type(i) is int for i in indices)
                    and set(indices) == set(range(len(documents)))):
                return indices
        except (KeyError, TypeError):
            pass
        return None
