"""Real model regression: unsupported business figures need a student's review."""
from pathlib import Path

import pytest
import server.app  # Register the server module path.
from proposal.agent import OllamaAgent
from proposal.chat_drafts import candidates
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.workflow import AgenticWorkflowEngine


MODEL_RESPONSE = (Path(__file__).parent / "fixtures/internet_plus_model_regression.txt").read_text()
REQUEST = ("我们的项目智灌助手拟为农户提供灌溉建议，团队三位同学；尚未开展市场调查、没有营业收入，"
           "也没有申请专利。请直接写商业计划书中的项目简介，不要编造数据。")


@pytest.mark.parametrize("stream", [False, True])
def test_actual_invented_model_response_is_buffered_and_requires_explicit_review(tmp_path, monkeypatch, stream):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "internet-plus", "skill_category": "competition"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_a: None)
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: {"message": {"content": MODEL_RESPONSE}})
    def reply(_payload):
        yield {"type": "delta", "text": "市场规模为5000亿元。"}
        yield {"type": "final", "message": {"content": MODEL_RESPONSE}, "usage": None}
    monkeypatch.setattr(agent, "_stream_post", reply)
    if stream:
        events = list(agent.chat_stream(project_id, REQUEST))
        result = events[-1]
        assert [event["text"] for event in events if event["type"] == "delta"] == [result["message"]]
    else:
        result = agent.chat(project_id, REQUEST)
    assert result["message"].startswith("这版含需要核对的项目内容")
    assert all(label in result["message"] for label in ("市场数据", "价格", "融资与股权"))
    # The student can edit the generated response without repeating a paid
    # model call, but the candidate is not automatically selected for saving.
    items = candidates(store.get_project(project_id), store.messages(project_id))
    assert len(items) == 1 and items[0]["requires_review"]
    assert "5000 亿元" in items[0]["content"]


@pytest.mark.parametrize("persist", [False, True])
def test_project_section_cannot_overwrite_existing_text_with_unsupported_figures(tmp_path, monkeypatch, persist):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "internet-plus", "outline_confirmed": True},
                         outline=[{"id": "market", "title": "市场分析"}],
                         sections={"market": "学生已有的市场分析"})
    store.add_message(project_id, "user", REQUEST)
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))

    class ModelSaysPassed:
        content = "目前尚未调研。市场规模为5000亿元，定价每年50元，计划融资50万元。"
        def model_dump(self):
            return {"content": self.content, "status": "passed", "review_card": {"review_status": "completed"}}

    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow", lambda *_a, **_kw: ModelSaysPassed())
    result = agent.generate_section(project_id, "market", persist=persist)
    assert result["review_incomplete"] and result["grounding_kind"] == "project"
    assert "项目数据" in result["notice"]
    assert store.get_project(project_id)["sections"]["market"] == "学生已有的市场分析"
    versions = store.list_section_versions(project_id, "market")
    assert bool(versions) is persist
    if persist:
        assert versions[0]["source"] == "ai_generated_alternative"


def test_unprovided_school_roles_and_development_are_exposed_for_review(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "internet-plus", "skill_category": "competition"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_a: None)
    output = ('<WritingBlock variant="document">\n## 项目简介\n\n'
              '我们团队开发了智灌助手项目。项目团队由三位同学组成，均来自XX大学，'
              '分别负责硬件设计、软件开发和市场推广。\n</WritingBlock>')
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: {"message": {"content": output}})
    response = agent.chat(project_id, REQUEST)["message"]
    assert response.startswith("这版含需要核对的项目内容")
    assert all(label in response for label in ("团队学校", "团队分工", "开发状态"))
    item = candidates(store.get_project(project_id), store.messages(project_id))[0]
    assert item["requires_review"] and "团队学校" in item["warnings"][0]


@pytest.mark.parametrize("stream", [False, True])
def test_real_model_unspecified_plans_are_flagged_without_changing_the_text(tmp_path, monkeypatch, stream):
    store = Store(tmp_path)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "internet-plus", "skill_category": "competition"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_a: None)
    output = (Path(__file__).parent / "fixtures/internet_plus_quality_retest.txt").read_text().strip()
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: {"message": {"content": output}})
    def reply(_payload):
        yield {"type": "final", "message": {"content": output}, "usage": None}
    monkeypatch.setattr(agent, "_stream_post", reply)
    request = ("我们准备参加创新大赛高教主赛道，项目是校园闲置物品交换平台，计划为大学生提供信息发布与匹配服务。"
               "尚未开发、尚无收入，也没有市场调研或融资。请直接写商业计划书的项目简介和商业模式，不要编造数据。")
    response = list(agent.chat_stream(project_id, request))[-1]["message"] if stream else agent.chat(project_id, request)["message"]
    assert response.startswith("这版含需要核对的项目内容")
    assert all(label in response for label in ("定位方案", "收费方案", "合作安排", "安全效果"))
    assert response.endswith(output)
    items = candidates(store.get_project(project_id), store.messages(project_id))
    assert items and all(item["requires_review"] for item in items)
