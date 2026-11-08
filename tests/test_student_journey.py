"""Student-facing local journey using a real upload and real Word output."""
import io

from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from utils.dispatcher import Dispatcher


def test_student_can_revise_a_grounded_scholarship_draft_and_export(tmp_path, monkeypatch):
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "retriever", retriever)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    monkeypatch.setattr(app, "dispatcher", Dispatcher(intent_decider=False, semantic_scorer=lambda _: {}))
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(agent, "_post", lambda *_: (_ for _ in ()).throw(AssertionError("unexpected model call")))
    with TestClient(app.app) as client:
        project_id = client.post("/api/projects/conversation").json()["id"]
        chat_url = f"/api/projects/{project_id}/chat"
        response = client.post(chat_url, json={"message": "我想申请国家奖学金，我叫李明，学计算机专业，绩点3.8，专业排名3/80，应该怎么准备？"})
        assert response.status_code == 200 and "准备" in response.json()["message"]

        source = "姓名：李明\n学院：信息学院\n获奖：数学建模二等奖".encode("gbk")
        upload = client.post(f"/api/projects/{project_id}/documents?kind=source", files={
            "files": ("材料.txt", source, "text/plain"),
        })
        assert upload.status_code == 200
        document_id = upload.json()["documents"][0]["document"]["id"]
        assert client.patch(f"/api/documents/{document_id}/confirm", json={"confirmed": True}).status_code == 200

        response = client.post(chat_url, json={"message": "请帮我写国家奖学金申请书，我没有科研经历。"})
        assert response.status_code == 200
        assert all(value in response.json()["message"] for value in ("李明", "信息学院", "数学建模二等奖", "暂无科研经历", "3.8"))
        draft_url = f"/api/projects/{project_id}/chat-drafts"
        preview = client.get(draft_url).json()
        old = preview["items"][0]
        assert client.post(draft_url + "/confirm", json={"snapshot": preview["snapshot"], "items": [{"id": old["id"]}]}).status_code == 200

        response = client.post(chat_url, json={"message": "更正，我的绩点改为3.7。请重新写国家奖学金申请书。"})
        assert response.status_code == 200
        assert all(value in response.json()["message"] for value in ("李明", "3.7", "数学建模二等奖"))
        assert "【政策资料核查】" not in response.json()["message"]
        preview = client.get(draft_url).json()
        assert client.post(draft_url + "/confirm", json={"snapshot": preview["snapshot"], "items": [
            {"id": preview["items"][0]["id"], "replace_existing": True},
        ]}).status_code == 200
        versions = client.get(f"/api/projects/{project_id}/sections/{old['section_id']}/versions").json()["versions"]
        assert any("3.8" in version["content"] for version in versions)

        exported = client.post(f"/api/projects/{project_id}/export")
        assert exported.status_code == 200
        assert exported.json()["validation"]["passed"] is False  # Other fields still need input.
        word = client.get(exported.json()["download_url"])
        assert word.status_code == 200
        content = "\n".join(p.text for p in Document(io.BytesIO(word.content)).paragraphs)
        assert "3.7" in content and "数学建模二等奖" in content and "新对话" not in content
