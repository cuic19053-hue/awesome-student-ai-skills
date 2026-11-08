"""Challenge Cup workbench path with a simulated model and real Word output."""
import io

from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.chat_drafts import candidates
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from utils.dispatcher import Dispatcher


def test_real_model_markdown_section_with_dividers_is_reviewable():
    """Regression reproduces the structure observed in a real local chat."""
    project = {"state": {"skill_id": "challenge-cup", "skill_category": "competition"},
               "outline": [], "sections": {}}
    messages = [
        {"role": "user", "content": "我要参加挑战杯科技发明制作，还没做实验。请直接写一小段研究方案，不要编造成果。"},
        {"role": "assistant", "content": (
            "下面根据你的设计构想起草一段研究方案：\n\n---\n\n### 研究方案\n\n"
            "本项目计划研究无人机火场监测，采用摄像头收集图像并研究火源识别。\n\n"
            "#### 1. 系统设计\n- 使用无人机拍摄火场图像，再传送到地面设备。\n\n"
            "#### 2. 实验验证\n- 拟进行模拟测试，测试条件和结果仍待补充。\n\n"
            "---\n\n请确认这段研究方案是否符合你的设计构想。"
        )},
    ]
    result = candidates(project, messages)
    assert len(result) == 1 and result[0]["title"] == "研究方案"
    assert "#### 1. 系统设计" in result[0]["content"]
    assert "请确认" not in result[0]["content"]
    assert not result[0]["content"].endswith("---")


def test_observed_plain_research_section_can_be_saved_and_exported(tmp_path, monkeypatch):
    """Replay the real model's response shape; this test does not call a model."""
    store = Store(tmp_path)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", ProposalTools(store))
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "challenge-cup", "skill_category": "competition"})
    store.add_message(project_id, "user", "请直接写一小段挑战杯研究方案，还没做实验。")
    store.add_message(project_id, "assistant", (
        "下面是研究方案：\n\n---\n\n### 研究方案\n\n"
        "本项目拟研究无人机火场监测，使用摄像头收集图像并进行火源识别。\n\n"
        "#### 1. 系统设计\n- 计划拍摄火场图像，并传送至地面设备。\n\n"
        "#### 2. 实验验证\n- 拟开展模拟测试，具体测试条件与结果尚待补充。\n\n"
        "---\n\n请确认这段研究方案是否符合你的设计构想。"
    ))
    with TestClient(app.app) as client:
        url = f"/api/projects/{project_id}/chat-drafts"
        review = client.get(url).json()
        assert len(review["items"]) == 1
        assert client.post(url + "/confirm", json={"snapshot": review["snapshot"], "items": [
            {"id": review["items"][0]["id"]},
        ]}).status_code == 200
        exported = client.post(f"/api/projects/{project_id}/export")
        assert exported.status_code == 200, exported.text
        downloaded = client.get(exported.json()["download_url"])
        text = "\n".join(p.text for p in Document(io.BytesIO(downloaded.content)).paragraphs)
        assert "无人机火场监测" in text and "测试条件与结果尚待补充" in text
        assert "请确认这段研究方案" not in text


def test_challenge_student_can_review_save_and_export_a_simulated_draft(tmp_path, monkeypatch):
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
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    monkeypatch.setattr(agent, "_post", lambda *_: {"message": {"content": (
        '<WritingBlock variant="document">\n## 研究方案\n\n'
        '计划使用无人机摄像头采集火场画面，研究识别和告警方案。'
        '目前尚未开展测试，测试条件与结果待补充。\n</WritingBlock>'
    )}})
    with TestClient(app.app) as client:
        project_id = client.post("/api/projects/conversation").json()["id"]
        text = "初步设想：无人机摄像头采集火场画面，用于研究识别与告警；目前尚未开展测试。".encode()
        uploaded = client.post(f"/api/projects/{project_id}/documents?kind=source", files={
            "files": ("作品初步设想.txt", text, "text/plain"),
        })
        assert uploaded.status_code == 200
        document_id = uploaded.json()["documents"][0]["document"]["id"]
        assert client.patch(f"/api/documents/{document_id}/confirm", json={"confirmed": True}).status_code == 200
        result = client.post(f"/api/projects/{project_id}/chat", json={"message": (
            "我参加挑战杯科技发明制作，作品是无人机火场监测系统，请根据资料起草研究方案。"
        )})
        assert result.status_code == 200, result.text
        assert store.get_project(project_id)["state"]["skill_id"] == "challenge-cup"
        assert "尚未开展测试" in result.json()["message"]
        url = f"/api/projects/{project_id}/chat-drafts"
        review = client.get(url).json()
        assert len(review["items"]) == 1 and review["items"][0]["title"] == "研究方案"
        saved = client.post(url + "/confirm", json={"snapshot": review["snapshot"], "items": [
            {"id": review["items"][0]["id"]},
        ]})
        assert saved.status_code == 200
        exported = client.post(f"/api/projects/{project_id}/export")
        assert exported.status_code == 200, exported.text
        word = client.get(exported.json()["download_url"])
        assert word.status_code == 200
        result_text = "\n".join(item.text for item in Document(io.BytesIO(word.content)).paragraphs)
        assert "无人机摄像头" in result_text and "尚未开展测试" in result_text
