# -*- coding: utf-8 -*-
"""向后兼容的服务路由测试。"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = ROOT / "server"
for _p in (str(SERVER_DIR), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# server/ 尚未纳入版本控制时，CI 不会安装 fastapi/httpx —— 此时跳过本模块而非报错。
if importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("httpx") is None:
    pytest.skip(
        "未安装 fastapi/httpx（server/ 尚未纳入版本控制时属预期），跳过服务层测试",
        allow_module_level=True,
    )

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    import app as server_app
    from proposal.agent import OllamaAgent
    from proposal.retrieval import ProjectRetriever
    from proposal.storage import Store
    from proposal.tools import ProposalTools

    isolated_store = Store(tmp_path)
    isolated_retriever = ProjectRetriever(isolated_store)
    isolated_tools = ProposalTools(isolated_store, isolated_retriever)
    isolated_agent = OllamaAgent(isolated_store, isolated_tools)
    monkeypatch.setattr(isolated_agent, "is_available", lambda: False)
    monkeypatch.setattr(
        isolated_agent,
        "status",
        lambda: {"running": False, "model_installed": False, "model": isolated_agent.model, "local": True},
    )
    monkeypatch.setattr(server_app, "store", isolated_store)
    monkeypatch.setattr(server_app, "retriever", isolated_retriever)
    monkeypatch.setattr(server_app, "tools", isolated_tools)
    monkeypatch.setattr(server_app, "agent", isolated_agent)
    with TestClient(server_app.app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["skills_loaded"] == 35


def test_chat_composer_offers_material_upload_categories(client):
    page = client.get("/")
    assert page.status_code == 200
    assert 'id="chatAttachBtn"' in page.text
    assert 'id="chatUploadKind"' in page.text
    assert 'id="modelSettingsBtn"' in page.text
    assert 'id="providerOllama"' in page.text
    assert 'id="providerCustom"' in page.text
    assert 'id="navResizeHandle"' in page.text
    assert 'id="workspaceResizeHandle"' in page.text
    assert "学校模板" in page.text
    assert "实验 / 调研照片" in page.text


def test_model_config_connection_test_never_echoes_api_key(client, monkeypatch):
    import app as server_app

    class MockAgent:
        def test_connection(self):
            return {
                "success": True,
                "provider": "openai_compatible",
                "model": "example-chat",
                "reply": "ignored",
            }

    monkeypatch.setattr(server_app, "_agent_for_config", lambda _config: MockAgent())
    response = client.post(
        "/api/model-config/test",
        json={
            "provider": "openai_compatible",
            "base_url": "https://api.example.test/v1",
            "model": "example-chat",
            "api_key": "secret-test-key",
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "api_key" not in response.json()
    assert "secret-test-key" not in response.text


def test_model_config_rejects_non_https_custom_endpoint(client):
    response = client.post(
        "/api/model-config/test",
        json={
            "provider": "openai_compatible",
            "base_url": "http://api.example.test/v1",
            "model": "example-chat",
            "api_key": "secret-test-key",
        },
    )
    assert response.status_code == 422


def test_cloud_api_blocks_project_access_without_supabase_session(client, monkeypatch):
    import app as server_app

    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    response = client.get("/api/projects")
    assert response.status_code == 401
    assert "登录" in response.json()["detail"]


def test_cloud_request_binds_verified_user_to_supabase_store_context(client, monkeypatch):
    import app as server_app
    import httpx
    from proposal.supabase_store import request_identity

    class MockResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "9e5ad745-804c-4ef2-8b7f-35ba4ac954fe"}

    class MockAsyncClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            return MockResponse()

    class IdentityStore:
        def list_projects(self):
            context = request_identity.get()
            return [{"id": context["user_id"]}]

    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    monkeypatch.setattr(server_app, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(server_app, "SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setattr(server_app, "store", IdentityStore())
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)
    response = client.get("/api/projects", headers={"Authorization": "Bearer verified-test-token"})
    assert response.status_code == 200
    assert response.json()["projects"][0]["id"] == "9e5ad745-804c-4ef2-8b7f-35ba4ac954fe"


def test_app_config_exposes_only_supabase_publishable_configuration(client, monkeypatch):
    import app as server_app

    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    monkeypatch.setattr(server_app, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(server_app, "SUPABASE_PUBLISHABLE_KEY", "sb_publishable_public")
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {
        "cloud_mode": True,
        "supabase_url": "https://example.supabase.co",
        "supabase_publishable_key": "sb_publishable_public",
    }
    assert "service_role" not in response.text


def test_chat_uses_request_model_config_without_saving_api_key(client, monkeypatch):
    import app as server_app

    project = client.post("/api/projects/start").json()
    captured = {}

    class MockAgent:
        def chat(self, project_id, message):
            captured["project_id"] = project_id
            captured["message"] = message
            return {"message": "收到。", "tool_calls": [], "model": "example-chat"}

    def make_agent(config):
        captured["config"] = config
        return MockAgent()

    monkeypatch.setattr(server_app, "_agent_for_config", make_agent)
    response = client.post(
        f"/api/projects/{project['id']}/chat",
        json={
            "message": "你好",
            "llm_config": {
                "provider": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "model": "example-chat",
                "api_key": "secret-test-key",
            },
        },
    )
    assert response.status_code == 200
    assert captured["config"].api_key == "secret-test-key"
    stored = client.get(f"/api/projects/{project['id']}").json()
    assert "secret-test-key" not in json.dumps(stored, ensure_ascii=False)


def test_types(client):
    r = client.get("/types")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 35
    assert len(body["skills"]) == 35


def test_web_skill_catalog_exposes_all_skills(client):
    response = client.get("/api/skills")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 35
    assert len(body["skills"]) == 35
    assert any(skill["id"] == "national-scholarship" for skill in body["skills"])


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("我要申请国家励志奖学金", "motivation-scholarship"),
        ("我要准备三下乡社会调查立项书", "social-survey"),
        ("帮我写转专业申请", "major-transfer"),
    ],
)
def test_natural_language_route_selects_the_matching_skill(client, query, expected):
    response = client.post("/api/route", json={"query": query})
    assert response.status_code == 200
    assert response.json()["selected"]["id"] == expected


def test_ambiguous_route_requests_clarification(client):
    response = client.post("/api/route", json={"query": "我想写申请材料"})
    assert response.status_code == 200
    assert response.json()["needs_clarification"] is True
    assert response.json()["selected"] is None


def test_project_can_start_in_a_non_innovation_skill(client):
    response = client.post(
        "/api/projects",
        json={
            "skill_id": "motivation-scholarship",
            "initial_request": "我要申请国家励志奖学金",
            "has_template": False,
        },
    )
    assert response.status_code == 200
    project = response.json()
    assert project["state"]["skill_id"] == "motivation-scholarship"
    assert project["state"]["skill_name"] == "国家励志奖学金"
    detail = client.get(f"/api/projects/{project['id']}").json()
    assert "国家励志奖学金" in detail["messages"][0]["content"]


def test_non_research_skill_can_save_skill_specific_facts(client):
    project = client.post(
        "/api/projects",
        json={"skill_id": "motivation-scholarship", "has_template": False},
    ).json()
    update = client.put(
        f"/api/projects/{project['id']}/facts",
        json={"gpa": "3.8/4.0", "family_income": "年收入 5 万元"},
    )
    assert update.status_code == 200
    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["state"]["confirmed_facts"]["gpa"] == "3.8/4.0"
    assert detail["state"]["confirmed_facts"]["family_income"] == "年收入 5 万元"
    assert client.post(f"/api/projects/{project['id']}/validate").json()["missing_facts"] == []
def test_new_project_starts_with_template_question_and_chat_saves_answer(client):
    response = client.post("/api/projects/start")
    assert response.status_code == 200
    project = response.json()
    assert project["state"]["template_preference"] == "not_asked"
    assert "学校下发的大创申报模板" in project["messages"][0]["content"]
    assert "聊天框下方" in project["messages"][0]["content"]

    import app as server_app

    server_app.agent._post = lambda *_args, **_kwargs: {
        "message": {"role": "assistant", "content": "好，我会按通用模板处理。你准备申报哪个级别？"}
    }
    answer = client.post(
        f"/api/projects/{project['id']}/chat",
        json={"message": "没有模板"},
    )
    assert answer.status_code == 200
    assert answer.json()["setup_updated"] is True
    updated = client.get(f"/api/projects/{project['id']}").json()
    assert updated["state"]["template_preference"] == "generic"


def test_topic_message_does_not_mistake_missing_experiments_for_no_template(client):
    import app as server_app

    project = client.post("/api/projects/start").json()
    server_app.agent._post = lambda *_args, **_kwargs: {
        "message": {"role": "assistant", "content": "了解，我们先梳理你的研究问题。"}
    }
    response = client.post(
        f"/api/projects/{project['id']}/chat",
        json={"message": "我目前没有实验数据，想先做植物病害观察。"},
    )
    assert response.status_code == 200
    state = client.get(f"/api/projects/{project['id']}").json()["state"]
    assert state["template_preference"] == "not_asked"


def test_route_returns_candidates(client):
    r = client.post("/route", json={"query": "我要申请国家奖学金", "top_n": 3})
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["candidates"]]
    assert names, "应至少返回一个候选赛道"
    assert "national_scholarship" in names


def test_fields_returns_checklist(client):
    r = client.get("/fields", params={"skill_id": "summary_report"})
    assert r.status_code == 200
    assert isinstance(r.json()["info_fields"], list)


def test_fields_unknown_skill_404(client):
    r = client.get("/fields", params={"skill_id": "not_a_real_skill"})
    assert r.status_code == 404


def test_generate_without_key_fails_fast(client):
    r = client.post("/generate", json={"skill_id": "summary_report", "user_info": {}})
    assert r.status_code == 503
    assert "LLM_API_KEY" in r.json()["detail"]


def test_generate_unknown_skill_404(client):
    r = client.post("/generate", json={"skill_id": "not_a_real_skill", "user_info": {}})
    assert r.status_code == 404
