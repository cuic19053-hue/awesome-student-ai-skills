#!/usr/bin/env python3
"""Validate a local index and optionally publish it using the service-role RPC.

Without --execute this only validates. This does not run migrations or enable
production retrieval. Never expose the service key to a browser or a client.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from proposal.knowledge import public_sources
from proposal.supabase_http import supabase_urlopen


def validate(path: Path, allow_keyword_only: bool = False) -> list[dict]:
    expected = {s["id"]: s for s in public_sources()}
    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [item["source"]["id"] for item in items]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError("来源清单缺失、重复或不在经过审核的仓库清单中。")
    revisions = set()
    for item in items:
        source, chunks = item["source"], item["chunks"]
        orig = expected[source["id"]]
        if source != {k: v for k, v in orig.items() if k != "chunks"}:
            raise ValueError("来源元数据已更改或校验和不匹配，请重新构建。")
        if len(chunks) != len(orig["chunks"]):
            raise ValueError("来源片段数不完整。")
        for chunk, original in zip(chunks, orig["chunks"]):
            if any(chunk.get(k) != v for k, v in original.items()):
                raise ValueError("来源片段不匹配，请重新构建。")
            vector = chunk.get("embedding")
            if vector is None:
                if not allow_keyword_only or chunk.get("embedding_model") or chunk.get("embedding_revision"):
                    raise ValueError("缺少向量，默认禁止发布不完整索引。")
                continue
            revision = chunk.get("embedding_revision", "")
            local_revision = (revision.startswith("ollama:bge-m3:sha256:")
                              and len(revision) == len("ollama:bge-m3:sha256:") + 64)
            cloud_revision = (revision.startswith("cloudflare:bge-m3:")
                              and len("cloudflare:bge-m3:") < len(revision) <= 200)
            if (chunk.get("embedding_model") != "bge-m3" or not (local_revision or cloud_revision)
                    or len(vector) != 1024 or not any(vector)
                    or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector)):
                raise ValueError("向量模型版本或维度不正确。")
            revisions.add(revision)
    if len(revisions) > 1:
        raise ValueError("不可混用不同版本的向量。")
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--allow-keyword-only", action="store_true")
    parser.add_argument("--execute", action="store_true", help="实际写入指定 Supabase 项目")
    parser.add_argument("--republish-revoked", action="store_true",
                        help="显式允许重新发布此前撤回的来源；须先人工审查")
    args = parser.parse_args()
    items = validate(args.input, args.allow_keyword_only)
    print(f"通过校验：{len(items)} 来源、{sum(len(i['chunks']) for i in items)} 片段。")
    if not args.execute:
        print("仅校验，未连接数据库或修改生产数据。")
        return 0
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    parsed = urllib.parse.urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or not key):
        raise SystemExit("须在服务端环境配置 HTTPS SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY。")
    from audit_public_sources import audit
    audit_report = audit(online=True)
    if any(item["status"] != "unchanged" for item in audit_report["results"]):
        raise SystemExit("有官方来源变化或无法核验；未写入数据库，请先审查。")
    if not args.republish_revoked:
        # Check every source before any write, so resuming an import cannot
        # silently republish a deliberately withdrawn source.
        for item in items:
            query = urllib.parse.urlencode({"id": "eq." + item["source"]["id"], "select": "id,published"})
            request = urllib.request.Request(base + "/rest/v1/rag_public_sources?" + query, headers={
                "apikey": key, "Authorization": "Bearer " + key,
            })
            try:
                with supabase_urlopen(request, timeout=20) as response:
                    rows = json.load(response)
            except (urllib.error.URLError, OSError, ValueError):
                raise SystemExit("来源发布状态检查失败；未写入数据库。") from None
            if not isinstance(rows, list) or any(row.get("published") is not True for row in rows):
                raise SystemExit("存在未发布或已撤回来源；需人工复核并显式允许重新发布。")
    for item in items:
        body = json.dumps({"p_source": item["source"], "p_chunks": item["chunks"]},
                          ensure_ascii=False, separators=(",", ":")).encode()
        request = urllib.request.Request(base + "/rest/v1/rpc/rag_publish_public_source", data=body,
            headers={"apikey": key, "Authorization": "Bearer " + key,
                     "Content-Type": "application/json"}, method="POST")
        try:
            with supabase_urlopen(request, timeout=60) as response:
                count = json.load(response)
        except (urllib.error.URLError, OSError):
            raise SystemExit(f"来源 {item['source']['id']} 上传失败；请检查服务状态后重新执行。") from None
        if count != len(item["chunks"]):
            raise SystemExit(f"来源 {item['source']['id']} 返回数量不匹配。")
        print(f"已原子发布：{item['source']['id']} ({count})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
