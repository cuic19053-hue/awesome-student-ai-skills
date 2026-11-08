"""Student-provided facts and plans must reach the actual chapter writer."""
import json

import pytest

from server.proposal.agent import OllamaAgent
from server.proposal.storage import Store
from server.proposal.tools import ProposalTools
from server.proposal.workflow import AgenticWorkflowEngine, REVIEW_WEIGHTS


@pytest.mark.parametrize("skill_id", ["innovation-research", "challenge-cup", "internet-plus", "social-survey"])
def test_legacy_section_generation_includes_student_facts_plans_and_track_guidance(tmp_path, monkeypatch, skill_id):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "false")
    store = Store(tmp_path)
    project = store.create_project("社区共享工具", "校级", "社会学", "测试大学")
    store.update_project(project["id"],
        state={"skill_id": skill_id, "outline_confirmed": True,
               "project_name": "社区共享工具", "method": "拟开展半结构访谈",
               "goal": "了解社区居民借用需求", "team": "两名学生组成团队",
               "confirmed_facts": {"foundation": "已经整理需求访谈提纲"}},
        outline=[{"id": "method", "title": "研究方法"}])
    tools = ProposalTools(store)
    monkeypatch.setattr(tools, "search_project_materials", lambda *_a, **_k: {"results": []})
    monkeypatch.setattr(tools, "search_public_knowledge", lambda *_a, **_k: {"results": []})
    agent = OllamaAgent(store, tools)
    messages = []
    review = {"overall_score": 85.0, "passed": True,
              "dimensions": [{"name": n, "score": 85.0, "weight": w, "comment": "检查"}
                             for n, w in REVIEW_WEIGHTS.items()],
              "strengths": [], "weaknesses": [], "actionable_revisions": [],
              "user_action_required": [], "blocking_issues": []}

    def post(_path, payload, **_kwargs):
        messages.append(payload["messages"])
        return {"message": {"content": "围绕居民借用需求，拟开展半结构访谈。" if len(messages) == 1 else json.dumps(review)}}

    monkeypatch.setattr(agent, "_post", post)
    result = agent.generate_section(project["id"], "method", persist=False)
    draft_prompt = messages[0][-1]["content"]
    assert "两名学生组成团队" in draft_prompt
    assert "已经整理需求访谈提纲" in draft_prompt
    assert "拟开展半结构访谈" in draft_prompt
    assert "了解社区居民借用需求" in draft_prompt
    assert draft_prompt.index("两名学生组成团队") < draft_prompt.index("研究计划与待验证假设")
    assert draft_prompt.index("拟开展半结构访谈") > draft_prompt.index("研究计划与待验证假设")
    assert "正文质量要求" in draft_prompt
    assert result["content"] == "围绕居民借用需求，拟开展半结构访谈。"


def test_engine_without_blackboard_preserves_project_context():
    prompts = []
    review = {"overall_score": 85.0, "passed": True,
              "dimensions": [{"name": n, "score": 85.0, "weight": w, "comment": "检查"}
                             for n, w in REVIEW_WEIGHTS.items()],
              "strengths": [], "weaknesses": [], "actionable_revisions": [],
              "user_action_required": [], "blocking_issues": []}
    def caller(messages, _options):
        prompts.append(messages[-1]["content"])
        return "拟开展访谈。" if len(prompts) == 1 else json.dumps(review)

    AgenticWorkflowEngine(caller, max_retries=0).run_workflow(
        project_context={"project_name": "项目", "method": "拟开展访谈", "team": "两位同学"},
        section_id="method", section_title="研究方法", skill_guidance="", evidence_results=[])
    assert "拟开展访谈" in prompts[0]
    assert "两位同学" in prompts[0]
