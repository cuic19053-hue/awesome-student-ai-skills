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


def test_login_sdk_is_accessible_without_signin_from_this_origin(client, monkeypatch):
    import app as server_app
    import hashlib

    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    vendor = ROOT / "server/static/vendor"
    lock = json.loads((vendor / "supabase-js.lock.json").read_text())
    response = client.get("/static/vendor/" + lock["bundle"])
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert hashlib.sha256(response.content).hexdigest() == lock["bundle_sha256"]


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


def test_material_preview_and_persistent_upload_result_are_available(client):
    page = client.get("/")
    assert 'id="uploadResult"' in page.text
    assert 'aria-live="polite"' in page.text
    assert 'id="documentPreviewDialog"' in page.text
    assert 'id="documentPreviewBody"' in page.text
    assert 'id="downloadDocumentBtn"' in page.text
    assert "查看识别文字" in page.text


def test_uploaded_material_original_is_available_for_preview_with_auto_indexing(client):
    project = client.post(
        "/api/projects", json={"title": "上传预览回归", "skill_id": "innovation-research"}
    ).json()
    content = "这是已上传并自动入库的材料。".encode("utf-8")
    result = client.post(
        f"/api/projects/{project['id']}/documents?kind=source",
        files={"files": ("材料.txt", content, "text/plain")},
    )
    assert result.status_code == 200
    document = result.json()["documents"][0]["document"]
    assert document["confirmed"] is True
    original = client.get(f"/api/documents/{document['id']}/file")
    assert original.status_code == 200
    assert original.content == content
    assert original.headers["content-type"].startswith("text/plain")
    assert client.get(f"/api/projects/{project['id']}").json()["documents"][0]["confirmed"] is True


def test_leader_photo_upload_delete_and_export(client):
    import io
    from docx import Document

    page = client.get("/").text
    assert 'id="leaderPhotoPreview"' in page
    assert 'id="chooseLeaderPhotoBtn"' in page
    assert 'id="leaderPhotoInput"' in page
    assert 'id="removeLeaderPhotoBtn"' in page

    project = client.post(
        "/api/projects", json={"title": "负责人照片课题", "skill_id": "innovation-research"}
    ).json()
    p_id = project["id"]

    fake_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b"\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    upload_res = client.post(
        f"/api/projects/{p_id}/leader-photo",
        files={"file": ("leader.png", fake_png, "image/png")},
    )
    assert upload_res.status_code == 200
    body = upload_res.json()
    assert body["success"] is True
    photo_doc_id = body["document_id"]

    state = client.get(f"/api/projects/{p_id}").json()["state"]
    assert state.get("leader_photo") == photo_doc_id
    assert state.get("confirmed_facts", {}).get("leader_photo") == photo_doc_id

    export_res = client.post(f"/api/projects/{p_id}/export")
    assert export_res.status_code == 200
    dl_url = export_res.json()["download_url"]
    dl = client.get(dl_url)
    assert dl.status_code == 200
    doc = Document(io.BytesIO(dl.content))
    table_labels = [row.cells[0].text for table in doc.tables for row in table.rows]
    assert "负责人照片" in table_labels

    del_res = client.delete(f"/api/projects/{p_id}/leader-photo")
    assert del_res.status_code == 200
    state_after = client.get(f"/api/projects/{p_id}").json()["state"]
    assert "leader_photo" not in state_after
    assert "leader_photo" not in state_after.get("confirmed_facts", {})


def test_pricing_copy_omits_official_discount_but_keeps_reservation_notice(client, monkeypatch):
    import app as server_app

    monkeypatch.setattr(server_app, "_platform_bundle_ready", lambda: True)
    page = client.get("/").text
    preset = client.get("/api/models/preset").json()
    text = page + json.dumps(preset, ensure_ascii=False)
    assert "9 折" not in text
    assert "9折" not in text
    assert "按实际用量" in text
    assert "预留 5 积分" in page
    assert "预留 20 积分" in page


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
        "turnstile_site_key": "",
        "payment_enabled": False,
        "card_redemption_enabled": False,
        "voucher_redemption_enabled": False,
        "card_shop_url": "",
        "preset_enabled": False,
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


def test_save_and_delete_diagram(client):
    project = client.post(
        "/api/projects",
        json={"title": "图表测试课题", "skill_id": "innovation-research", "has_template": False},
    ).json()
    p_id = project["id"]
    res = client.post(
        f"/api/projects/{p_id}/diagrams",
        json={"title": "测试技术路线图", "nodes": ["数据采集", "模型训练", "实验验证"]},
    )
    assert res.status_code == 200
    diagram_id = res.json()["diagram"]["id"]
    proj_after = client.get(f"/api/projects/{p_id}").json()
    assert any(d["id"] == diagram_id for d in proj_after.get("diagrams", []))

    del_res = client.delete(f"/api/projects/{p_id}/diagrams/{diagram_id}")
    assert del_res.status_code == 200
    assert del_res.json()["ok"] is True
    proj_after_del = client.get(f"/api/projects/{p_id}").json()
    assert not any(d["id"] == diagram_id for d in proj_after_del.get("diagrams", []))


def test_custom_image_generation_with_byok(client, monkeypatch):
    import io
    import json
    import base64
    from proposal.workbench_images import generate_custom_image

    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    fake_b64 = base64.b64encode(fake_png).decode()

    class FakeResponse:
        def __init__(self, data):
            self.data = io.BytesIO(data)
        def read(self):
            return self.data.read()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=60):
        body = json.dumps({"data": [{"b64_json": fake_b64}]}).encode()
        return FakeResponse(body)

    monkeypatch.setattr("proposal.workbench_images.urllib.request.urlopen", fake_urlopen)

    project = client.post(
        "/api/projects",
        json={"title": "生图测试课题", "skill_id": "innovation-research", "has_template": False},
    ).json()
    p_id = project["id"]

    res = client.post(
        f"/api/projects/{p_id}/images/generate",
        json={
            "prompt": "绘制无人机火场侦测技术路线图",
            "llm_config": {
                "provider": "openai_compatible",
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "sk-fake-text-key",
                "image_model": "black-forest-labs/FLUX.1-schnell",
                "image_base_url": "https://api.siliconflow.cn/v1",
                "image_api_key": "sk-fake-image-key",
            },
        },
    )
    assert res.status_code == 200
    diagram = res.json()["diagram"]
    assert diagram["kind"] == "generated_image"
    assert "无人机" in diagram["title"]


def test_auth_proxy_endpoints(client, monkeypatch):
    import app as server_app

    # 1. 本地模式下拒绝登录注册
    monkeypatch.setattr(server_app, "CLOUD_MODE", False)
    r = client.post("/api/auth/login", json={"email": "test@qq.com", "password": "password123"})
    assert r.status_code == 400
    assert "无需登录" in r.json()["detail"]

    # 2. 云端模式下未登录也能访问（中间件放行）并转发至 Supabase
    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    monkeypatch.setattr(server_app, "SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setattr(server_app, "SUPABASE_PUBLISHABLE_KEY", "sb_pub_test_123")

    class MockResponse:
        def __init__(self, status_code, data):
            self.status_code = status_code
            self._data = data

        def json(self):
            return self._data

    # 登录成功
    async def mock_post_success(self, url, headers=None, json=None):
        return MockResponse(200, {
            "access_token": "mock-jwt-token",
            "refresh_token": "mock-refresh-token",
            "user": {"id": "user-123", "email": json["email"]},
        })

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_success)
    r = client.post("/api/auth/login", json={"email": "student@qq.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["access_token"] == "mock-jwt-token"

    # 密码错误友好提示
    async def mock_post_invalid_creds(self, url, headers=None, json=None):
        return MockResponse(400, {"msg": "Invalid login credentials"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_invalid_creds)
    r = client.post("/api/auth/login", json={"email": "student@qq.com", "password": "wrong"})
    assert r.status_code == 400
    assert "邮箱或密码错误" in r.json()["detail"]

    # 注册邮箱已存在友好提示
    async def mock_post_already_registered(self, url, headers=None, json=None):
        return MockResponse(422, {"msg": "User already registered"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_already_registered)
    r = client.post("/api/auth/signup", json={"email": "student@qq.com", "password": "password123"})
    assert r.status_code == 422
    assert "已被注册" in r.json()["detail"]
