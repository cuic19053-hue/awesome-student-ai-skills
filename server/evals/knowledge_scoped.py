#!/usr/bin/env python3
"""Source-linked retrieval and scope probes; agent-curated, not human-approved gold."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
from proposal.knowledge import PublicKnowledgeRetriever, public_sources

# Each question is linked to a source previously inspected in full. These are
# still agent-curated test cases; independent human review remains mandatory.
QUESTIONS = {
    "seu-2026-innovation-training:notice": "校级SRTP项目申报资格是什么",
    "wuxi-2026-motivation-scholarship": "励志奖学金的奖励对象和标准是什么",
    "wuxi-2026-national-grant": "国家助学金困难学生资助对象是什么",
    "wuxi-2027-selected-graduate": "应届毕业生选调条件和职位类别是什么",
    "wuxi-2026-university-scholarship": "学校特等奖学金综合测评申请条件是什么",
    "wuxi-2026-national-scholarship": "国家奖学金的奖励对象和标准是什么",
    "wuxi-2026-entrepreneurship-training": "创业训练项目商业计划书怎么准备",
    "wuxi-2026-entrepreneurship-practice": "创业实践项目需要实际创业多久",
    "wuxi-2027-internet-plus": "高教主赛道有哪些项目类型",
    "wuxi-2027-internet-plus-red-tour": "红旅赛道活动主题是什么",
    "wuxi-2027-must-exchange": "澳门科技大学交流时间安排是什么",
    "wuxi-2026-challenge-cup-training": "挑战杯训练营课程安排有哪些",
    "wuxi-2026-summer-social-survey": "乡村产业调研活动有哪些",
    "wuxi-2026-summer-volunteer-teaching": "农村留守儿童助学帮扶有哪些",
    "wuxi-2026-summer-policy-lecture": "理论宣传宣讲活动怎么开展",
    "wuxi-2026-summer-tech-service": "农技指导和智慧农业科技实践有哪些",
    "wuxi-2024-outstanding-student": "省级三好学生的评选标准是什么",
    "wuxi-2024-outstanding-cadre": "优秀学生干部的任职条件是什么",
    "wuxi-2024-outstanding-graduate": "优秀毕业生的评选条件是什么",
    "wuxi-2024-class-collective": "先进班集体的评选标准是什么",
    "wuxi-2026-jiangsu-enlistment": "男性公民兵役登记年龄是什么",
    "wuxi-2026-major-transfer": "普通本科生转专业的申请对象有哪些",
    "wuxi-2023-western-plan": "西部计划志愿者招募对象是什么",
    "wuxi-2026-youth-league-application": "入团申请书应该向哪个团组织递交",
    "xjtu-2027-graduate-recommendation": "本科推免推荐的基本条件是什么",
    "xjtu-2027-csc-aus-nz-canada": "澳新加合作高校公派博士项目面向哪些人",
    "dlut-2025-enterprise-scholarships": "研究生企业专项奖学金申报对象是什么",
    "henu-2026-open-lab-research": "本科生开放性课题项目如何发布和申报",
    "henu-2026-single-scholarship": "本科生单项奖学金评选范围是什么",
    "henu-2027-outstanding-thesis": "毕业论文综合成绩如何核算",
    "henu-2026-national-project-review": "大创国家级项目推荐和学校复评流程是什么",
    "henu-2026-party-probation-conversion": "预备党员书面转正申请的程序是什么",
    "henu-2015-summary-activist": "入党积极分子思想汇报内容包括什么",
    "henu-2024-civilized-student": "文明学生评选对象是什么",
}


def evaluate() -> dict:
    old = {key: os.environ.pop(key, None) for key in ("RAG_LOCAL_VECTOR_INDEX", "RAG_LOCAL_RERANK_MODEL", "RAG_PUBLIC_DB_ENABLED")}
    try:
        sources = {s["id"]: s for s in public_sources() if s["kind"] == "official"}
        searcher = PublicKnowledgeRetriever(object())
        failures = []
        total = 0
        for source_id, question in QUESTIONS.items():
            source = sources[source_id]
            filters = {key: values[0] for key, values in source.get("restrictions", {}).items()}
            scopes = [
                ("matched", source["school"], source["application_year"], True),
                ("missing_school", "", source["application_year"], False),
                ("wrong_school", "测试用不相干大学", source["application_year"], False),
                ("missing_year", source["school"], None, False),
                ("wrong_year", source["school"], source["application_year"] + 1, False),
            ]
            for label, school, year, expected in scopes:
                result = searcher.search(source["skill_id"], question, school, year, top_k=6,
                                         variant=source.get("variant", ""), filters=filters)
                found = source_id in {item["source_id"] for item in result.get("results", [])}
                total += 1
                if found != expected:
                    failures.append({"source_id": source_id, "question": question, "probe": label,
                                     "expected": expected, "found": found})
        # The only uncovered track must explicitly abstain from official claims.
        for question in ("院级科研项目申请条件", "院级科研申报资格", "院级科研评审标准", "院级项目名额限制", "院级科研报名截止时间"):
            result = searcher.search("college-research", question, "测试用不相干大学", 2026)
            total += 1
            if result.get("official_evidence_found") or result.get("results"):
                failures.append({"source_id": None, "question": question, "probe": "uncovered_abstention"})
        return {"label": "source-linked agent-curated questions; scope probes synthetic; not human-approved gold",
                "skills": len(QUESTIONS) + 1, "total": total,
                "accuracy": round((total-len(failures))/total, 4), "failures": failures}
    finally:
        for key, value in old.items():
            if value is not None:
                os.environ[key] = value


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not report["failures"] else 1)
