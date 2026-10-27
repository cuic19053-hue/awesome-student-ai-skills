#!/usr/bin/env python3
"""Revoke or delete one public knowledge source; defaults to a read-only dry run."""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from proposal.supabase_http import supabase_urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("revoke", "delete"))
    parser.add_argument("source_id")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="", help="必须与 source_id 完全相同")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9:_-]{0,199}", args.source_id):
        raise SystemExit("来源标识格式无效。")
    if not args.execute:
        print(f"预览：{args.action} {args.source_id}；未连接数据库。")
        return 0
    if args.confirm != args.source_id:
        raise SystemExit("实际执行时须使用 --confirm 原样确认来源标识。")
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    parsed = urllib.parse.urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or not key):
        raise SystemExit("须配置服务端 HTTPS SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY。")
    params = urllib.parse.urlencode({"id": "eq." + args.source_id})
    method = "PATCH" if args.action == "revoke" else "DELETE"
    body = json.dumps({"published": False}).encode() if method == "PATCH" else None
    req = urllib.request.Request(base + "/rest/v1/rag_public_sources?" + params, data=body,
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Prefer": "return=representation"}, method=method)
    try:
        with supabase_urlopen(req, timeout=20) as response:
            rows = json.load(response)
    except (OSError, ValueError):
        raise SystemExit("来源操作失败；未输出密钥或原始响应。") from None
    if not isinstance(rows, list) or len(rows) != 1 or rows[0].get("id") != args.source_id:
        raise SystemExit("来源不存在或操作结果不明确；请检查数据库状态。")
    print(f"已{ '撤回' if method == 'PATCH' else '删除' }来源 {args.source_id}。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
