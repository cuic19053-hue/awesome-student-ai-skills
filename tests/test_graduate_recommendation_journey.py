"""Graduate recommendation journey with a simulated model and real files."""
import copy
import io
import json

from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from utils.dispatcher import Dispatcher


def test_graduate_personal_draft_uses_applicable_sources_and_exports(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_: (None, ""))
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "dispatcher", Dispatcher(intent_decider=False, semantic_scorer=lambda _: {}))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    requests = []
    answers = iter([
        {"tool_calls": [{"id": "evidence", "function": {"name": "search_project_materials",
            "arguments": {"query": "个人基本情况"}}}]},
        {"content": '<WritingBlock variant="document">\n## 个人陈述\n\n'
                    '我叫李明，学习计算机专业，绩点为3.8，计划申请保研。'
                    '我的科研经历和申请目标仍需补充。\n</WritingBlock>'},
    ])

    def simulated_model(_endpoint, payload):
        requests.append(copy.deepcopy(payload))
        return {"message": next(answers)}

    monkeypatch.setattr(agent, "_post", simulated_model)
    with TestClient(app.app) as client:
        pid = client.post("/api/projects/conversation").json()["id"]
        for filename, kind, text in [
            ("李明资料.txt", "source", "姓名：李明\n个人基本情况：计算机专业，绩点3.8。"),
            ("王五资料.txt", "source", "姓名：王五\n个人基本情况：研究助理，绩点4.5。"),
            ("学校通知.txt", "official", "个人基本情况要求：填写本人专业。"),
        ]:
            response = client.post(f"/api/projects/{pid}/documents?kind={kind}", files={
                "files": (filename, text.encode(), "text/plain"),
            })
            assert response.status_code == 200
            doc_id = response.json()["documents"][0]["document"]["id"]
            assert client.patch(f"/api/documents/{doc_id}/confirm", json={"confirmed": True}).status_code == 200
        response = client.post(f"/api/projects/{pid}/chat", json={"message": (
            "我叫李明，计算机专业，绩点3.8。我想申请保研，请根据材料写一份个人陈述。"
        )})
        assert response.status_code == 200, response.text
        assert store.get_project(pid)["state"]["skill_id"] == "graduate-recommendation"
        assert response.json()["tool_calls"] == ["search_project_materials"]
        initial_context = requests[0]["messages"][0]["content"]
        assert "李明资料.txt" in initial_context and "学校通知.txt" in initial_context
        assert "王五资料.txt" not in initial_context
        evidence = json.loads(next(item["content"] for item in requests[1]["messages"] if item.get("role") == "tool"))
        assert {item["source_name"] for item in evidence["results"]} == {"李明资料.txt", "学校通知.txt"}
        url = f"/api/projects/{pid}/chat-drafts"
        review = client.get(url).json()
        assert len(review["items"]) == 1 and review["items"][0]["title"] == "个人陈述"
        assert client.post(url + "/confirm", json={"snapshot": review["snapshot"], "items": [
            {"id": review["items"][0]["id"]},
        ]}).status_code == 200
        exported = client.post(f"/api/projects/{pid}/export")
        assert exported.status_code == 200
        result = client.get(exported.json()["download_url"])
        output = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(result.content)).paragraphs)
        assert "李明" in output and "3.8" in output and "王五" not in output and "4.5" not in output
