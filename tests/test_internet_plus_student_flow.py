"""Isolated internet-plus student flow with a controlled model response.

These checks exercise API routing, uploaded material, structure and Word
delivery.  The model response is deliberately mocked, not an LLM quality test.
"""
import io

from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.workflow import AgenticWorkflowEngine
from utils.dispatcher import Dispatcher


def test_confirmed_track_material_and_controlled_section_reach_word(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_a, **_kw: (None, ""))
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "dispatcher", Dispatcher(intent_decider=False, semantic_scorer=lambda _: {}))
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "_metered_invoke", lambda _cfg, _request, _action, _pid, fn: fn(agent))
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: {"message": {"content": "我会先依据你的项目材料整理。"}})
    monkeypatch.setattr(tools, "search_public_knowledge", lambda *_a, **_kw: {"results": []})

    observed = []
    class ControlledResult:
        content = "项目针对人工灌溉耗时的问题，计划探索土壤湿度监测与灌溉提示。"
        def model_dump(self):
            return {"content": self.content, "status": "passed", "review_card": {"review_status": "completed"}}
    def controlled_workflow(_self, **kwargs):
        observed.append(kwargs)
        return ControlledResult()
    monkeypatch.setattr(AgenticWorkflowEngine, "run_workflow", controlled_workflow)

    with TestClient(app.app) as client:
        pid = client.post("/api/projects/conversation").json()["id"]
        chat = client.post(f"/api/projects/{pid}/chat", json={"message":
            "我们要申报中国国际大学生创新大赛高教主赛道，项目是智灌助手，请帮我准备商业计划书。",
            "llm_config": {"provider": "ollama"}})
        assert chat.status_code == 200, chat.text
        assert store.get_project(pid)["state"]["skill_id"] == "internet-plus"
        source = "项目名称：智灌助手\n实际问题：农田人工灌溉耗时\n计划方案：土壤湿度监测与灌溉提示".encode()
        upload = client.post(f"/api/projects/{pid}/documents?kind=source", files={
            "files": ("项目现状.txt", source, "text/plain"),
        })
        assert upload.status_code == 200, upload.text
        document = upload.json()["documents"][0]["document"]
        assert client.patch(f"/api/documents/{document['id']}/confirm", json={"confirmed": True}).status_code == 200
        proposed = client.get(f"/api/projects/{pid}/outline/recommend")
        assert proposed.status_code == 200
        outline = proposed.json()["outline"]
        assert any(item["id"] == "problem" for item in outline)
        assert any("商业模式" in item["title"] for item in outline)
        assert client.put(f"/api/projects/{pid}/outline", json={"outline": outline}).status_code == 200
        generated = client.post(f"/api/projects/{pid}/sections/problem/generate", json={"llm_config": {"provider": "ollama"}})
        assert generated.status_code == 200, generated.text
        assert observed and "互联网+" in observed[0]["skill_guidance"]
        assert any("灌溉" in str(item) for item in observed[0]["evidence_results"])
        assert store.get_project(pid)["sections"]["problem"] == ControlledResult.content
        exported = client.post(f"/api/projects/{pid}/export")
        assert exported.status_code == 200, exported.text
        word = client.get(exported.json()["download_url"])
        assert word.status_code == 200
        text = "\n".join(p.text for p in Document(io.BytesIO(word.content)).paragraphs)
        assert "灌溉" in text and "土壤湿度" in text
        assert not exported.json()["validation"]["passed"]  # Other sections remain blank.
