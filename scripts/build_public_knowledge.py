#!/usr/bin/env python3
"""Build a resumable, locally generated public-knowledge artifact (never uploads)."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from proposal.knowledge import public_sources

OLLAMA = "http://127.0.0.1:11434"
MODEL = "bge-m3"


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(OLLAMA + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def revision() -> str:
    with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5) as response:
        data = json.load(response)
    model = next((m for m in data.get("models", []) if m.get("name") in (MODEL, MODEL + ":latest")), None)
    digest = (model or {}).get("digest", "")
    if len(digest) != 64:
        raise RuntimeError("本地 Ollama 未安装可确定版本的 bge-m3。")
    return "ollama:bge-m3:sha256:" + digest


def embed_chunks(chunks: list[dict], model_revision: str, cloud_client=None) -> list[dict]:
    output = []
    for offset in range(0, len(chunks), 16):
        batch = chunks[offset:offset + 16]
        if cloud_client is not None:
            vectors = cloud_client.embed([c["content"] for c in batch], scope="public")
        else:
            if revision() != model_revision:
                raise RuntimeError("本地嵌入模型版本发生变化；未保存当前来源。")
            data = post("/api/embed", {"model": MODEL, "input": [c["content"] for c in batch]})
            if revision() != model_revision:
                raise RuntimeError("嵌入期间本地模型版本发生变化；未保存当前来源。")
            vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise RuntimeError("本地模型返回的向量数量不正确。")
        for chunk, vector in zip(batch, vectors):
            if (not isinstance(vector, list) or len(vector) != 1024
                    or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector)
                    or not any(vector)):
                raise RuntimeError("本地模型返回的向量无效；未保存当前来源。")
            output.append({**chunk, "embedding_model": MODEL,
                           "embedding_revision": model_revision, "embedding": vector})
    return output


def write_atomic(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            for item in records:
                f.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="输出 JSONL；建议放在 .agent-data 下")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--embed-local", action="store_true", help="使用本机 Ollama bge-m3，仅离线构建公共资料")
    group.add_argument("--embed-cloudflare-free", action="store_true", help="使用已核验免费账户构建公共资料；不包含项目私有数据")
    parser.add_argument("--resume", action="store_true", help="仅跳过来源及模型版本均未变化的完整来源")
    args = parser.parse_args()
    cloud_client = None
    if args.embed_cloudflare_free:
        from proposal.cloudflare_free import CloudflareFreeClient
        model_revision = os.environ.get("RAG_CF_MODEL_REVISION", "").strip()
        if not model_revision.startswith("cloudflare:bge-m3:") or len(model_revision) <= len("cloudflare:bge-m3:") or len(model_revision) > 200:
            raise SystemExit("须配置已核验的 RAG_CF_MODEL_REVISION；模型版本变化后必须重新索引。")
        cloud_client = CloudflareFreeClient(
            os.environ.get("RAG_CF_ACCOUNT_ID", ""), os.environ.get("RAG_CF_API_TOKEN", ""),
            free_plan_confirmed=os.environ.get("RAG_CF_FREE_PLAN_CONFIRMED", "").lower() == "true",
        )
    else:
        model_revision = revision() if args.embed_local else ""
    previous = {}
    if args.resume and args.out.is_file():
        with args.out.open(encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                previous[item["source"]["id"]] = item
    records = []
    sources = public_sources()
    for position, item in enumerate(sources, 1):
        source = {k: v for k, v in item.items() if k != "chunks"}
        old = previous.get(source["id"])
        same = (old and old.get("source", {}).get("source_sha256") == source["source_sha256"]
                and len(old.get("chunks", [])) == len(item["chunks"])
                and [c.get("id") for c in old["chunks"]] == [c["id"] for c in item["chunks"]]
                and all(c.get("embedding_revision", "") == model_revision for c in old["chunks"]))
        if same:
            # Metadata/scope changes do not require recomputing identical text
            # vectors; publish the current metadata with the reusable vectors.
            result = {"source": source, "chunks": old["chunks"]}
        else:
            chunks = embed_chunks(item["chunks"], model_revision, cloud_client) if model_revision else item["chunks"]
            result = {"source": source, "chunks": chunks}
        records.append(result)
        # Checkpoint only after a changed complete source; unchanged sources
        # would otherwise rewrite a large vector artifact on every loop.
        if not same:
            completed = {r["source"]["id"] for r in records}
            remaining = [v for k, v in previous.items() if k not in completed]
            write_atomic(args.out, records + remaining)
        print(f"[{position}/{len(sources)}] {source['id']}: {len(result['chunks'])} 片段", flush=True)
    if args.embed_local and revision() != model_revision:
        raise RuntimeError("本地嵌入模型版本发生变化；请重新构建。")
    write_atomic(args.out, records)
    print(f"完成：{len(records)} 个来源；模型版本：{model_revision or '未计算向量'}。未上传或部署。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
