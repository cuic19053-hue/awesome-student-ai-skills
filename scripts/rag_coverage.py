#!/usr/bin/env python3
"""Report checked-in public corpus coverage without inventing official sources."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
from proposal.knowledge import public_sources
from utils.skill_cards import build_skill_cards


def coverage() -> dict:
    skills = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))["skills"]
    cards = build_skill_cards(skills)
    sources = public_sources()
    reports = []
    for card in cards:
        selected = [source for source in sources if source["skill_id"] == card["id"]]
        guides = [source for source in selected if source["kind"] == "skill_guidance"]
        officials = [source for source in selected if source["kind"] == "official"]
        reports_for_skill = [source for source in selected if source["kind"] == "institution_report"]
        examples = [source for source in selected if source["kind"] == "example"]
        reports.append({
            "id": card["id"], "name": card["name"],
            "guidance_sources": len(guides),
            "guidance_chunks": sum(len(source["chunks"]) for source in guides),
            "official_sources": [{"title": s["title"], "school": s["school"],
                                  "year": s["application_year"], "url": s["source_url"],
                                  "scope": s["scope"]} for s in officials],
            "official_coverage": "school_year_scoped" if officials else "missing",
            "institution_reports": [{"title": s["title"], "school": s["school"],
                                     "year": s["application_year"], "url": s["source_url"],
                                     "scope": s["scope"]} for s in reports_for_skill],
            "real_example_coverage": (
                "direct" if any(source.get("example_match_type") == "direct" for source in examples)
                else "cross_track_only" if examples else "missing"
            ),
        })
    return {
        "total_skills": len(skills), "routing_cards": len(cards),
        "guidance_sources": sum(s["kind"] == "skill_guidance" for s in sources),
        "official_sources": sum(s["kind"] == "official" for s in sources),
        "institution_report_sources": sum(s["kind"] == "institution_report" for s in sources),
        "real_example_sources": sum(s["kind"] == "example" for s in sources),
        "total_chunks": sum(len(s["chunks"]) for s in sources),
        "notice": "仓库知识不等于数据库已发布。写作指南不是官方规则；历史批次不代表当前政策。",
        "skills": reports,
    }


if __name__ == "__main__":
    print(json.dumps(coverage(), ensure_ascii=False, indent=2))
