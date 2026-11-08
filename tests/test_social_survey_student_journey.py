"""Simulated-model student journey for a social-survey practice application."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from utils.dispatcher import Dispatcher


USER = "我们准备三下乡社会调查，主题是社区垃圾分类。还未实地走访，也没有调查数据，请帮我写调研背景、调研方法和安全保障草稿。"
FAKE_REPLY = """好的，下面是可编辑的初步草稿。

### 调研背景
本次社会调查拟围绕社区垃圾分类工作展开，了解居民在日常分类中遇到的问题及其对宣传方式的需求，具体情况待实地调查确认。

### 调研方法
团队计划结合访谈与问卷收集居民意见，在取得知情同意后进行资料整理，问卷内容和样本安排有待进一步设计。

### 安全保障
团队将在出发前核对人员分工，提前了解当地天气和交通情况，建立紧急联系机制，具体安排根据实际行程补充。

请确认是否需要调整。
"""


@pytest.mark.parametrize("stream", [False, True])
def test_unprovided_bare_table_count_is_flagged_in_chat(tmp_path, monkeypatch, stream):
    store = Store(tmp_path)
    pid = store.create_project()["id"]
    store.update_project(pid, state={"skill_id": "social-survey", "skill_category": "practice"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    reply = "<WritingBlock>## 调研方法\n\n| 样本量 | 100 |\n</WritingBlock>"
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_a: None)
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: {"message": {"content": reply}})
    monkeypatch.setattr(agent, "_stream_post", lambda *_a, **_kw: iter([
        {"type": "final", "message": {"content": reply}, "usage": None}]))
    result = list(agent.chat_stream(pid, USER))[-1] if stream else agent.chat(pid, USER)
    assert result["message"].startswith("这版含需要核对的项目内容")
    assert "调查样本数量" in result["message"]


def test_unprovided_bare_table_count_does_not_replace_saved_section(tmp_path, monkeypatch):
    from proposal.workflow import AgenticWorkflowEngine
    store = Store(tmp_path)
    pid = store.create_project()["id"]
    store.update_project(pid, state={"skill_id": "social-survey", "outline_confirmed": True},
                         outline=[{"id": "survey", "title": "调查方案"}],
                         sections={"survey": "学生原有的调查方案"})
    store.add_message(pid, "user", USER)
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    class ModelSaysPassed:
        content = "| 样本量 | 100 |"
        def model_dump(self):
            return {"content": self.content, "status": "passed", "review_card": {"review_status": "completed"}}
    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow", lambda *_a, **_kw: ModelSaysPassed())
    result = agent.generate_section(pid, "survey")
    assert result["review_incomplete"] and "调查样本数量" in result["grounding_issues"]
    assert store.get_project(pid)["sections"]["survey"] == "学生原有的调查方案"


@pytest.fixture
def social_client(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_args, **_kwargs: (None, ""))
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools)
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_args: None)
    calls = []
    def simulated_model(_endpoint, _payload, **_kwargs):
        calls.append(_payload)
        return {"message": {"role": "assistant", "content": FAKE_REPLY}}
    monkeypatch.setattr(agent, "_post", simulated_model)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "dispatcher", Dispatcher(intent_decider=False, semantic_scorer=lambda _: {}))
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    with TestClient(app.app) as client:
        project_id = client.post("/api/projects/conversation").json()["id"]
        yield client, store, project_id, calls


def test_social_survey_routes_collects_material_and_recovers_draft(social_client):
    client, store, pid, calls = social_client
    uploaded = client.post(f"/api/projects/{pid}/documents?kind=source", files={
        "files": ("活动想法.txt", "活动主题：社区垃圾分类\n实施计划：尚待讨论".encode(), "text/plain"),
    })
    assert uploaded.status_code == 200
    doc = uploaded.json()["documents"][0]["document"]
    assert client.patch(f"/api/documents/{doc['id']}/confirm", json={"confirmed": True}).status_code == 200
    chat = client.post(f"/api/projects/{pid}/chat", json={"message": USER})
    assert chat.status_code == 200
    assert store.get_project(pid)["state"]["skill_id"] == "social-survey"
    assert len(calls) == 1
    assert "调研背景" in chat.json()["message"] and "有待" in chat.json()["message"]
    outline = client.get(f"/api/projects/{pid}/outline/recommend")
    assert outline.status_code == 200
    titles = [entry["title"] for entry in outline.json()["outline"]]
    assert any("调研" in title for title in titles) and not any("商业模式" in title for title in titles)
    assert not store.get_project(pid)["sections"]
    url = f"/api/projects/{pid}/chat-drafts"
    preview = client.get(url).json()
    assert {item["title"] for item in preview["items"]} == {"调研背景", "调研方法", "安全保障"}
    assert all("请确认是否" not in item["content"] for item in preview["items"])
    saved = client.post(url + "/confirm", json={"snapshot": preview["snapshot"],
        "items": [{"id": item["id"]} for item in preview["items"]]})
    assert saved.status_code == 200, saved.text
    response = client.post(f"/api/projects/{pid}/export")
    assert response.status_code == 200, response.text
    content = client.get(response.json()["download_url"]).content
    text = "\n".join(p.text for p in Document(io.BytesIO(content)).paragraphs)
    assert "垃圾分类" in text and "紧急联系" in text
    assert "请确认是否" not in text
    assert not response.json()["validation"]["passed"]


@pytest.mark.parametrize("stream", [False, True])
def test_real_survey_model_claims_require_explicit_student_review(tmp_path, monkeypatch, stream):
    import json
    from pathlib import Path
    from proposal.chat_drafts import candidates
    from proposal.chat_safety import PROJECT_CLAIM_REVIEW_PREFIX

    case = json.loads((Path(__file__).parent / "fixtures/social_survey_model_regression.json").read_text())
    store = Store(tmp_path)
    pid = store.create_project()["id"]
    store.update_project(pid, state={"skill_id": "social-survey", "skill_category": "practice"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_a: None)
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: {"message": {"content": case["assistant"]}})
    def response(_payload):
        yield {"type": "delta", "text": "模型临时片段"}
        yield {"type": "final", "message": {"content": case["assistant"]}, "usage": None}
    monkeypatch.setattr(agent, "_stream_post", response)
    if stream:
        events = list(agent.chat_stream(pid, case["user"]))
        result = events[-1]
        assert [event["text"] for event in events if event["type"] == "delta"] == [result["message"]]
    else:
        result = agent.chat(pid, case["user"])
    assert result["message"].startswith(PROJECT_CLAIM_REVIEW_PREFIX)
    assert all(label in result["message"] for label in ("调研覆盖范围", "问卷数量", "访谈数量", "宣讲场次"))
    review = candidates(store.get_project(pid), store.messages(pid))
    assert {item["title"] for item in review} == {"调研背景", "实施方案"}
    assert all(item["requires_review"] for item in review)
