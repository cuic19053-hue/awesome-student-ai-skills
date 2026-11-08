"""Writing requests must not be swallowed by the policy-only shortcut."""
import pytest

import server.app  # Adds server to the module path.
from proposal.knowledge import is_policy_question


@pytest.mark.parametrize("query", [
    "请根据这些评审标准帮我设计申请书大纲",
    "请根据申报条件帮我润色下面这段正文",
    "我想写申请书，报名截止时间我稍后会补充",
    "根据我提供的评审标准起草申请书",
    "评审标准这一章节怎么写",
    "请帮我写一份奖学金申请材料",
    "我要申请国家奖学金，请帮我列一个准备材料的步骤。",
    "更正，我的绩点改为3.7。请重新写国家奖学金申请书。",
    "我的专业排名是3/80，请重新写国家奖学金申请书。",
    "我的绩点为3.7，请直接写国家奖学金申请书。",
])
def test_writing_intent_does_not_become_policy_question(query):
    assert not is_policy_question(query)


@pytest.mark.parametrize("query", [
    "学校的申报条件是什么？",
    "国家奖学金金额是多少？",
    "报名截止时间是什么时候？",
    "我符不符合申请条件？请帮我写申请书",
    "请先告诉我申报条件有哪些，再帮我写申请书",
    "请查一下官方评审标准并设计大纲",
    "请帮我写申请书，同时确认截止时间是几号？",
    "奖学金排名要求多少？帮我起草申请材料",
    "帮我查询学校的评选标准并写一份申请书",
    "请帮我写申请书，今年国家奖学金多少钱？",
    "我能拿多少奖学金？请帮我写申请书",
    "我能申请国家奖学金吗？帮我起草材料",
    "专业前多少名可以申请？帮我写申请书",
    "申请要求绩点多少？帮我写申请书",
    "学校奖学金申请需要哪些材料？",
    "绩点多少可以申请国家奖学金？请重新写国家奖学金申请书。",
    "重新写国家奖学金申请书，同时查询绩点要求是多少。",
])
def test_factual_policy_questions_keep_the_evidence_only_path(query):
    assert is_policy_question(query)


@pytest.mark.parametrize("stream", [False, True])
def test_writing_request_reaches_real_chat_runtime(tmp_path, monkeypatch, stream):
    import server.app as app
    from fastapi.testclient import TestClient
    from proposal.agent import OllamaAgent
    from proposal.retrieval import ProjectRetriever
    from proposal.storage import Store
    from proposal.tools import ProposalTools

    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools)
    requests = []
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", agent)
    if stream:
        def stream_reply(payload):
            requests.append(payload)
            yield {"type": "delta", "text": "这是申请书大纲。"}
            yield {"type": "final", "message": {"content": "这是申请书大纲。"}, "usage": None}
        monkeypatch.setattr(agent, "_stream_post", stream_reply)
    else:
        def reply(_endpoint, payload):
            requests.append(payload)
            return {"message": {"content": "这是申请书大纲。"}}
        monkeypatch.setattr(agent, "_post", reply)
    project = store.create_project(title="意图路由测试")
    response = TestClient(app.app).post(
        f"/api/projects/{project['id']}/chat", json={
            "message": "请根据这些评审标准帮我设计申请书大纲", "stream": stream,
        },
    )
    assert response.status_code == 200
    assert len(requests) == 1
    assert "这是申请书大纲。" in response.text
