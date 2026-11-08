"""Student-facing major-transfer conversation, revision and Word delivery."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.transfer_draft import is_transfer_draft_request, transfer_student_facts
from utils.dispatcher import Dispatcher


@pytest.fixture
def conversation(tmp_path, monkeypatch):
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
    monkeypatch.setattr(agent, "_post", lambda *_a, **_kw: pytest.fail("bounded draft must not call model"))
    with TestClient(app.app) as client:
        pid = client.post("/api/projects/conversation").json()["id"]
        yield client, store, pid


def test_explicit_request_creates_saves_and_exports_a_student_draft(conversation):
    client, store, pid = conversation
    response = client.post(f"/api/projects/{pid}/chat", json={"message":
        "我叫李明，现学汉语言文学，想转计算机专业，因为对编程很感兴趣。请写一份转专业申请书，我没有竞赛或科研经历，未说的内容不要编。",
        "llm_config": {"provider": "preset"}})
    assert response.status_code == 200
    text = response.json()["message"]
    assert store.get_project(pid)["state"]["skill_id"] == "major-transfer"
    assert all(v in text for v in ("李明", "汉语言文学", "计算机", "感兴趣", "待补充"))
    assert all(v not in text for v in ("计算机科学与技术", "大一", "第二学期", "联系电话"))
    assert response.json()["model"] == "evidence-only"
    assert store.get_workbench_credit_balance("local_user")["free_chat_count"] == 3
    url = f"/api/projects/{pid}/chat-drafts"
    preview = client.get(url).json()
    assert len(preview["items"]) == 1 and preview["items"][0]["title"] == "转专业申请书"
    saved = client.post(url + "/confirm", json={"snapshot": preview["snapshot"], "items": [{"id": preview["items"][0]["id"]}]})
    assert saved.status_code == 200
    exported = client.post(f"/api/projects/{pid}/export")
    assert exported.status_code == 200
    assert not exported.json()["validation"]["passed"]
    word = client.get(exported.json()["download_url"])
    text = "\n".join(p.text for p in Document(io.BytesIO(word.content)).paragraphs)
    assert all(v in text for v in ("李明", "汉语言文学", "计算机", "待补充"))
    assert "计算机科学与技术" not in text


def test_multi_turn_conflict_stays_blank_until_explicit_correction(conversation):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫李明，现学汉语言文学，想转计算机专业。")
    store.add_message(pid, "user", "我想转英语专业。")
    url = f"/api/projects/{pid}/chat"
    first = client.post(url, json={"message": "请帮我写转专业申请书。"})
    assert first.status_code == 200
    assert "目标专业待补充" in first.text and "部分信息有不同说法" in first.text
    assert "李明" in first.text and "汉语言文学" in first.text
    second = client.post(url, json={"message": "更正，目标专业改为英语专业，请重新写申请书。"})
    assert second.status_code == 200
    assert "转入英语专业" in second.text and "李明" in second.text
    assert "转入计算机专业" not in second.text


def test_specific_omission_and_general_opt_out_are_respected(conversation):
    client, store, pid = conversation
    store.add_message(pid, "user", "我叫李明，现学汉语言文学，想转计算机专业。")
    url = f"/api/projects/{pid}/chat"
    first = client.post(url, json={"message": "请写转专业申请书，不要写姓名。"})
    assert first.status_code == 200 and "李明" not in first.text and "汉语言文学" in first.text
    second = client.post(url, json={"message": "不要使用我的资料，请重新写申请书。"})
    assert second.status_code == 200
    assert all(value not in second.text for value in ("李明", "汉语言文学", "计算机"))


@pytest.mark.parametrize("text", ["不要写转专业申请书", "我不想写转专业申请书", "转专业申请书该怎么写？", "转专业需要什么条件？"])
def test_only_explicit_writing_requests_trigger_draft(text):
    assert not is_transfer_draft_request(text, {"state": {"skill_id": "major-transfer"}})


def test_project_context_is_not_a_source_and_conflicting_user_values_are_not_guessed():
    facts, conflict, _ = transfer_student_facts([{"role": "assistant", "content": "你是李明，转到计算机专业。"}], "请写申请书")
    assert not facts and not conflict
    facts, conflict, _ = transfer_student_facts([], "我现学英语专业，现学汉语言文学专业，请写申请书。")
    assert "原专业" not in facts and conflict


def test_negative_interest_is_not_rewritten_as_interest():
    facts, conflict, _ = transfer_student_facts([], "我叫李明，现学英语专业，对编程不感兴趣。")
    assert facts.get("姓名") == "李明" and not conflict
    assert "兴趣" not in facts


def test_unpunctuated_majors_do_not_merge_into_a_new_major():
    facts, conflict, _ = transfer_student_facts([], "我叫李明现学汉语言文学想转计算机专业，因为对编程很感兴趣。")
    assert not conflict
    assert facts["姓名"] == "李明" and facts["原专业"] == "汉语言文学" and facts["目标专业"] == "计算机"


@pytest.mark.parametrize("cloud", [False, True])
@pytest.mark.parametrize("stream", [False, True])
def test_preflight_matches_runtime_without_model_charge(conversation, monkeypatch, cloud, stream):
    import httpx

    client, store, pid = conversation
    if cloud:
        class Auth:
            async def get(self, *_args, **_kwargs):
                return httpx.Response(200, json={"id": "isolated-user", "created_at": "2026-01-01T00:00:00Z"})
        monkeypatch.setattr(app, "CLOUD_MODE", True)
        monkeypatch.setattr(app.app.state, "auth_http", Auth())
        client.headers["Authorization"] = "Bearer isolated-token"
    response = client.post(f"/api/projects/{pid}/chat", json={
        "message": "我叫李明，现学英语专业，想转计算机专业。请写转专业申请书。",
        "stream": stream, "llm_config": {"provider": "preset"},
    })
    assert response.status_code == 200 and "李明" in response.text and "<WritingBlock" in response.text
    assert "evidence-only" in response.text and '"free_chat":false' in response.text.replace(" ", "")
    user_id = "isolated-user" if cloud else "local_user"
    assert store.get_workbench_credit_balance(user_id)["free_chat_count"] == 3


def test_explanatory_request_remains_model_dependent(conversation, monkeypatch):
    client, store, pid = conversation
    store.update_project(pid, state={"skill_id": "major-transfer"})
    invocations = []
    monkeypatch.setattr(app, "_metered_invoke", lambda *args: invocations.append(True) or {"message": "解释写法。"})
    response = client.post(f"/api/projects/{pid}/chat", json={"message": "转专业申请书该怎么写？"})
    assert response.status_code == 200 and invocations == [True]
