#!/usr/bin/env python3
"""Audit official sources and approved example hashes; never change publication."""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import ipaddress
import json
from pathlib import Path
import sys
import socket
import urllib.parse
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from proposal.knowledge import public_sources
from proposal.tools import _OfficialRedirectHandler, _validate_public_official_url


def _validate_public_https(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443)):
        raise ValueError("范文来源必须是公开 HTTPS 地址。")
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise ValueError("不允许访问本机地址。")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("无法解析来源。")
    egress_testnet = ipaddress.ip_network("198.18.0.0/15")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip not in egress_testnet and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
            raise ValueError("不允许访问本机或私有网络地址。")
    return url


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def audit(online: bool = False) -> dict:
    sources = [s for s in public_sources() if s["kind"] in {"official", "institution_report", "example"}]
    by_url = defaultdict(list)
    for source in sources:
        by_url[source["source_url"]].append(source)
    outcomes = []
    for url, items in by_url.items():
        entry = {"url": url, "ids": [item["id"] for item in items], "status": "not_checked"}
        if online:
            try:
                is_official = all(item["kind"] in {"official", "institution_report"} for item in items)
                validator = _validate_public_official_url if is_official else _validate_public_https
                validator(url)
                opener = urllib.request.build_opener(_OfficialRedirectHandler() if is_official else _PublicRedirectHandler())
                request = urllib.request.Request(url, headers={"User-Agent": "StardustKnowledgeAudit/1.0"})
                with opener.open(request, timeout=10) as response:
                    validator(response.geturl())
                    body = response.read(5_000_001)
                if len(body) > 5_000_000:
                    entry["status"] = "too_large"
                else:
                    observed = hashlib.sha256(body).hexdigest()
                    entry["status"] = "unchanged" if all(observed == item["source_sha256"] for item in items) else "changed"
                    entry["observed_sha256"] = observed
            except (ValueError, OSError, urllib.error.URLError):
                entry["status"] = "unavailable"
        outcomes.append(entry)
    # Public permissions must remain accessible, but accessibility does not
    # substitute for the human review of scope and actual license terms.
    evidence_urls = {
        url for source in sources if source["kind"] == "example"
        for url in (source.get("rights_evidence_url"), source.get("rights_resolution_url")) if url
    }
    for url in sorted(evidence_urls):
        entry = {"url": url, "ids": [s["id"] for s in sources
                                       if url in (s.get("rights_evidence_url"), s.get("rights_resolution_url"))],
                 "kind": "rights_evidence", "status": "not_checked"}
        if online:
            try:
                _validate_public_https(url)
                opener = urllib.request.build_opener(_PublicRedirectHandler())
                request = urllib.request.Request(url, headers={"User-Agent": "StardustKnowledgeAudit/1.0"})
                with opener.open(request, timeout=10) as response:
                    _validate_public_https(response.geturl())
                    entry["status"] = "unchanged" if 200 <= response.status < 300 else "unavailable"
            except (ValueError, OSError, urllib.error.URLError):
                entry["status"] = "unavailable"
        outcomes.append(entry)
    return {"sources": len(sources), "unique_urls": len(by_url), "online": online,
            "notice": "校验哈希不代表内容仍然适用；变化或不可访问须人工复核，脚本不会自动发布。",
            "results": outcomes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="请求官方源并比对内容哈希")
    result = audit(parser.parse_args().online)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["online"] and any(item["status"] != "unchanged" for item in result["results"]):
        raise SystemExit(1)
