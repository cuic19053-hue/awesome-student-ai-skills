from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from proposal.knowledge import PublicKnowledgeRetriever, matching_sources, public_sources
from proposal.storage import Store
from proposal.tools import ProposalTools


def test_corpus_has_35_license_marked_guides_with_stable_line_provenance():
    sources = public_sources()
    guides = [s for s in sources if s["kind"] == "skill_guidance"]
    assert len(guides) == 35
    assert len({g["skill_id"] for g in guides}) == 35
    assert all(g["source_sha256"] and g["license"] == "MIT" and g["chunks"] for g in guides)
    assert all(c["source_ref"].startswith("第 ") for g in guides for c in g["chunks"])
    ids = [c["id"] for s in sources for c in s["chunks"]]
    assert len(ids) == len(set(ids))
    import re
    assert not any(
        re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", chunk["content"])
        for guide in guides for chunk in guide["chunks"]
    )
    from proposal.skills import registry
    assert "@" not in registry.guidance("csc-scholarship", max_chars=100_000)


def test_historical_official_source_is_not_generalized():
    no_school = matching_sources("innovation-research", "", 2026)
    wrong_school = matching_sources("innovation-research", "清华大学", 2026)
    no_year = matching_sources("innovation-research", "东南大学", None)
    wrong_year = matching_sources("innovation-research", "东南大学", 2027)
    right_scope = matching_sources("innovation-research", "东南大学", 2026)
    assert all(s["kind"] != "official" for s in no_school + wrong_school + no_year + wrong_year)
    assert sum(s["kind"] == "official" for s in right_scope) == 3
    assert all("摘要" in s["scope"] for s in right_scope if s["kind"] == "official")


def test_tool_uses_server_project_scope_not_query_contents(tmp_path):
    store = Store(tmp_path)
    project = store.create_project(title="测试", school="清华大学")
    tools = ProposalTools(store)
    result = tools.search_public_knowledge(project["id"], "东南大学 2026 项目经费")
    assert result["results"]
    assert all(r["kind"] == "skill_guidance" for r in result["results"])
    assert "不是官方规则" in result["message"]
    assert tools.search_public_knowledge("does-not-exist", "要求")["results"] == []


def test_db_outage_does_not_resurrect_revoked_official_data(monkeypatch):
    class FailingStore:
        def search_public_knowledge(self, *args):
            raise RuntimeError("down")

    monkeypatch.setenv("RAG_PUBLIC_DB_ENABLED", "true")
    result = PublicKnowledgeRetriever(FailingStore()).search(
        "innovation-research", "项目经费 预算", "东南大学", 2026)
    assert result["retrieval_mode"] == "database_unavailable"
    assert result["fallback_reason"]
    assert result["results"] == []


def test_public_hybrid_fusion_and_rerank_never_invents_sources(monkeypatch):
    from proposal import local_public_vectors
    source = next(s for s in public_sources() if s["skill_id"] == "national-scholarship")
    second = source["chunks"][-1]
    metadata = {k: v for k, v in source.items() if k != "chunks"}
    monkeypatch.setenv("RAG_LOCAL_VECTOR_INDEX", "not-read-when-mocked")
    monkeypatch.setattr(local_public_vectors, "local_vector_candidates", lambda *args: [
        {**metadata, **second, "source_id": source["id"], "lexical_score": 0.0, "vector_score": .99}
    ])

    class Reverse:
        def rerank(self, query, docs):
            return list(reversed(range(len(docs))))

    result = PublicKnowledgeRetriever(object(), Reverse()).search("national-scholarship", "学习成绩")
    assert result["retrieval_mode"] == "local_hybrid"
    assert result["reranked"]
    assert all(row["source_id"] == source["id"] for row in result["results"])


def test_public_rerank_failure_keeps_candidates():
    class Broken:
        def rerank(self, query, docs):
            raise TimeoutError()
    result = PublicKnowledgeRetriever(object(), Broken()).search("national-scholarship", "学习成绩")
    assert result["results"]
    assert not result["reranked"]
    assert "重排服务不可用" in result["fallback_reason"]


def test_two_school_notices_are_not_cross_applied():
    wx = matching_sources("motivation-scholarship", "无锡学院", 2026, filters={"education_level": "本科"})
    dl = matching_sources("motivation-scholarship", "大连海洋大学", 2026, filters={"education_level": "本科"})
    wx_rules = [s for s in wx if s["kind"] == "official"]
    dl_rules = [s for s in dl if s["kind"] == "official"]
    assert len(wx_rules) == len(dl_rules) == 1
    assert all(s["school"] == "无锡学院" for s in wx_rules)
    assert all(s["school"] == "大连海洋大学" for s in dl_rules)
    assert all(s["kind"] != "official" for s in matching_sources("motivation-scholarship", "无锡学院", 2027))
    result = PublicKnowledgeRetriever(object()).search("motivation-scholarship", "家庭经济困难综合测评", "大连海洋大学", 2026, filters={"education_level": "本科"})
    assert result["official_evidence_found"]
    assert result["results"][0]["kind"] == "official"
    assert result["results"][0]["school"] == "大连海洋大学"


def test_generated_citation_requires_exact_retrieved_source_and_location():
    from proposal.agent import _check_generated_citations
    evidence = [{"source_name": "原始材料.txt", "source_ref": "段落 2"}]
    public = [{"title": "学校2026年通知", "source_ref": "第一条"}]
    text = ("事实 [来源：原始材料.txt，段落 2]。规则 [来源：学校2026年通知，第一条]。"
            "不明 [来源：捏造通知，第一条]。误页 [来源：原始材料.txt，段落 9]。")
    result, errors = _check_generated_citations(text, evidence, public)
    assert "[来源：原始材料.txt，段落 2]" in result
    assert "[来源：学校2026年通知，第一条]" in result
    assert result.count("【待核实来源】") == 2
    assert len(errors) == 2


def test_cloud_query_and_rerank_require_each_request_consent(monkeypatch):
    from proposal import cloudflare_free
    source = next(s for s in public_sources() if s["skill_id"] == "national-scholarship")
    chunk = source["chunks"][0]
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls.append("init")
        def embed(self, texts, *, scope, query_consent=False):
            calls.append(("embed", texts, scope, query_consent))
            return [[0.1] * 1024]
        def rerank(self, query, documents, *, query_consent=False):
            calls.append(("rerank", query, documents, query_consent))
            return [0]

    class FakeStore:
        def search_public_knowledge(self, skill_id, school, year, terms, embedding, revision, variant, filters, official_only, include_examples):
            calls.append(("db", embedding, revision))
            metadata = {k: v for k, v in source.items() if k != "chunks"}
            return [{**metadata, **chunk, "source_id": source["id"],
                     "lexical_score": 1, "vector_score": .5 if embedding else 0}]

    monkeypatch.setattr(cloudflare_free, "CloudflareFreeClient", FakeClient)
    for key, value in {"RAG_PUBLIC_DB_ENABLED": "true", "RAG_CF_ENABLED": "true",
                       "RAG_CF_FREE_PLAN_CONFIRMED": "true", "RAG_CF_MODEL_REVISION": "cloudflare:bge-m3:test"}.items():
        monkeypatch.setenv(key, value)
    searcher = PublicKnowledgeRetriever(FakeStore())
    result = searcher.search("national-scholarship", "私有的检索问题")
    assert result["retrieval_mode"] == "database_keyword"
    assert all(call == "db" if isinstance(call, str) else call[0] == "db" for call in calls)
    calls.clear()
    result = searcher.search("national-scholarship", "私有的检索问题", external_query_consent=True)
    assert result["retrieval_mode"] == "database_hybrid"
    assert result["reranked"] is True
    assert any(isinstance(call, tuple) and call[0] == "embed" for call in calls)
    assert any(isinstance(call, tuple) and call[0] == "rerank" for call in calls)


def test_model_tool_cannot_grant_external_query_consent(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project = store.create_project(title="测试")
    tools = ProposalTools(store)
    calls = []
    monkeypatch.setattr(tools.public_knowledge, "search", lambda *a, **kw: calls.append(kw) or {"results": []})
    response = tools.invoke("search_public_knowledge", {
        "project_id": project["id"], "query": "个人问题", "external_query_consent": True,
    })
    assert response.get("error")
    assert not calls
    tools.search_public_knowledge(project["id"], "个人问题")
    assert calls[-1]["external_query_consent"] is False
    tools.search_public_knowledge_user(project["id"], "个人问题", external_query_consent=True)
    assert calls[-1]["external_query_consent"] is True


def test_award_variants_do_not_cross_apply():
    student = matching_sources("outstanding-student", "无锡学院", 2024, variant="outstanding_student", filters={"education_level": "本科"})
    league = matching_sources("outstanding-student", "无锡学院", 2024, variant="outstanding_youth_league")
    unknown = matching_sources("outstanding-student", "无锡学院", 2024)
    assert {s["id"] for s in student if s["kind"] == "official"} == {"wuxi-2024-outstanding-student"}
    assert {s["id"] for s in league if s["kind"] == "official"} == {"wuxi-2024-outstanding-youth-league"}
    assert all(s["kind"] != "official" for s in unknown)


def test_curated_official_retrieval_cases_keep_school_year_and_source():
    cases = [
        ("motivation-scholarship", "无锡学院", 2026, "", "家庭经济困难", "wuxi-2026-motivation-scholarship"),
        ("motivation-scholarship", "大连海洋大学", 2026, "", "综合测评", "dlou-2026-motivation-scholarship"),
        ("national-scholarship", "无锡学院", 2026, "", "综合测评", "wuxi-2026-national-scholarship"),
        ("grant-application", "无锡学院", 2026, "", "困难等级", "wuxi-2026-national-grant"),
        ("innovation-research", "无锡学院", 2026, "", "研究周期", "wuxi-2026-innovation-research"),
        ("entrepreneurship-practice", "无锡学院", 2026, "", "企业法人", "wuxi-2026-entrepreneurship-practice"),
        ("social-survey", "无锡学院", 2026, "", "项目立项", "wuxi-2026-summer-social-survey"),
        ("major-transfer", "无锡学院", 2026, "", "转专业申请", "wuxi-2026-major-transfer"),
        ("outstanding-student", "无锡学院", 2024, "outstanding_youth_league", "共青团员参评资格", "wuxi-2024-outstanding-youth-league"),
        ("youth-league-application", "无锡学院", 2026, "", "入团申请", "wuxi-2026-youth-league-application"),
    ]
    for skill, school, year, variant, query, expected in cases:
        result = PublicKnowledgeRetriever(object()).search(skill, query, school, year, variant=variant, filters={"education_level": "本科"})
        official = [row for row in result["results"] if row["kind"] == "official"]
        assert official and any(row["source_id"] == expected for row in official), (skill, query)
        assert all(row["school"] == school and row["application_year"] == year for row in official)
        assert all(row["source_url"].startswith("https://") and row["source_ref"] for row in official)


def test_academic_level_and_college_filters_are_fail_closed():
    skill, school, year = "enterprise-scholarship", "大连理工大学", 2025
    assert all(s["kind"] != "official" for s in matching_sources(skill, school, year))
    assert all(s["kind"] != "official" for s in matching_sources(skill, school, year, filters={"education_level": "本科", "college": "生物工程学院"}))
    assert all(s["kind"] != "official" for s in matching_sources(skill, school, year, filters={"education_level": "硕士", "college": "机械工程学院"}))
    assert any(s["id"] == "dlut-2025-enterprise-scholarships" for s in matching_sources(skill, school, year, filters={"education_level": "硕士", "college": "生物工程学院"}))
    csc = matching_sources("csc-scholarship", "西安交通大学", 2027, filters={"education_level": "本科"})
    assert all(s["kind"] != "official" for s in csc)
    csc = matching_sources("csc-scholarship", "西安交通大学", 2027, filters={"education_level": "博士"})
    assert any(s["id"] == "xjtu-2027-csc-aus-nz-canada" for s in csc)


def test_explicit_policy_questions_never_use_unverified_guidance():
    searcher = PublicKnowledgeRetriever(object())
    # Repository guidance contains outdated amounts; no school/year must not
    # let the system infer an eligibility rule from it.
    missing = searcher.search("national-scholarship", "国家奖学金评选时学业排名有何要求")
    assert missing["official_only"] is True
    assert not missing["official_evidence_found"]
    assert missing["results"] == []
    assert "没有检索到适用的官方依据" in missing["message"]
    applicable = searcher.search("national-scholarship", "国家奖学金评选排名条件", "无锡学院", 2026,
                                  filters={"education_level": "本科"})
    assert applicable["official_only"] is True
    assert applicable["official_evidence_found"]
    assert all(item["kind"] == "official" for item in applicable["results"])
    scoped = searcher.search("single-scholarship", "单项奖学金评选范围与获奖时间",
                             "河南大学", 2026, filters={"education_level": "本科"})
    assert scoped["official_only"] is True
    assert scoped["official_evidence_found"] and all(item["kind"] == "official" for item in scoped["results"])
    from proposal.knowledge import is_policy_question
    assert not is_policy_question("帮我安排项目研究时间")
    assert not is_policy_question("帮我写一份奖学金申请材料")
    assert is_policy_question("学校奖学金评选办法是什么")
    # Writing-structure requests may still use explicitly labelled guidance.
    writing = searcher.search("national-scholarship", "申请书章节结构怎么写")
    assert writing["results"]
    assert all(item["kind"] == "skill_guidance" for item in writing["results"])


def test_model_guidance_excludes_unverified_amounts_and_examples(tmp_path):
    from proposal.skills import registry
    guidance = registry.model_guidance("national-scholarship", 100_000)
    assert "8000元" not in guidance and "10000 元" not in guidance
    assert "国家奖学金" in guidance
    store = Store(tmp_path)
    project = store.create_project(title="国奖", school="")
    store.update_project(project["id"], state={"skill_id": "national-scholarship"})
    tools = ProposalTools(store)
    result = tools.search_public_knowledge(project["id"], "申请理由怎么写")
    assert result["results"]
    assert all(item.get("model_content_restricted") for item in result["results"])
    assert all("8000元" not in item["content"] for item in result["results"])


def test_examples_require_license_privacy_review_and_only_structure_reaches_model(tmp_path, monkeypatch):
    import hashlib
    import pytest
    from proposal import knowledge
    excerpt = "# 方案结构\n某示例成果取得98%的指标，不能变成当前用户事实。"
    examples = tmp_path / "examples"
    examples.mkdir()
    path = examples / "sample.md"
    path.write_text(excerpt, encoding="utf-8")
    monkeypatch.setattr(knowledge, "EXAMPLE_ROOT", examples)
    item = {
        "id": "example:test", "skill_id": "innovation-research", "kind": "example",
        "title": "已授权示例", "source_url": "https://example.edu.cn/original",
        "rights_evidence_url": "https://example.edu.cn/license", "license": "CC-BY-4.0",
        "approval_reference": "review-123", "approved": True, "privacy_reviewed": True,
        "structure_reviewed": True, "public_redistribution": True, "school": "示例大学",
        "application_year": 2026, "verified_at": "2026-10-27", "scope": "仅该校批次",
        "source_sha256": "a" * 64, "excerpt_path": "sample.md",
        "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
        "example_structure": "包含背景、实施方法与结果讨论等部分",
        "example_match_type": "cross_track",
        "attribution": "公开作者署名（测试）",
        "rights_review_status": "no_conflict",
    }
    source = knowledge._approved_example(item)
    monkeypatch.setattr(knowledge, "public_sources", lambda: (source,))
    store = Store(tmp_path / "store")
    project = store.create_project(title="项目", school="当前大学")
    store.update_project(project["id"], state={"skill_id": "innovation-research", "confirmed_facts": {"application_year": "2027"}})
    tools = ProposalTools(store)
    assert not tools.search_public_knowledge_user(project["id"], "方案结构")["results"]
    raw = tools.search_public_knowledge_user(project["id"], "方案结构", include_examples=True)
    model = tools.search_public_knowledge(project["id"], "方案结构", include_examples=True)
    assert "98%" in raw["results"][0]["content"]
    assert "98%" not in model["results"][0]["content"]
    assert model["results"][0]["model_content_restricted"] is True
    assert model["results"][0]["content"] == item["example_structure"]
    assert raw["results"][0]["school"] == "示例大学"
    assert raw["results"][0]["application_year"] == 2026
    assert raw["results"][0]["example_match_type"] == "cross_track"
    assert raw["results"][0]["attribution"] == item["attribution"]
    assert "attribution" not in model["results"][0]
    assert tools.search_public_knowledge_user(
        project["id"], "项目申报条件", include_examples=True
    )["results"] == []

    for flag in ("approved", "privacy_reviewed", "structure_reviewed", "public_redistribution"):
        with pytest.raises(ValueError):
            knowledge._approved_example({**item, flag: False})
    with pytest.raises(ValueError):
        knowledge._approved_example({**item, "excerpt_path": "../outside.md"})
    with pytest.raises(ValueError):
        knowledge._approved_example({**item, "example_structure": "成果98%"})
    with pytest.raises(ValueError):
        knowledge._approved_example({**item, "rights_review_status": "resolved"})
    with pytest.raises(ValueError):
        knowledge._approved_example({**item, "rights_review_status": "conflict_unresolved"})
    path.write_text("邮箱 someone@example.org", encoding="utf-8")
    with pytest.raises(ValueError):
        knowledge._approved_example({**item, "excerpt_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})


def test_college_report_is_separate_from_authoritative_policy(tmp_path):
    store = Store(tmp_path)
    project = store.create_project(title="院级科研", school="河南大学")
    store.update_project(project["id"], state={
        "skill_id": "college-research",
        "confirmed_facts": {"application_year": "2024", "college": "基础医学院"},
    })
    tools = ProposalTools(store)
    report = tools.search_public_knowledge_user(project["id"], "科创训练营项目答辩科学问题")
    assert any(item["kind"] == "institution_report" for item in report["results"])
    assert not report["official_evidence_found"]
    model = tools.search_public_knowledge(project["id"], "科创训练营项目答辩科学问题")
    model_report = next(item for item in model["results"] if item["kind"] == "institution_report")
    assert model_report["model_content_restricted"] is True
    assert "该学院报道" not in model_report["content"]
    assert "研究问题" in model_report["content"]
    policy = tools.search_public_knowledge_user(project["id"], "院级科研项目申报条件")
    assert policy["official_only"] is True and policy["results"] == []


def test_local_example_revocation_invalidates_cache_without_restart(tmp_path, monkeypatch):
    import hashlib
    import json
    import os
    from proposal import knowledge
    examples = tmp_path / "examples"
    examples.mkdir()
    excerpt = "# 研究结构\n背景与方法仅供讨论。"
    (examples / "sample.md").write_text(excerpt, encoding="utf-8")
    item = {
        "id": "example:revocation", "skill_id": "innovation-research", "kind": "example",
        "title": "公开授权范文", "source_url": "https://example.edu.cn/example",
        "rights_evidence_url": "https://example.edu.cn/license", "license": "CC-BY-4.0",
        "approval_reference": "review-456", "approved": True, "privacy_reviewed": True,
        "structure_reviewed": True, "public_redistribution": True, "school": "测试大学",
        "application_year": 2026, "verified_at": "2026-10-27", "scope": "测试范围",
        "source_sha256": "a" * 64, "excerpt_path": "sample.md",
        "excerpt_sha256": hashlib.sha256(excerpt.encode()).hexdigest(),
        "example_structure": "研究背景与方法的结构示例",
        "example_match_type": "cross_track",
        "attribution": "公开作者署名（测试）",
        "rights_review_status": "no_conflict",
    }
    manifest = tmp_path / "example_sources.json"
    manifest.write_text(json.dumps({"version": 1, "sources": [item]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(knowledge, "EXAMPLE_ROOT", examples)
    monkeypatch.setattr(knowledge, "EXAMPLE_MANIFEST", manifest)
    assert any(s["id"] == item["id"] for s in knowledge.public_sources())
    before = manifest.stat()
    original = manifest.read_text(encoding="utf-8")
    changed = original.replace('"approved": true', '"approved": null')
    assert len(changed.encode()) == len(original.encode())
    manifest.write_text(changed, encoding="utf-8")
    os.utime(manifest, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert all(s["id"] != item["id"] for s in knowledge.public_sources())


def test_corrupt_public_manifest_fails_closed_without_using_cached_sources(tmp_path, monkeypatch):
    from proposal import knowledge
    manifest = tmp_path / "examples.json"
    manifest.write_text('{"version":1,"sources":[]}', encoding="utf-8")
    monkeypatch.setattr(knowledge, "EXAMPLE_MANIFEST", manifest)
    searcher = knowledge.PublicKnowledgeRetriever(object())
    assert searcher.search("innovation-research", "研究方法")["results"]
    manifest.write_text('{"sources":', encoding="utf-8")
    result = searcher.search("innovation-research", "研究方法")
    assert result["retrieval_mode"] == "local_unavailable"
    assert result["results"] == []
    assert "清单无效" in result["fallback_reason"]
