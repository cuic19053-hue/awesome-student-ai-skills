"""Public skill guidance and scope-checked official knowledge.

No public source is project evidence. Guidance and examples are not policy and
must never be presented as personal facts. Official summaries require an exact
school/year scope and still point readers back to the original document.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .retrieval import _tokens
from .skills import ROOT, redact_source_contacts, registry

FIXTURE = ROOT / "server/evals/fixtures/innovation_research/seu_2026/rules.json"
OFFICIAL_MANIFEST = ROOT / "server/knowledge/official_sources.json"
EXAMPLE_MANIFEST = ROOT / "server/knowledge/example_sources.json"
EXAMPLE_ROOT = ROOT / "server/knowledge/approved_examples"
REPO_URL = "https://github.com/cuic19053-hue/awesome-student-ai-skills/blob/main/"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _id(*parts: str) -> str:
    return _sha("\0".join(parts).encode("utf-8"))


def _read_manifest(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 2_000_000:
        raise ValueError("公共来源清单超过大小上限。")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sources", []), list):
        raise ValueError("公共来源清单格式无效。")
    return data


def _https_public_url(value: Any, *, allow_query: bool = True) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urlsplit(value)
        return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username
                    and not parsed.password and parsed.port in (None, 443)
                    and (allow_query or not parsed.query) and not parsed.fragment)
    except ValueError:
        return False


def _approved_example(item: dict[str, Any]) -> dict[str, Any]:
    """Accept only manually approved, publicly redistributable and deidentified excerpts."""
    if (item.get("kind") != "example" or item.get("approved") is not True
            or item.get("privacy_reviewed") is not True or item.get("structure_reviewed") is not True
            or item.get("public_redistribution") is not True
            or not re.fullmatch(r"[a-z0-9][a-z0-9:_-]{0,199}", str(item.get("id", "")))
            or registry.get(item.get("skill_id", "")) is None
            or not _https_public_url(item.get("source_url"), allow_query=False)
            or not _https_public_url(item.get("rights_evidence_url"), allow_query=False)
            or item.get("rights_review_status") not in {"no_conflict", "resolved"}
            or (item.get("rights_review_status") == "resolved"
                and not _https_public_url(item.get("rights_resolution_url"), allow_query=False))
            or not isinstance(item.get("title"), str) or not item["title"].strip()
            or not re.fullmatch(r"[A-Za-z0-9:_-]{3,100}", str(item.get("approval_reference", "")))
            or not isinstance(item.get("license"), str) or not item["license"].strip()
            or not isinstance(item.get("attribution"), str) or not 3 <= len(item["attribution"].strip()) <= 500
            or not isinstance(item.get("school"), str) or not item["school"].strip()
            or not isinstance(item.get("scope"), str) or not item["scope"].strip()
            or not isinstance(item.get("application_year"), int)
            or not 1900 <= item["application_year"] <= 2200
            or not isinstance(item.get("example_structure"), str)
            or not 4 <= len(item["example_structure"].strip()) <= 500
            or item.get("example_match_type") not in {"direct", "cross_track"}
            or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("source_sha256", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("excerpt_sha256", "")))
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(item.get("verified_at", "")))):
        raise ValueError("真实范文缺少公开授权、脱敏复核、来源或范围信息。")
    date.fromisoformat(item["verified_at"])
    path = (EXAMPLE_ROOT / str(item.get("excerpt_path", ""))).resolve()
    if not path.is_relative_to(EXAMPLE_ROOT.resolve()) or path.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("范文摘录必须位于已审核目录内。")
    if path.stat().st_size > 200_000:
        raise ValueError("范文摘录超过大小上限。")
    raw = path.read_bytes()
    if not raw or len(raw) > 200_000 or _sha(raw) != item["excerpt_sha256"]:
        raise ValueError("范文摘录为空、过大或哈希不匹配。")
    text = raw.decode("utf-8")
    sensitive = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)\d{17}[\dXx](?!\d)"
    if (re.search(sensitive, text) or re.search(sensitive, item["example_structure"])
            or re.search(sensitive, item["title"]) or re.search(sensitive, item["attribution"])
            or re.search(r"\d", item["example_structure"])):
        raise ValueError("范文摘录包含疑似联系方式或身份证号，须先脱敏。")
    restrictions = item.get("restrictions", {})
    if (not isinstance(restrictions, dict)
            or any(k not in {"education_level", "college", "political_stage"} or not isinstance(v, list) or not v
                   or any(not isinstance(x, str) or not x.strip() for x in v)
                   for k, v in restrictions.items())):
        raise ValueError("范文适用对象限制无效。")
    source = {key: item[key] for key in (
        "id", "skill_id", "kind", "title", "source_url", "school", "application_year",
        "source_sha256", "verified_at", "license", "rights_evidence_url", "approval_reference",
        "example_structure", "example_match_type", "attribution", "rights_review_status")}
    source.update({"variant": item.get("variant", ""), "restrictions": restrictions,
                   "privacy_reviewed": True, "structure_reviewed": True,
                   "rights_resolution_url": item.get("rights_resolution_url", ""),
                   "scope": str(item.get("scope", "")) + "；已授权去标识化范文，仅供结构参考，不是当前用户事实。"})
    source["chunks"] = _markdown_chunks(text, item["id"])
    if not source["chunks"]:
        raise ValueError("范文摘录不含可检索片段。")
    return source


def _markdown_chunks(text: str, source_id: str, max_chars: int = 900) -> list[dict[str, str]]:
    """Retain lines and Markdown headings; long lines are split without losing provenance."""
    chunks: list[dict[str, str]] = []
    items: list[str] = []
    first = last = 0
    current_size = 0

    def flush() -> None:
        nonlocal items, first, last, current_size
        content = "\n".join(items).strip()
        if content:
            ref = f"第 {first}–{last} 行"
            chunks.append({"id": _id(source_id, ref, content), "source_ref": ref, "content": content})
        items, first, last, current_size = [], 0, 0, 0

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            if current_size >= max_chars // 2:
                flush()
            continue
        if re.match(r"^#{1,3}\s", line) and items:
            flush()
        for offset in range(0, len(line), max_chars):
            part = line[offset:offset + max_chars]
            if items and current_size + len(part) + 1 > max_chars:
                flush()
            if not items:
                first = number
            items.append(part)
            last = number
            current_size += len(part) + 1
    flush()
    return chunks


def _source_signature() -> tuple[tuple[str, int, int, str], ...]:
    """Detect local source edits and revocations without restarting the process."""
    paths = {ROOT / "index.json", FIXTURE, OFFICIAL_MANIFEST, EXAMPLE_MANIFEST}
    integrity_paths = {FIXTURE, OFFICIAL_MANIFEST, EXAMPLE_MANIFEST}
    for item in registry.skills:
        candidate = (ROOT / str(item.get("skill_md_path", ""))).resolve()
        if candidate.is_relative_to((ROOT / "subskills").resolve()):
            paths.add(candidate)
    if EXAMPLE_MANIFEST.is_file():
        try:
            data = _read_manifest(EXAMPLE_MANIFEST)
            for item in data.get("sources", []):
                if isinstance(item, dict) and item.get("approved") is True:
                    candidate = (EXAMPLE_ROOT / str(item.get("excerpt_path", ""))).resolve()
                    if candidate.is_relative_to(EXAMPLE_ROOT.resolve()):
                        paths.add(candidate)
                        integrity_paths.add(candidate)
        except (OSError, ValueError, TypeError):
            # The loader will fail closed instead of reusing an older snapshot.
            pass
    signature = []
    for path in sorted(paths):
        try:
            stat = path.stat()
            digest = ""
            if path in integrity_paths:
                digest = _sha(path.read_bytes()) if stat.st_size <= 2_000_000 else "oversize"
            signature.append((str(path), stat.st_mtime_ns, stat.st_size, digest))
        except OSError:
            signature.append((str(path), -1, -1, ""))
    return tuple(signature)


def public_sources() -> tuple[dict[str, Any], ...]:
    return _public_sources_cached(_source_signature())


@lru_cache(maxsize=4)
def _public_sources_cached(_signature: tuple[tuple[str, int, int, str], ...]) -> tuple[dict[str, Any], ...]:
    """Build the checked-in public corpus; no files uploaded by users are read."""
    sources: list[dict[str, Any]] = []
    for skill in registry.skills:
        resolved = registry.get(skill["name"])
        if not resolved:
            continue
        path = resolved["skill_path"]
        raw = path.read_bytes()
        source_id = "guidance:" + resolved["id"]
        source = {
            "id": source_id, "skill_id": resolved["id"], "kind": "skill_guidance",
            "variant": "",
            "restrictions": {},
            "title": resolved.get("display_name", resolved["id"]) + " · 项目写作指南",
            "source_url": REPO_URL + path.relative_to(ROOT).as_posix(),
            "school": "", "application_year": None,
            "scope": "项目内写作参考，不是官方评审规则；案例和数据不是用户事实。",
            "source_sha256": _sha(raw), "license": "MIT",
            "verified_at": None,
        }
        source["chunks"] = _markdown_chunks(redact_source_contacts(raw.decode("utf-8")), source_id)
        if source["chunks"]:
            sources.append(source)
    # Existing source-verified historical fixture. These are summaries, not quotes.
    if FIXTURE.is_file():
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for name, provenance in data.get("sources", {}).items():
            sid = data["id"] + ":" + name
            chunks = [{"id": _id(sid, item["id"], item["rule"]),
                       "source_ref": item["locator"], "content": item["rule"]}
                      for item in data.get("requirements", []) if item.get("source") == name]
            if not chunks:
                continue
            sources.append({
                "id": sid, "skill_id": data["skill_id"], "kind": "official",
                "variant": "",
                "restrictions": {},
                "title": data["institution"] + "2026年创新训练资料（" + name + "）",
                "source_url": provenance["url"], "school": data["institution"],
                "application_year": 2026,
                "scope": data["scope"] + "；以下是人工整理摘要而非原文，请回源核对。",
                "source_sha256": provenance["sha256"], "license": "官方政策摘要，回源核验",
                "verified_at": data.get("retrieved_date"),
                "chunks": chunks,
            })
    if OFFICIAL_MANIFEST.is_file():
        manifest = _read_manifest(OFFICIAL_MANIFEST)
        for item in manifest.get("sources", []):
            if not isinstance(item, dict):
                raise ValueError("公共官方来源清单格式无效。")
            parsed_url = urlsplit(item.get("source_url", ""))
            if item.get("kind") not in {"official", "institution_report"} or registry.get(item.get("skill_id", "")) is None:
                raise ValueError("公共官方来源清单含无效赛道或类型。")
            if (not re.fullmatch(r"[0-9a-f]{64}", item.get("source_sha256", ""))
                    or parsed_url.scheme != "https" or not parsed_url.hostname
                    or not parsed_url.hostname.endswith((".edu.cn", ".gov.cn"))
                    or parsed_url.username or parsed_url.password or parsed_url.port not in (None, 443)
                    or not item.get("school") or not isinstance(item.get("application_year"), int)
                    or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item.get("verified_at", ""))):
                raise ValueError("公共官方来源缺少可核查的来源、范围或校验值。")
            date.fromisoformat(item["verified_at"])
            source = {key: value for key, value in item.items() if key != "chunks"}
            source.setdefault("variant", "")
            source.setdefault("restrictions", {})
            if source["kind"] == "institution_report":
                structure = source.get("example_structure")
                if (not isinstance(structure, str) or not structure.strip()
                        or len(structure) > 500 or re.search(r"\d", structure)
                        or redact_source_contacts(structure) != structure):
                    raise ValueError("机构报道必须提供不含案例事实的结构摘要。")
            restrictions = source["restrictions"]
            if (not isinstance(restrictions, dict)
                    or any(key not in {"education_level", "college", "political_stage"} or not isinstance(values, list)
                           or not values or any(not isinstance(value, str) or not value.strip() for value in values)
                           for key, values in restrictions.items())):
                raise ValueError("公共官方来源的适用对象限制无效。")
            source["chunks"] = [{**chunk, "id": _id(item["id"], chunk["source_ref"], chunk["content"])}
                                for chunk in item.get("chunks", [])]
            if source["chunks"]:
                sources.append(source)
    if EXAMPLE_MANIFEST.is_file():
        manifest = _read_manifest(EXAMPLE_MANIFEST)
        for item in manifest.get("sources", []):
            if not isinstance(item, dict):
                raise ValueError("范文来源清单格式无效。")
            # Drafts remain private and never enter the public retriever.
            if item.get("approved") is True:
                sources.append(_approved_example(item))
    ids = [source["id"] for source in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("公共来源标识重复。")
    return tuple(sources)


def matching_sources(skill_id: str, school: str = "", year: int | None = None,
                     *, variant: str = "", filters: dict[str, str] | None = None,
                     guidance_only: bool = False, official_only: bool = False,
                     include_examples: bool = False) -> list[dict[str, Any]]:
    """No school or dated source may leak into an unknown/different scope."""
    return [source for source in public_sources()
            if source["skill_id"] == skill_id
            and (not source.get("variant") or source["variant"] == variant)
            and all((filters or {}).get(key, "") in values
                    for key, values in source.get("restrictions", {}).items())
            and (not guidance_only or source["kind"] == "skill_guidance")
            and (not official_only or source["kind"] == "official")
            and (source["kind"] != "example" or include_examples)
            and (source["kind"] == "example" or not source["school"] or (bool(school) and source["school"] == school.strip()))
            and (source["kind"] == "example" or source["application_year"] is None or source["application_year"] == year)]


def _local_candidates(skill_id: str, school: str, year: int | None, query: str,
                      *, variant: str = "", filters: dict[str, str] | None = None,
                      guidance_only: bool = False, official_only: bool = False,
                      include_examples: bool = False) -> list[dict[str, Any]]:
    terms = _tokens(query)
    scored = []
    for source in matching_sources(skill_id, school, year, variant=variant, filters=filters,
                                   guidance_only=guidance_only, official_only=official_only,
                                   include_examples=include_examples):
        metadata = {key: value for key, value in source.items() if key != "chunks"}
        for chunk in source["chunks"]:
            indexed_text = chunk["content"]
            if source["kind"] == "example":
                indexed_text += " " + source.get("title", "") + " " + source.get("scope", "")
            terms_in_chunk = _tokens(indexed_text)
            overlap = len(terms & terms_in_chunk)
            if not overlap:
                continue
            # Normalize long chunks without making one generic match dominant.
            score = overlap / max(1, len(terms_in_chunk) ** 0.5)
            scored.append({**metadata, **chunk, "source_id": source["id"],
                           "lexical_score": score, "vector_score": 0.0})
    scored.sort(key=lambda item: (-item["lexical_score"], item["id"]))
    return scored[:30]


def _fuse(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fuse ranked lists by RRF; scores from different models are never mixed."""
    indexed = {str(row["id"]): row for row in rows}
    score: dict[str, float] = {}
    for field in ("lexical_score", "vector_score"):
        ranking = sorted(
            (row for row in indexed.values() if float(row.get(field, 0) or 0) > 0),
            key=lambda row: (-float(row[field]), str(row["id"])),
        )[:30]
        for position, row in enumerate(ranking, 1):
            ident = str(row["id"])
            score[ident] = score.get(ident, 0.0) + 1.0 / (60 + position)
    result = [{**indexed[ident], "fusion_score": value} for ident, value in score.items()]
    result.sort(key=lambda row: (-row["fusion_score"], str(row["id"])))
    return result


def is_policy_question(query: str) -> bool:
    """Treat explicit eligibility, deadlines and policy claims as evidence-only."""
    normalized = re.sub(r"\s+", "", query)
    strong = ("官方规定", "官方政策", "评审规则", "申报条件", "申请条件",
              "报名条件", "资格要求", "申请资格", "申报资格", "报考条件",
              "评选标准", "评审标准", "截止时间", "资助标准", "奖学金金额",
              "排名门槛", "是否符合", "能不能申请", "能否申请", "可以申请吗",
              "可以报名吗", "我有资格吗")
    if any(term in normalized for term in strong):
        return True
    if any(term in normalized for term in ("怎么写", "如何写", "撰写", "润色", "写作结构", "章节结构",
                                            "帮我写", "我要写", "请写", "写一份", "起草", "生成一份")):
        return False
    if re.search(r"(?:资格|条件|门槛|排名|金额|截止|报名时间|政策).{0,8}(?:多少|要求|怎样|是什么|如何|能否|哪些|怎么算)", normalized):
        return True
    subject = ("申请", "申报", "评审", "评选", "评优", "报考", "报名", "报奖", "资格", "奖学金", "奖项", "单项奖")
    requirement = ("资格", "条件", "门槛", "标准", "排名", "截止", "多少钱", "金额",
                   "年龄", "年级", "人数", "次数", "材料清单", "绩点", "学分", "比例", "分数", "年限",
                   "名额", "限制", "是否能", "能否", "最低", "最高", "范围", "对象", "时间", "要求", "材料",
                   "规则", "政策", "办法", "看哪些")
    if any(term in normalized for term in subject) and any(term in normalized for term in requirement):
        return True
    return "项目" in normalized and any(term in normalized for term in
                                     ("资格", "门槛", "政策", "名额", "限制", "申报截止"))


def policy_scope_conflict(query: str, school: str, year: int | None) -> str:
    """Never answer a named school/year using a different confirmed scope."""
    if not is_policy_question(query):
        return ""
    mentioned_years = {int(value) for value in re.findall(r"(?<!\d)((?:19|20|21)\d{2})(?!\d)", query)}
    if len(mentioned_years) > 1 or (mentioned_years and (year is None or year not in mentioned_years)):
        return "问题中的年度与项目已确认的单一申报年度不一致，请先核对并更新项目年度。"
    mentioned_schools = {
        source["school"] for source in public_sources()
        if source.get("school") and source["school"] in query
    }
    if len(mentioned_schools) > 1 or (mentioned_schools and (not school or school.strip() not in mentioned_schools)):
        return "问题提到的学校与项目学校不一致，请先核对并更新项目学校。"
    # If an unfamiliar named school appears, do not assume it means the
    # current school. Generic references to “我的学院” are not named schools.
    if not mentioned_schools and school and school.strip() not in query:
        school_like = re.findall(r"[\u4e00-\u9fff]{2,16}(?:大学|学院)(?!生)", query)
        generic = ("我的学院", "本学院", "所在学院", "各学院", "该学院", "我院", "学校学院")
        if any(not any(token.endswith(word) for word in generic) for token in school_like):
            return "问题可能提到其他学校，请先核对项目学校后再检索。"
    return ""


class PublicKnowledgeRetriever:
    def __init__(self, store: Any, reranker: Any = None):
        self.store = store
        self.reranker = reranker

    def search(self, skill_id: str, query: str, school: str = "", year: int | None = None,
               top_k: int = 6, *, variant: str = "", filters: dict[str, str] | None = None,
               external_query_consent: bool = False, include_examples: bool = False) -> dict[str, Any]:
        if registry.get(skill_id) is None:
            return {"results": [], "retrieval_mode": "invalid_skill", "message": "赛道不存在。"}
        if not query.strip():
            return {"results": [], "retrieval_mode": "empty_query", "message": "请输入检索问题。"}
        try:
            conflict = policy_scope_conflict(query, school, year)
        except (OSError, ValueError, UnicodeError):
            conflict = "公共来源清单不可用，请先核对来源。"
        if conflict:
            return {"results": [], "official_evidence_found": False, "retrieval_mode": "scope_conflict",
                    "scope_conflict": conflict, "message": "无法核对适用范围，未引用规则。"}
        official_only = is_policy_question(query)
        failure = ""
        use_db = (os.environ.get("RAG_PUBLIC_DB_ENABLED", "").lower() == "true"
                  and callable(getattr(self.store, "search_public_knowledge", None)))
        cloud_client = None
        cloud_embedding = None
        cloud_revision = ""
        if external_query_consent is True and (
            not use_db or os.environ.get("RAG_CF_ENABLED", "").lower() != "true"
        ):
            failure = "免费云模型未启用或数据库检索不可用；未向云端发送检索问题。"
        if use_db and external_query_consent is True and os.environ.get("RAG_CF_ENABLED", "").lower() == "true":
            try:
                from .cloudflare_free import CloudflareFreeClient
                cloud_client = CloudflareFreeClient(
                    os.environ.get("RAG_CF_ACCOUNT_ID", ""), os.environ.get("RAG_CF_API_TOKEN", ""),
                    free_plan_confirmed=os.environ.get("RAG_CF_FREE_PLAN_CONFIRMED", "").lower() == "true",
                )
                cloud_revision = os.environ.get("RAG_CF_MODEL_REVISION", "").strip()
                if cloud_revision.startswith("cloudflare:bge-m3:") and len(cloud_revision) <= 200:
                    vectors = cloud_client.embed([query[:300]], scope="query", query_consent=True)
                    cloud_embedding = vectors[0] if vectors else None
                if cloud_embedding is None:
                    failure = "免费向量服务未就绪或不可用，已使用关键词召回。"
            except ValueError:
                failure = "免费模型服务配置未验证，已使用关键词召回。"
        if use_db:
            try:
                rows = self.store.search_public_knowledge(skill_id, school, year,
                    sorted(_tokens(query), key=lambda term: (-len(term), term))[:80],
                    cloud_embedding, cloud_revision, variant, filters or {}, official_only, include_examples)
                has_vector_results = bool(cloud_embedding) and any(
                    float(row.get("vector_score", 0) or 0) > 0 for row in rows
                )
                mode = "database_hybrid" if has_vector_results else "database_keyword"
                if cloud_embedding and not has_vector_results:
                    failure = "未命中相同模型版本的向量；已使用关键词召回。"
            except (RuntimeError, OSError, ValueError):
                # The database owns the publication state. Never fall back to
                # checked-in copies after an outage: that could resurrect a
                # source an administrator has revoked.
                rows = []
                mode = "database_unavailable"
                failure = "公共知识库不可用；为避免返回已撤回来源，本次不返回公共资料。"
                use_db = False
        else:
            try:
                rows = _local_candidates(skill_id, school, year, query, variant=variant, filters=filters,
                                         official_only=official_only, include_examples=include_examples)
                mode = "local_keyword"
            except (OSError, ValueError, UnicodeError):
                # A corrupt or oversized approval manifest must not resurrect
                # older cached sources or prevent the rest of the app running.
                rows = []
                mode = "local_unavailable"
                failure = "本地公共来源清单无效；为避免使用未经审核资料，本次未返回结果。"
            # Never make a cloud store rely on the user's local computer.
            if (mode != "local_unavailable" and os.environ.get("RAG_LOCAL_VECTOR_INDEX", "").strip()
                    and not callable(getattr(self.store, "search_public_knowledge", None))):
                try:
                    from .local_public_vectors import local_vector_candidates
                    vector_rows = local_vector_candidates(matching_sources(
                        skill_id, school, year, variant=variant, filters=filters, official_only=official_only,
                        include_examples=include_examples), query)
                    merged = {row["id"]: row for row in rows}
                    for row in vector_rows:
                        if row["id"] in merged:
                            merged[row["id"]]["vector_score"] = row["vector_score"]
                        else:
                            merged[row["id"]] = row
                    rows = list(merged.values())
                    if vector_rows:
                        mode = "local_hybrid"
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    failure = "本地向量索引不可用或版本不匹配；已降级为关键词检索。"
        if official_only:
            # Defense in depth for an out-of-date backend or injected test store.
            rows = [row for row in rows if row.get("kind") == "official"]
        rows = _fuse(rows)
        # An applicable reviewed official source outranks project guidance; the
        # latter must never displace the former merely due to lexical frequency.
        rows.sort(key=lambda row: row.get("kind") != "official")
        reranked = False
        reranker = self.reranker
        if (reranker is None and os.environ.get("RAG_LOCAL_RERANK_MODEL", "").strip()
                and not callable(getattr(self.store, "search_public_knowledge", None))):
            from .local_reranker import LocalReranker
            reranker = LocalReranker(os.environ["RAG_LOCAL_RERANK_MODEL"].strip())
        if cloud_client and use_db and external_query_consent and rows:
            # Only RLS-published public text is sent; project materials never enter
            # this candidate list. User query requires explicit per-request consent.
            try:
                order = cloud_client.rerank(query, [row["content"] for row in rows[:30]], query_consent=True)
                head, tail = rows[:30], rows[30:]
                if (isinstance(order, list) and len(order) == len(head)
                        and all(type(i) is int for i in order) and set(order) == set(range(len(head)))):
                    rows = [head[index] for index in order] + tail
                    reranked = True
                else:
                    failure = (failure + " " if failure else "") + "免费重排不可用，已保留融合排序。"
            except Exception:
                failure = (failure + " " if failure else "") + "免费重排不可用，已保留融合排序。"
        elif reranker and rows:
            try:
                # Keep the prompt bounded for small local models. The remaining
                # RRF candidates stay after the reranked head.
                head, tail = rows[:8], rows[8:]
                order = reranker.rerank(query, [row["content"] for row in head])
                if (isinstance(order, list) and len(order) == len(head)
                        and all(type(index) is int for index in order)
                        and set(order) == set(range(len(head)))):
                    rows = [head[index] for index in order] + tail
                    reranked = True
                else:
                    failure = (failure + " " if failure else "") + "重排结果无效，已保留融合排序。"
            except Exception:
                failure = (failure + " " if failure else "") + "重排服务不可用，已保留融合排序。"
        rows.sort(key=lambda row: row.get("kind") != "official")
        results = []
        for row in rows[:max(1, min(top_k, 10))]:
            results.append({key: row.get(key) for key in (
                "id", "source_id", "skill_id", "variant", "restrictions", "kind", "title", "source_url", "school",
                "application_year", "scope", "source_sha256", "source_ref", "content", "lexical_score",
                "vector_score", "fusion_score", "verified_at", "license", "rights_evidence_url", "example_structure",
                "example_match_type", "attribution", "rights_review_status", "rights_resolution_url")})
        official_found = any(row["kind"] == "official" for row in results)
        message = "项目指南与示例不是官方规则或用户事实。官方资料仅限标注学校和年份；请回源核对。"
        if not official_found:
            message += "本次没有检索到适用的官方依据；请补充学校、年度、学历或学院，并核验当年通知。"
        return {"results": results, "retrieval_mode": mode, "reranked": reranked, "official_only": official_only,
                "official_evidence_found": official_found, "fallback_reason": failure, "message": message}
