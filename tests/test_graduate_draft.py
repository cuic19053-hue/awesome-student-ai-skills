"""Graduate starter: no invented admission claims or personal achievements."""
import sys
import io
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from proposal.graduate_draft import graduate_placeholder_draft, is_graduate_draft_request


PROJECT = {"id": "p", "state": {"skill_id": "graduate-recommendation"}}


@pytest.mark.parametrize("text", [
    "请写一份保研个人陈述，不要编造经历。", "帮我写推免申请书，不要写成绩。",
    "请帮我起草个人陈述。", "请重新写一份。",
])
def test_explicit_writing_request_is_supported(text):
    assert is_graduate_draft_request(text, PROJECT)


@pytest.mark.parametrize("text", [
    "保研个人陈述应该怎么写？", "推免的学校有哪些？", "不要写个人陈述。", "请说明申请资格。",
])
def test_questions_and_refusal_do_not_trigger_draft(text):
    assert not is_graduate_draft_request(text, PROJECT)


def test_narrow_personal_facts_and_missing_items_are_visible():
    text = "我叫李明，学计算机专业，绩点3.8，专业排名3/80，没有科研经历。请写一份保研个人陈述，不要编造经历。"
    draft = graduate_placeholder_draft([], text, [], project_id="p")
    assert all(value in draft for value in ("李明", "计算机", "3.8", "3/80", "暂无科研经历"))
    assert all(value in draft for value in ("【英语成绩待补充】", "【目标院校待补充】", "【未来学习与研究计划待补充】"))
    assert all(value not in draft for value in ("党员", "第一作者", "已经获得推免资格", "本人提供、尚未核验"))


@pytest.mark.parametrize("text", [
    "我准备申请保研推免，请帮我写个人陈述。姓名：李明，专业：计算机科学，绩点：3.8，排名：3/80。项目经历：参与校园图书检索系统的需求分析。",
    "请重新帮我写保研个人陈述。我叫李明，专业是计算机科学，绩点3.8，排名3/80。项目经历：参与校园图书检索系统的需求分析。",
])
def test_student_form_fields_and_natural_major_keep_following_facts(text):
    draft = graduate_placeholder_draft([], text, [], project_id="p")
    assert all(value in draft for value in ("李明", "计算机科学", "3.8", "3/80", "校园图书检索系统"))


def test_labelled_name_is_not_assumed_to_belong_to_student_without_self_context():
    text = "姓名：李明，专业：计算机科学，绩点：3.8，排名：3/80。"
    draft = graduate_placeholder_draft([], text, [], project_id="p")
    assert all(value not in draft for value in ("李明", "计算机科学", "3.8", "3/80"))
    third_party = "我准备申请保研，我朋友的姓名：李明，专业：计算机科学，绩点：3.8，排名：3/80。"
    draft = graduate_placeholder_draft([], third_party, [], project_id="p")
    assert all(value not in draft for value in ("李明", "计算机科学", "3.8", "3/80"))


def test_form_fields_honor_omission_and_later_correction():
    first = "我准备申请保研推免，请帮我写个人陈述。姓名：李明，专业：计算机科学，绩点：3.8，排名：3/80。"
    history = [{"role": "user", "content": first}]
    hidden = graduate_placeholder_draft(history, "请重写个人陈述，不要写姓名和成绩。", [], project_id="p")
    assert "计算机科学" in hidden
    assert all(value not in hidden for value in ("李明", "3.8", "3/80"))
    corrected = graduate_placeholder_draft(history, "更正，我的绩点改为3.9。请重新写个人陈述。", [], project_id="p")
    assert "3.9" in corrected and "3.8" not in corrected


def test_confirmed_matching_material_and_conflict_correction():
    history = [{"role": "user", "content": "我叫李明，学计算机专业，绩点3.8。"},
               {"role": "user", "content": "我的绩点是3.9。"}]
    documents = [
        {"project_id": "p", "kind": "source", "confirmed": 1, "confirmation_origin": "user",
         "extracted_text": "姓名：李明\n学院：信息学院\n获奖：数学建模二等奖"},
        {"project_id": "p", "kind": "source", "confirmed": 1, "confirmation_origin": "user",
         "extracted_text": "姓名：王五\n学院：管理学院"},
    ]
    draft = graduate_placeholder_draft(history, "请写保研个人陈述。", documents, project_id="p")
    assert "信息学院" in draft and "数学建模二等奖" in draft
    assert "管理学院" not in draft and "王五" not in draft
    assert "【绩点待补充】" in draft and "不同说法" in draft
    revised = graduate_placeholder_draft(history, "更正，我的绩点改为3.7。请重新写一份。", documents, project_id="p")
    assert "3.7" in revised and "3.8" not in revised and "3.9" not in revised


def test_grade_and_name_omission_preserves_other_fields_and_can_be_reversed():
    history = [{"role": "user", "content": "我叫李明，学计算机专业，绩点3.8，排名3/80。"}]
    text = "请帮我写保研个人陈述，不写姓名和成绩。"
    draft = graduate_placeholder_draft(history, text, [], project_id="p")
    assert "计算机" in draft
    assert all(value not in draft for value in ("李明", "绩点", "排名", "3.8", "3/80"))
    restored = graduate_placeholder_draft([*history, {"role": "user", "content": text}],
                                         "可以写姓名和成绩，请重新写。", [], project_id="p")
    assert "李明" in restored and "3.8" in restored and "3/80" in restored


def test_named_school_and_english_score_only_if_explicit_and_can_be_omitted():
    text = "我叫李明，目标院校是清华大学，六级成绩560分。请写保研个人陈述。"
    draft = graduate_placeholder_draft([], text, [], project_id="p")
    assert "清华大学" in draft and "六级560" in draft
    hidden = graduate_placeholder_draft([{"role": "user", "content": text}],
        "不要写目标院校，不要写英语成绩，请重新写。", [], project_id="p")
    assert "清华大学" not in hidden and "六级560" not in hidden
    assert "目标院校" not in hidden and "英语成绩" not in hidden


def test_explicit_personal_experience_motivation_and_plan_are_kept_without_inventing_details():
    text = ("我叫李明，学计算机专业，绩点3.8。"
            "项目经历：参与校园失物招领系统开发。"
            "申请方向：软件工程。申请动机：希望改进校园信息服务。"
            "研究计划：学习软件系统设计并探索相关问题。"
            "请帮我写保研个人陈述，不要编造经历。")
    draft = graduate_placeholder_draft([], text, [], project_id="p")
    assert all(phrase in draft for phrase in (
        "参与校园失物招领系统开发", "软件工程", "希望改进校园信息服务", "学习软件系统设计并探索相关问题"))
    assert all(phrase not in draft for phrase in ("主持", "第一作者", "国家级", "显著提升"))
    assert "【科研、课程项目或实践经历待补充】" not in draft
    assert "【申请动机与目标方向待补充】" not in draft
    assert "【未来学习与研究计划待补充】" not in draft


def test_narrative_conflicts_require_correction_and_partial_intent_keeps_missing_placeholder():
    history = [{"role": "user", "content": "申请方向：软件工程。"},
               {"role": "user", "content": "申请方向：人工智能。"}]
    draft = graduate_placeholder_draft(history, "请写保研个人陈述。", [], project_id="p")
    assert "软件工程" not in draft and "人工智能" not in draft
    assert "不同说法" in draft and "【申请动机与目标方向待补充】" in draft
    corrected = graduate_placeholder_draft(history, "申请方向改为数据科学。请重新写保研个人陈述。", [], project_id="p")
    assert "数据科学" in corrected and "【申请动机待补充】" in corrected


def test_narrative_does_not_copy_examples_or_another_person_and_respects_omissions():
    text = ("我叫李明，绩点3.8。"
            "项目经历：例如参加国家级竞赛。朋友的研究方向：计算机视觉。"
            "学习计划：强化系统设计能力。请写保研个人陈述。")
    draft = graduate_placeholder_draft([], text, [], project_id="p")
    assert "国家级竞赛" not in draft and "计算机视觉" not in draft
    assert "强化系统设计能力" in draft
    hidden = graduate_placeholder_draft([{"role": "user", "content": text}],
                                       "不要写姓名和成绩，请重新写保研个人陈述。", [], project_id="p")
    assert "李明" not in hidden and "3.8" not in hidden
    assert "强化系统设计能力" not in hidden


def test_narrative_opt_out_and_later_reauthorization_do_not_leak_hidden_facts():
    first = "项目经历：参加校内课程设计。申请方向：软件工程。学习计划：加强系统设计。"
    history = [{"role": "user", "content": first},
               {"role": "user", "content": "项目经历不要写，也不要写申请方向和学习计划。"}]
    hidden = graduate_placeholder_draft(history, "请写保研个人陈述。", [], project_id="p")
    assert all(value not in hidden for value in ("校内课程设计", "软件工程", "加强系统设计"))
    assert "【科研、课程项目或实践经历待补充】" not in hidden
    assert "【未来学习与研究计划待补充】" not in hidden
    restored = graduate_placeholder_draft(history, "允许写项目经历和申请方向，也可以写学习计划，请重新写保研个人陈述。", [], project_id="p")
    assert all(value in restored for value in ("校内课程设计", "软件工程", "加强系统设计"))


def test_application_scope_does_not_claim_the_full_application_package():
    draft = graduate_placeholder_draft([], "请写一份推免申请书。", [], project_id="p")
    assert "陈述初稿" in draft and "申请表、推荐信和附件" in draft
    assert "陈述初稿" not in graduate_placeholder_draft([], "请写一份保研个人陈述。", [], project_id="p")


def test_other_track_does_not_intercept():
    assert not is_graduate_draft_request("帮我写个人陈述。", {"state": {"skill_id": "major-transfer"}})


def test_explicit_request_to_use_confirmed_source_keeps_model_retrieval_path():
    message = "请根据材料写一份保研个人陈述。"
    source = {"project_id": "p", "kind": "source", "confirmed": 1, "confirmation_origin": "user"}
    assert not is_graduate_draft_request(message, PROJECT, documents=[source])
    assert is_graduate_draft_request(message, PROJECT, documents=[])
    assert is_graduate_draft_request(message, PROJECT, documents=[{**source, "confirmed": 0}])
    assert is_graduate_draft_request(message, PROJECT, documents=[{**source, "project_id": "other"}])
    assert is_graduate_draft_request(message, PROJECT, documents=[source],
                                     history=[{"role": "user", "content": "不要使用我的附件。"}])
    assert not is_graduate_draft_request("可以重新使用我的附件，请根据材料写一份保研个人陈述。", PROJECT,
                                         documents=[source], history=[{"role": "user", "content": "不要使用我的附件。"}])


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
    monkeypatch.setattr(retriever, "_embed_verified", lambda *_args, **_kwargs: (None, ""))
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


_REAL_BETA_INPUT = ("我叫李明，学计算机专业，绩点3.8，专业排名3/80，没有论文、专利和竞赛获奖经历。"
                    "请写一份保研个人陈述，不要编造经历。")


@pytest.mark.parametrize("message", [
    "我准备申请保研推免，请帮我写个人陈述。姓名：李明，专业：计算机科学，绩点：3.8，排名：3/80。项目经历：参与校园图书检索系统的需求分析。",
    "请重新帮我写保研个人陈述。我叫李明，专业是计算机科学，绩点3.8，排名3/80。项目经历：参与校园图书检索系统的需求分析。",
])
def test_browser_student_input_survives_real_api_preview_and_word(conversation, message):
    from docx import Document
    client, _, pid = conversation
    response = client.post(f"/api/projects/{pid}/chat", json={"message": message})
    assert response.status_code == 200, response.text
    assert all(value in response.text for value in ("李明", "计算机科学", "3.8", "3/80", "校园图书检索系统"))
    url = f"/api/projects/{pid}/chat-drafts"
    preview = client.get(url).json()
    saved = client.post(url + "/confirm", json={"snapshot": preview["snapshot"], "items": [{"id": preview["items"][0]["id"]}]})
    assert saved.status_code == 200, saved.text
    exported = client.post(f"/api/projects/{pid}/export").json()
    text = "\n".join(p.text for p in Document(io.BytesIO(client.get(exported["download_url"]).content)).paragraphs)
    assert all(value in text for value in ("李明", "计算机科学", "3.8", "3/80", "校园图书检索系统"))


def test_real_beta_input_can_be_saved_and_exported(conversation):
    from docx import Document
    client, store, pid = conversation
    response = client.post(f"/api/projects/{pid}/chat", json={
        "message": _REAL_BETA_INPUT, "llm_config": {"provider": "preset"},
    })
    assert response.status_code == 200, response.text
    assert response.json()["model"] == "evidence-only"
    assert store.get_project(pid)["state"]["skill_id"] == "graduate-recommendation"
    assert all(value in response.text for value in ("李明", "计算机", "3.8", "3/80", "待补充"))
    assert all(value not in response.text for value in ("第一作者", "已获得推免资格", "计算机科学与技术"))
    url = f"/api/projects/{pid}/chat-drafts"
    draft = client.get(url).json()
    assert len(draft["items"]) == 1 and draft["items"][0]["title"] == "保研个人陈述"
    saved = client.post(url + "/confirm", json={"snapshot": draft["snapshot"], "items": [{"id": draft["items"][0]["id"]}]})
    assert saved.status_code == 200
    exported = client.post(f"/api/projects/{pid}/export")
    assert exported.status_code == 200 and not exported.json()["validation"]["passed"]
    word = client.get(exported.json()["download_url"])
    text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(word.content)).paragraphs)
    assert all(value in text for value in ("李明", "计算机", "3.8", "3/80", "待补充"))


def test_labeled_student_experience_survives_preview_and_word_export(conversation):
    from docx import Document
    client, _, pid = conversation
    response = client.post(f"/api/projects/{pid}/chat", json={"message": (
        "我叫李明，学计算机专业，绩点3.8。项目经历：参与校园失物招领系统开发。"
        "申请方向：软件工程。申请动机：希望改进校园信息服务。"
        "学习计划：加强系统设计。请写保研个人陈述，不要编造经历。")})
    assert response.status_code == 200, response.text
    url = f"/api/projects/{pid}/chat-drafts"
    preview = client.get(url).json()
    result = client.post(url + "/confirm", json={"snapshot": preview["snapshot"],
                                                   "items": [{"id": preview["items"][0]["id"]}]})
    assert result.status_code == 200, result.text
    exported = client.post(f"/api/projects/{pid}/export").json()
    data = client.get(exported["download_url"]).content
    text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    assert all(value in text for value in ("参与校园失物招领系统开发", "软件工程", "希望改进校园信息服务", "加强系统设计"))
    assert all(value not in text for value in ("国家级", "第一作者", "主持"))


@pytest.mark.parametrize("cloud", [False, True])
@pytest.mark.parametrize("stream", [False, True])
def test_bounded_draft_neither_calls_nor_charges_model(conversation, monkeypatch, cloud, stream):
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
        "message": _REAL_BETA_INPUT, "stream": stream, "llm_config": {"provider": "preset"},
    })
    assert response.status_code == 200 and "李明" in response.text and "<WritingBlock" in response.text
    assert "evidence-only" in response.text and '"free_chat":false' in response.text.replace(" ", "")
    assert store.get_workbench_credit_balance("isolated-user" if cloud else "local_user")["free_chat_count"] == 3


def test_consultation_does_not_get_forced_into_a_draft(conversation, monkeypatch):
    import server.app as app
    client, _, pid = conversation
    calls = []
    def model(_endpoint, _payload):
        calls.append(True)
        return {"message": {"content": "个人陈述可以围绕学习经历、研究兴趣和未来计划组织。"}}
    monkeypatch.setattr(app.agent, "_post", model)
    response = client.post(f"/api/projects/{pid}/chat", json={"message": "保研个人陈述应该怎么写？"})
    assert response.status_code == 200 and calls == [True]
    assert "WritingBlock" not in response.text and "研究兴趣" in response.text


def test_material_opt_out_then_explicit_reauthorization_changes_actual_chat_path(conversation, monkeypatch):
    import copy
    import json
    import server.app as app
    client, store, pid = conversation
    source = "姓名：李明\n个人基本情况：我参加过课程项目，负责资料整理。".encode()
    upload = client.post(f"/api/projects/{pid}/documents?kind=source", files={
        "files": ("李明资料.txt", source, "text/plain"),
    })
    assert upload.status_code == 200
    doc = upload.json()["documents"][0]["document"]
    assert client.patch(f"/api/documents/{doc['id']}/confirm", json={"confirmed": True}).status_code == 200
    store.add_message(pid, "user", "请不要使用我的附件。")
    hidden = client.post(f"/api/projects/{pid}/chat", json={"message": (
        "我叫李明，想申请保研，请根据材料写一份个人陈述。"
    ), "llm_config": {"provider": "preset"}})
    assert hidden.status_code == 200 and hidden.json()["model"] == "evidence-only"
    assert "资料整理" not in hidden.text and store.get_workbench_credit_balance("local_user")["free_chat_count"] == 3

    requests = []
    answers = iter([
        {"tool_calls": [{"id": "source", "function": {"name": "search_project_materials", "arguments": {"query": "个人基本情况"}}}]},
        {"content": '<WritingBlock variant="document">\n## 保研个人陈述\n\n我叫李明，参加过课程项目并负责资料整理。\n</WritingBlock>'},
    ])
    def simulated_model(_endpoint, payload):
        requests.append(copy.deepcopy(payload))
        return {"message": next(answers)}
    monkeypatch.setattr(app.agent, "_post", simulated_model)
    allowed = client.post(f"/api/projects/{pid}/chat", json={"message": (
        "现在可以重新使用我的附件，请根据材料写一份保研个人陈述。"
    )})
    assert allowed.status_code == 200 and allowed.json()["tool_calls"] == ["search_project_materials"]
    evidence = json.loads(next(item["content"] for item in requests[1]["messages"] if item.get("role") == "tool"))
    assert "资料整理" in evidence["results"][0]["text"]
    assert "资料整理" in allowed.text and len(requests) == 2
