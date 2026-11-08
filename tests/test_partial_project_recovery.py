"""Keep completed chapters when an upstream stream fails mid-document."""
import io
import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import ModelUnavailable, OllamaAgent
from proposal.chat_drafts import candidates
from proposal.storage import Store
from proposal.tools import ProposalTools


REQUEST = "我们的校园闲置交换项目尚未开发，请帮我写项目简介和商业模式草稿。"


def setup_agent(tmp_path, monkeypatch, content):
    store = Store(tmp_path)
    pid = store.create_project(title="校园交换")["id"]
    store.update_project(pid, state={"skill_id": "internet-plus", "skill_category": "competition"})
    agent = OllamaAgent(store, ProposalTools(store))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    calls = []
    def interrupted(_payload):
        calls.append(1)
        for part in content:
            yield {"type": "delta", "text": part}
        raise ModelUnavailable("测试中断")
    monkeypatch.setattr(agent, "_stream_post", interrupted)
    return store, pid, agent, calls


def test_complete_chapter_can_be_reviewed_and_exported_after_stream_interrupt(tmp_path, monkeypatch):
    store, pid, agent, calls = setup_agent(tmp_path, monkeypatch, [
        '<WritingBlock>## 项目简介\n\n项目拟服务校园闲置交换，市场规模为5000亿元。</WritingBlock>',
        '<WritingBlock>## 商业模式\n\n尚未完成的内容',
    ])
    events = list(agent.chat_stream(pid, REQUEST))
    final = events[-1]
    assert final["type"] == "done" and final["incomplete"] is True
    assert "生成中断" in final["message"] and "市场数据" in final["message"]
    assert "尚未完成的内容" not in final["message"] and calls == [1]
    assert [event["text"] for event in events if event["type"] == "delta"] == [final["message"]]
    found = candidates(store.get_project(pid), store.messages(pid))
    assert len(found) == 1 and found[0]["requires_review"] and found[0]["title"] == "项目简介"

    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    with TestClient(app.app) as client:
        path = f"/api/projects/{pid}/chat-drafts"
        preview = client.get(path).json()
        saved = client.post(path + "/confirm", json={"snapshot": preview["snapshot"], "items": [{
            "id": preview["items"][0]["id"], "content": "项目拟服务校园闲置交换，市场情况待调研。",
        }]})
        assert saved.status_code == 200, saved.text
        exported = client.post(f"/api/projects/{pid}/export").json()
        content = client.get(exported["download_url"]).content
    doc = "\n".join(item.text for item in Document(io.BytesIO(content)).paragraphs)
    assert "校园闲置交换" in doc and "5000亿元" not in doc


def test_completed_peer_chapter_in_unclosed_block_is_recovered_but_tail_is_not(tmp_path, monkeypatch):
    store, pid, agent, calls = setup_agent(tmp_path, monkeypatch, [
        '<WritingBlock>\n## 项目简介\n\n该项目拟为校园师生提供闲置物品信息交换服务，'
        '实际使用需求和具体实施细节仍需后续调查确认。\n\n## 商业模式\n\n后续内容尚未写完',
    ])
    final = list(agent.chat_stream(pid, REQUEST))[-1]
    assert final["incomplete"] and "项目简介" in final["message"]
    assert "后续内容尚未写完" not in final["message"] and calls == [1]
    found = candidates(store.get_project(pid), store.messages(pid))
    assert len(found) == 1 and found[0]["title"] == "项目简介"
    assert "实际使用需求" in found[0]["content"] and found[0]["requires_review"]


@pytest.mark.parametrize("partial", [
    '<WritingBlock>## 项目简介\n\n尚未结束',
    '<WritingBlock>## 项目简介\n\n此段虽有句号，但没有下一个章节边界，不能视作完整章节。',
    '<WritingBlock>正文缺少章节标题</WritingBlock>',
    '这是示例：<WritingBlock>## 项目简介\n\n示例项目正文。</WritingBlock>',
    '仅有普通未完成的输出',
])
def test_no_complete_chapter_never_claims_recovery(tmp_path, monkeypatch, partial):
    store, pid, agent, calls = setup_agent(tmp_path, monkeypatch, [partial])
    with pytest.raises(ModelUnavailable):
        list(agent.chat_stream(pid, REQUEST))
    assert [item["role"] for item in store.messages(pid)] == ["user"]
    assert calls == [1]
