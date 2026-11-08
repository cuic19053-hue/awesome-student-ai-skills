"""Bounded national motivation scholarship drafts use only student input."""
import sys
import io
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from proposal.motivation_draft import is_motivation_draft_request, motivation_placeholder_draft, motivation_student_facts


def _letter(history, message):
    facts, conflicted, omitted = motivation_student_facts(history, message, [], project_id="isolated-project")
    return motivation_placeholder_draft(facts, conflicted=conflicted, omitted=omitted)


def test_explicit_student_facts_are_not_expanded_or_treated_as_eligibility():
    draft = _letter([], "我叫王明，计算机专业，绩点3.8，排名3/80，家庭年收入2万元，"
                        "家庭困难认定还没有完成。请帮我写国家励志奖学金申请书。")
    assert all(v in draft for v in ("王明", "计算机", "3.8", "3/80", "2万元", "待补充"))
    assert all(v not in draft for v in ("计算机科学与技术", "加权平均分", "已通过", "认定已完成", "本人提供", "尚未核验"))
    assert "<WritingBlock" in draft


@pytest.mark.parametrize("text", ["不要写申请书。", "先别写国家励志奖学金申请书，请说说思路。",
                                  "励志奖学金申请书该怎么写？", "请润色申请书。"])
def test_nonwriting_requests_do_not_force_draft(text):
    assert not is_motivation_draft_request(text, {"state": {"skill_id": "motivation-scholarship"}})


def test_draft_intent_is_bound_to_selected_skill():
    assert is_motivation_draft_request("请写国家励志奖学金申请书", {"state": {"skill_id": "motivation-scholarship"}})
    assert not is_motivation_draft_request("请写国家励志奖学金申请书", {"state": {"skill_id": "grant-application"}})


def test_optouts_and_explicit_restore_do_not_drop_other_facts():
    history = [{"role": "user", "content": "我叫王明，计算机专业，绩点3.8，排名3/80，家庭年收入2万元。"},
               {"role": "user", "content": "不要写成绩，不要把我家的收入放进去。"}]
    hidden = _letter(history, "请重写申请书。")
    assert "王明" in hidden and "计算机" in hidden
    assert all(v not in hidden for v in ("3.8", "3/80", "2万元", "家庭年收入"))
    allowed = _letter(history, "现在可以写成绩和家庭收入，请重新写。")
    assert all(v in allowed for v in ("王明", "3.8", "3/80", "2万元"))


def test_conflicting_income_remains_blank_until_corrected():
    history = [{"role": "user", "content": "我叫王明，家庭年收入2万元。"},
               {"role": "user", "content": "我家年收入为3万元。"}]
    draft = _letter(history, "请写申请书。")
    assert "2万元" not in draft and "3万元" not in draft and "不同说法" in draft
    corrected = _letter(history, "更正，家庭年收入改为4万元，请重新写申请书。")
    assert "4万元" in corrected and "2万元" not in corrected and "3万元" not in corrected


def test_assistant_text_is_not_a_fact_source():
    draft = _letter([{"role": "assistant", "content": "你叫王明，获得校级一等奖。"}], "请写申请书。")
    assert "王明" not in draft and "一等奖" not in draft


@pytest.fixture
def conversation(tmp_path, monkeypatch):
    import server.app as app
    from fastapi.testclient import TestClient
    from proposal.agent import OllamaAgent
    from proposal.retrieval import ProjectRetriever
    from proposal.storage import Store
    from proposal.tools import ProposalTools
    from utils.dispatcher import Dispatcher
    store = Store(tmp_path)
    retriever = ProjectRetriever(store)
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_a, **_k: (None, ""))
    tools = ProposalTools(store, retriever)
    agent = OllamaAgent(store, tools)
    for name, value in {"store": store, "retriever": retriever, "tools": tools, "agent": agent,
                        "CLOUD_MODE": False, "dispatcher": Dispatcher(intent_decider=False, semantic_scorer=lambda _: {})}.items():
        monkeypatch.setattr(app, name, value)
    monkeypatch.setattr(agent, "_post", lambda *_a, **_k: pytest.fail("bounded draft must not call model"))
    monkeypatch.setattr(agent, "_stream_post", lambda *_a, **_k: pytest.fail("bounded draft must not call model"))
    with TestClient(app.app) as client:
        pid = client.post("/api/projects/conversation").json()["id"]
        yield client, store, pid


def test_real_student_journey_to_saved_word(conversation):
    from docx import Document
    client, store, pid = conversation
    response = client.post(f"/api/projects/{pid}/chat", json={"message":
        "我叫王明，计算机专业，绩点3.8，排名3/80，家庭年收入2万元，家庭困难认定还没有完成。"
        "请帮我写一份国家励志奖学金申请书，没有的经历不要编造。", "llm_config": {"provider": "preset"}})
    assert response.status_code == 200
    assert store.get_project(pid)["state"]["skill_id"] == "motivation-scholarship"
    assert response.json()["model"] == "evidence-only"
    assert all(v in response.text for v in ("王明", "计算机", "3.8", "3/80", "2万元", "待补充"))
    assert all(v not in response.text for v in ("计算机科学与技术", "加权平均分", "认定已完成"))
    url = f"/api/projects/{pid}/chat-drafts"
    draft = client.get(url).json()
    assert len(draft["items"]) == 1 and draft["items"][0]["title"] == "国家励志奖学金申请书"
    saved = client.post(url + "/confirm", json={"snapshot": draft["snapshot"],
                                                "items": [{"id": draft["items"][0]["id"]}]})
    assert saved.status_code == 200
    exported = client.post(f"/api/projects/{pid}/export")
    assert exported.status_code == 200 and not exported.json()["validation"]["passed"]
    word = client.get(exported.json()["download_url"])
    text = "\n".join(p.text for p in Document(io.BytesIO(word.content)).paragraphs)
    assert all(v in text for v in ("王明", "计算机", "3.8", "3/80", "2万元", "待补充"))
    assert "计算机科学与技术" not in text


def test_followup_income_preference_is_preserved_in_new_draft(conversation):
    client, store, pid = conversation
    url = f"/api/projects/{pid}/chat"
    first = client.post(url, json={"message": "我叫王明，计算机专业，家庭年收入2万元，请写国家励志奖学金申请书。"})
    assert first.status_code == 200 and "2万元" in first.text
    hidden = client.post(url, json={"message": "不要把我家的收入写进申请书，请重新写。"})
    assert hidden.status_code == 200
    assert all(value in hidden.text for value in ("王明", "计算机", "WritingBlock"))
    assert "2万元" not in hidden.text and "家庭年收入" not in hidden.text
    restored = client.post(url, json={"message": "现在可以写家庭年收入，请重新写。"})
    assert restored.status_code == 200 and "2万元" in restored.text


def test_policy_and_writing_are_delivered_together_without_guessing(conversation, monkeypatch):
    import server.app as app
    client, _, pid = conversation
    monkeypatch.setattr(app.agent, "_policy_evidence_reply", lambda *_a: "学校当年通知暂未找到。")
    response = client.post(f"/api/projects/{pid}/chat", json={"message":
        "国家励志奖学金的申请条件是什么？我叫王明，计算机专业，请帮我写申请书。"})
    assert response.status_code == 200
    assert all(value in response.text for value in ("学校当年通知暂未找到", "国家励志奖学金申请书", "王明", "计算机"))
    assert "WritingBlock" in response.text


@pytest.mark.parametrize("cloud", [False, True])
@pytest.mark.parametrize("stream", [False, True])
def test_local_reply_preflight_does_not_call_or_charge_a_model(conversation, monkeypatch, cloud, stream):
    import httpx
    import server.app as app
    client, store, pid = conversation
    if cloud:
        class Auth:
            async def get(self, *_args, **_kwargs):
                return httpx.Response(200, json={"id": "isolated-user", "created_at": "2026-01-01T00:00:00Z"})
        monkeypatch.setattr(app, "CLOUD_MODE", True)
        monkeypatch.setattr(app.app.state, "auth_http", Auth())
        client.headers["Authorization"] = "Bearer isolated-token"
    response = client.post(f"/api/projects/{pid}/chat", json={
        "message": "我叫王明，计算机专业，家庭年收入2万元，请写国家励志奖学金申请书。",
        "stream": stream, "llm_config": {"provider": "preset"},
    })
    assert response.status_code == 200 and "王明" in response.text and "<WritingBlock" in response.text
    assert "evidence-only" in response.text and '"free_chat":false' in response.text.replace(" ", "")
    assert store.get_workbench_credit_balance("isolated-user" if cloud else "local_user")["free_chat_count"] == 3
