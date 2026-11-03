"""Opt-in, request-scoped private embeddings; never accept a user-supplied URL."""
from __future__ import annotations

import os
import re
from contextvars import ContextVar

private_embedding_consent: ContextVar[bool] = ContextVar("private_embedding_consent", default=False)
private_embedding_project: ContextVar[str] = ContextVar("private_embedding_project", default="")


def private_embedding_configured() -> bool:
    """Configuration presence is not proof that the service or free plan works."""
    return bool(
        os.environ.get("RAG_PRIVATE_CF_ENABLED", "").lower() == "true"
        and os.environ.get("RAG_DB_SEARCH_ENABLED", "").lower() == "true"
        and os.environ.get("RAG_CF_FREE_PLAN_CONFIRMED", "").lower() == "true"
        and re.fullmatch(r"[0-9a-f]{32}", os.environ.get("RAG_CF_ACCOUNT_ID", ""))
        and os.environ.get("RAG_CF_API_TOKEN", "")
        and re.fullmatch(r"cloudflare:bge-m3:[A-Za-z0-9._-]{1,160}",
                         os.environ.get("RAG_PRIVATE_CF_MODEL_REVISION", ""))
    )


class CloudPrivateEmbedder:
    """Cloudflare BGE-M3, distinct from locally indexed model revisions."""
    model = "bge-m3"
    fallback_notice = "私有向量服务未授权、未就绪或材料尚未建立同版本向量；已使用关键词检索。"

    def authorized_for(self, project_id: str) -> bool:
        return bool(project_id and project_id == private_embedding_project.get())

    def revision(self) -> str:
        if (private_embedding_consent.get() is not True
                or not re.fullmatch(r"[a-f0-9]{32}", private_embedding_project.get())
                or not private_embedding_configured()):
            return ""
        return os.environ["RAG_PRIVATE_CF_MODEL_REVISION"]

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self.revision():
            return None
        if not texts:
            return []
        # A bounded synchronous operation fits the serverless request budget.
        if len(texts) > 72 or any(not isinstance(t, str) or not t or len(t) > 2000 for t in texts):
            return None
        from .cloudflare_free import CloudflareFreeClient
        try:
            client = CloudflareFreeClient(
                os.environ["RAG_CF_ACCOUNT_ID"], os.environ["RAG_CF_API_TOKEN"],
                free_plan_confirmed=True,
            )
            vectors = []
            for start in range(0, len(texts), 24):
                batch = client.embed_private(texts[start:start + 24], consent=True)
                if batch is None:
                    return None
                vectors.extend(batch)
            return vectors
        except (ValueError, KeyError):
            return None
