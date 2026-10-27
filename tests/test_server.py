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


def test_uploaded_material_original_requires_confirmation_for_indexing(client):
    project = client.post(
        "/api/projects", json={"title": "上传预览回归", "skill_id": "innovation-research"}
    ).json()
    content = "这是上传后需要核对的材料。".encode("utf-8")
    result = client.post(
        f"/api/projects/{project['id']}/documents?kind=source",
        files={"files": ("材料.txt", content, "text/plain")},
    )
    assert result.status_code == 200
    document = result.json()["documents"][0]["document"]
    assert document["confirmed"] is False
    assert result.json()["documents"][0]["needs_confirmation"] is True
    original = client.get(f"/api/documents/{document['id']}/file")
    assert original.status_code == 200
    assert original.content == content
    assert original.headers["content-type"].startswith("text/plain")
    assert client.get(f"/api/projects/{project['id']}").json()["documents"][0]["confirmed"] is False
    confirmed = client.patch(f"/api/documents/{document['id']}/confirm", json={"confirmed": True})
    assert confirmed.status_code == 200
    assert client.get(f"/api/projects/{project['id']}").json()["documents"][0]["confirmed"] is True


def test_failed_reconfirmation_never_reveals_stale_chunks(client, monkeypatch):
    import app as server_app
    project = client.post("/api/projects", json={"title": "材料重确认"}).json()
    uploaded = client.post(
        f"/api/projects/{project['id']}/documents?kind=source",
        files={"files": ("事实.txt", "旧版材料包含珍贵原始数据".encode(), "text/plain")},
    ).json()["documents"][0]["document"]
    doc_id = uploaded["id"]
    assert client.patch(f"/api/documents/{doc_id}/confirm", json={"confirmed": True}).status_code == 200
    assert server_app.tools.search_project_materials(project["id"], "珍贵原始数据")["results"]
    monkeypatch.setattr(server_app.retriever, "index_document",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("index failure")))
    with pytest.raises(RuntimeError, match="index failure"):
        client.patch(f"/api/documents/{doc_id}/confirm",
                     json={"confirmed": True, "corrected_text": "新内容不包含原始数据"})
    assert not server_app.store.get_document(doc_id)["confirmed"]
    assert server_app.tools.search_project_materials(project["id"], "珍贵原始数据")["results"] == []
    assert client.get(f"/api/projects/{project['id']}").json()["documents"][0]["confirmed"] is False


def test_concurrent_newer_confirmation_is_not_overwritten(client, monkeypatch):
    import app as server_app
    from proposal.materials import MaterialConflict
    project = client.post("/api/projects", json={"title": "并发材料"}).json()
    uploaded = client.post(
        f"/api/projects/{project['id']}/documents?kind=source",
        files={"files": ("事实.txt", "最初文本".encode(), "text/plain")},
    ).json()["documents"][0]["document"]
    doc_id = uploaded["id"]
    def concurrent_update(*_args, **_kwargs):
        server_app.store.update_document_extraction(
            doc_id, "另一个请求更新的文本", "ready", confirmed=True, confirmed_by_user=True
        )
        raise MaterialConflict("材料已更改")
    monkeypatch.setattr(server_app.retriever, "index_document", concurrent_update)
    response = client.patch(f"/api/documents/{doc_id}/confirm",
                            json={"confirmed": True, "corrected_text": "本次提交的文本"})
    assert response.status_code == 409
    current = server_app.store.get_document(doc_id)
    assert current["extracted_text"] == "另一个请求更新的文本"
    assert current["confirmed"]


def test_legacy_automatic_confirmations_require_fresh_user_action(client, tmp_path):
    import app as server_app
    project = client.post("/api/projects", json={"title": "旧资料"}).json()
    file_path = tmp_path / "old.txt"
    file_path.write_text("旧系统自动提取的研究材料", encoding="utf-8")
    document = server_app.store.add_document(project["id"], "old.txt", str(file_path), "source", "text/plain")
    server_app.store.update_document_extraction(
        document["id"], "旧系统自动提取的研究材料", "ready", confirmed=True
    )
    # Simulate chunks produced by the former auto-confirming implementation.
    server_app.store.replace_chunks(document["id"], [{"content": "旧系统自动提取的研究材料", "source_ref": "段落 1"}])
    assert server_app.tools.search_project_materials(project["id"], "自动提取")["results"] == []
    assert client.get(f"/api/projects/{project['id']}").json()["documents"][0]["confirmed"] is False
    assert client.patch(f"/api/documents/{document['id']}/confirm", json={"confirmed": True}).status_code == 200
    assert server_app.tools.search_project_materials(project["id"], "自动提取")["results"]


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

    export_res = client.post(f"/api/projects/{p_id}/export", json={"allow_empty_draft": True})
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
    monkeypatch.setattr(server_app.app.state, "auth_http", MockAsyncClient())
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
        "storage_upload_endpoint": "",
        "max_upload_bytes": 50_000_000,
    }
    assert "service_role" not in response.text


def test_upload_proxy_is_explicitly_enabled_and_never_exposes_its_secret(client, monkeypatch):
    import app as server_app
    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    monkeypatch.setenv("STORAGE_UPLOAD_PROXY_ENABLED", "true")
    monkeypatch.setenv("UPLOAD_SESSION_SECRET", "this-must-not-reach-the-browser")
    response = client.get("/api/config")
    assert response.json()["storage_upload_endpoint"] == "/uploads/resumable"
    assert "this-must-not-reach-the-browser" not in response.text


def test_cloud_registration_does_not_download_or_parse_and_processing_can_retry(client, monkeypatch, tmp_path):
    import app as server_app
    import httpx
    from types import SimpleNamespace
    project_id, document_id = "a" * 32, "b" * 32
    path = tmp_path / "material.txt"
    path.write_text("这是已上传材料，解析失败后原文件必须保留。")
    document = {
        "id": document_id, "project_id": project_id, "original_name": "material.txt",
        "kind": "source", "stored_path": str(path), "storage_path": f"owner/{project_id}/{document_id}.txt",
        "extraction_status": "pending", "extracted_text": "", "confirmed": False,
    }
    downloads = []
    def register_document(**kwargs):
        assert kwargs["download"] is False
        return document
    def get_document(_id, download=True):
        if download:
            downloads.append(_id)
        return dict(document)
    def update(_id, text, status, warning, low, confirmed):
        document.update(extracted_text=text, extraction_status=status, extraction_warning=warning, confirmed=confirmed)
    fake_store = SimpleNamespace(
        register_document=register_document, get_document=get_document,
        get_project=lambda _: {"id": project_id, "state": {}}, update_document_extraction=update,
    )
    class Auth:
        async def get(self, *a, **kw):
            return httpx.Response(200, json={"id": "owner"})
    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    monkeypatch.setattr(server_app.app.state, "auth_http", Auth())
    monkeypatch.setattr(server_app, "store", fake_store)
    monkeypatch.setattr(server_app.retriever, "index_document", lambda *a: 1)
    headers = {"Authorization": "Bearer user-jwt"}
    payload = {
        "document_id": document_id, "original_name": "material.txt", "storage_path": document["storage_path"],
        "kind": "source", "process_now": False,
    }
    registered = client.post(f"/api/projects/{project_id}/documents/from-storage", json=payload, headers=headers)
    assert registered.status_code == 200
    assert registered.json()["documents"][0]["document"]["id"] == document_id
    assert downloads == []
    original_extract = server_app._extract_uploaded_document
    monkeypatch.setattr(server_app, "_extract_uploaded_document", lambda *a: (_ for _ in ()).throw(ValueError("解析失败")))
    failed = client.post(f"/api/documents/{document_id}/process", headers=headers)
    assert failed.status_code == 200
    assert failed.json()["documents"][0]["document"]["extraction_status"] == "error"
    assert path.exists()
    monkeypatch.setattr(server_app, "_extract_uploaded_document", original_extract)
    retried = client.post(f"/api/documents/{document_id}/process", headers=headers)
    assert retried.status_code == 200
    assert retried.json()["documents"][0]["document"]["confirmed"] is False
    assert retried.json()["documents"][0]["needs_confirmation"] is True
    assert "这是已上传材料" in retried.json()["documents"][0]["document"]["extracted_text"]


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


def test_storage_proxy_enforces_auth_and_ownership(client, monkeypatch):
    import app as server_app
    import httpx
    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    monkeypatch.setattr(server_app, "SUPABASE_URL", "https://fixed.supabase.co")

    async def get_user(self, *args, **kwargs):
        return httpx.Response(200, json={"id": "owner-1"})

    class MockAuthClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def get(self, *args, **kwargs):
            return httpx.Response(200, json={"id": "owner-1"})
        async def request(self, method, url, **kwargs):
            assert "owner-1" in str(url)
            return httpx.Response(200, json={"Key": "uploaded-ok"})

    mock_client = MockAuthClient()
    monkeypatch.setattr(server_app.app.state, "auth_http", mock_client)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: mock_client)
    headers = {"Authorization": "Bearer valid-user-jwt"}

    # 试图越权操作他人文件 -> 403
    resp = client.post(
        "/api/storage/proxy/object/stardust-project-files/other-user/project/doc.pdf",
        content=b"test data",
        headers=headers,
    )
    assert resp.status_code == 403
    assert "无权操作" in resp.json()["detail"]

    resp = client.post(
        "/api/storage/proxy/object/stardust-project-files/owner-1/project/doc.pdf",
        content=b"test data",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["Key"] == "uploaded-ok"


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


def test_skill_cards_and_route_expose_task_metadata(client):
    cards = client.get("/api/skill-cards")
    assert cards.status_code == 200
    assert cards.json()["total"] == 35
    assert all(card["id"] and card["aliases"] for card in cards.json()["cards"])
    result = client.post("/api/route", json={"query": "国家奖学金和励志奖学金有什么区别"}).json()
    assert result["task_type"] == "compare"
    assert result["selected"] is None
    assert result["method"]


def test_public_skill_cards_do_not_require_cloud_login(client, monkeypatch):
    import app as server_app
    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    response = client.get("/api/skill-cards")
    assert response.status_code == 200
    assert response.json()["total"] == 35


def test_public_knowledge_respects_confirmed_school_and_year(client):
    project = client.post("/api/projects", json={
        "title": "励志奖学金", "school": "无锡学院",
        "skill_id": "motivation-scholarship",
    }).json()
    project_id = project["id"]
    def search():
        return client.post(
            f"/api/projects/{project_id}/search/knowledge", json={"query": "申报条件 奖励标准"}
        ).json()
    assert not search()["official_evidence_found"]
    response = client.put(f"/api/projects/{project_id}/facts", json={"application_year": "2026", "education_level": "本科"})
    assert response.status_code == 200
    result = search()
    assert result["official_evidence_found"]
    assert all(row["school"] == "无锡学院" for row in result["results"] if row["kind"] == "official")
    assert client.put(f"/api/projects/{project_id}/facts", json={"application_year": "not-a-year"}).status_code == 422
    assert client.put(f"/api/projects/{project_id}/facts", json={"application_year": ""}).status_code == 200
    assert not search()["official_evidence_found"]


def test_outstanding_youth_league_uses_correct_skill_and_variant(client):
    query = "我要申报优秀团员"
    route = client.post("/api/route", json={"query": query}).json()
    assert route["selected"]["id"] == "outstanding-student"
    project = client.post("/api/projects", json={
        "title": "团员评优", "skill_id": route["selected"]["id"], "initial_request": query,
    }).json()
    assert project["state"]["skill_variant"] == "outstanding_youth_league"
    assert project["state"]["skill_name"] == "优秀团员"
    from proposal.agent import _system_prompt
    assert "category 必须使用 outstanding_youth_league" in _system_prompt(project)


def test_policy_chat_never_uses_unverified_guidance_or_model(client, monkeypatch):
    import app as server_app
    monkeypatch.setattr(server_app.agent, "_post", lambda *a, **kw: pytest.fail("must not invoke model"))
    project = client.post("/api/projects", json={
        "title": "国奖材料", "skill_id": "national-scholarship", "school": "无锡学院",
    }).json()
    project_id = project["id"]
    query = "国家奖学金评选时学业排名有何要求"
    before_wallet = server_app.store.get_workbench_credit_balance("local_user")
    response = client.post(f"/api/projects/{project_id}/chat", json={
        "message": query, "llm_config": {"provider": "preset"}
    })
    assert response.status_code == 200
    assert "暂未检索到适用于当前项目的官方依据" in response.json()["message"]
    assert "8000" not in response.json()["message"]
    assert response.json()["model"] == "evidence-only"
    after_wallet = server_app.store.get_workbench_credit_balance("local_user")
    assert after_wallet["free_chat_count"] == before_wallet["free_chat_count"]
    assert after_wallet["balance_micro_cny"] == before_wallet["balance_micro_cny"]

    client.put(f"/api/projects/{project_id}/facts", json={"application_year": "2026", "education_level": "本科"})
    response = client.post(f"/api/projects/{project_id}/chat", json={"message": query})
    assert response.status_code == 200
    assert "无锡学院2026年本科生国家奖学金" in response.json()["message"]
    assert "https://xgc.cwxu.edu.cn/info/1129/3307.htm" in response.json()["message"]
    assert "8000" not in response.json()["message"]
    assert response.json()["free_chat"] is False
    other_year = client.post(f"/api/projects/{project_id}/chat",
                             json={"message": "2027年国家奖学金评选排名条件是什么"}).json()["message"]
    assert "年度" in other_year and "不一致" in other_year
    assert "无锡学院2026年本科生国家奖学金" not in other_year
    other_school = client.post(f"/api/projects/{project_id}/chat",
                               json={"message": "河南大学国家奖学金评选排名条件是什么"}).json()["message"]
    assert "学校" in other_school and "不一致" in other_school
    assert "无锡学院2026年本科生国家奖学金" not in other_school
    unfamiliar_school = client.post(f"/api/projects/{project_id}/chat",
                                    json={"message": "武汉理工大学国家奖学金评选条件是什么"}).json()["message"]
    assert "其他学校" in unfamiliar_school
    assert "无锡学院2026年本科生国家奖学金" not in unfamiliar_school

    streamed = client.post(f"/api/projects/{project_id}/chat",
                           json={"message": query, "stream": True})
    assert streamed.status_code == 200
    assert "event: done" in streamed.text and "evidence-only" in streamed.text


def test_uploaded_notice_requires_confirmation_and_is_not_claimed_verified(client, monkeypatch):
    import app as server_app
    monkeypatch.setattr(server_app.agent, "_post", lambda *a, **kw: pytest.fail("must not invoke model"))
    project = client.post("/api/projects", json={"title": "通知核对", "skill_id": "national-scholarship"}).json()
    project_id = project["id"]
    uploaded = client.post(
        f"/api/projects/{project_id}/documents?kind=official",
        files={"files": ("通知.txt", "国家奖学金评选排名条件：以本学院通知为准。".encode(), "text/plain")},
    ).json()["documents"][0]["document"]
    query = "国家奖学金评选排名条件是什么"
    before = client.post(f"/api/projects/{project_id}/chat", json={"message": query}).json()["message"]
    assert "暂未检索到适用于当前项目的官方依据" in before
    assert client.patch(f"/api/documents/{uploaded['id']}/confirm", json={"confirmed": True}).status_code == 200
    after = client.post(f"/api/projects/{project_id}/chat", json={"message": query}).json()["message"]
    assert "用户标记为通知" in after
    assert "尚未独立核验" in after
    assert "本学院通知为准" in after


def test_policy_stream_preserves_verified_cloud_identity(client, monkeypatch):
    import httpx
    import app as server_app
    from proposal.agent import OllamaAgent
    from proposal.supabase_store import request_identity
    from proposal.tools import ProposalTools

    backing = server_app.store
    project = backing.create_project(title="隔离测试", school="")

    class IdentityStore:
        def __getattr__(self, name):
            value = getattr(backing, name)
            if not callable(value):
                return value
            def checked(*args, **kwargs):
                assert request_identity.get()["user_id"] == "verified-owner"
                return value(*args, **kwargs)
            return checked

    class Auth:
        async def get(self, *_args, **_kwargs):
            return httpx.Response(200, json={"id": "verified-owner"})

    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def auth_http():
        yield Auth()

    scoped_store = IdentityStore()
    scoped_tools = ProposalTools(scoped_store, server_app.retriever)
    monkeypatch.setattr(server_app, "CLOUD_MODE", True)
    monkeypatch.setattr(server_app, "auth_http", auth_http)
    monkeypatch.setattr(server_app, "store", scoped_store)
    monkeypatch.setattr(server_app, "tools", scoped_tools)
    monkeypatch.setattr(server_app, "agent", OllamaAgent(scoped_store, scoped_tools))
    response = client.post(
        f"/api/projects/{project['id']}/chat",
        headers={"Authorization": "Bearer scoped-token"},
        json={"message": "国家奖学金申请条件是什么", "stream": True},
    )
    assert response.status_code == 200
    assert "event: done" in response.text
    assert "暂未检索到适用于当前项目的官方依据" in response.text


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


def test_sensitive_endpoints_are_never_cached_or_echo_invalid_secrets(client, monkeypatch):
    import app as server_app
    monkeypatch.setattr(server_app, 'CLOUD_MODE', True)
    for method in ('get', 'post', 'delete'):
        response = getattr(client, method)('/api/user/llm-config')
        assert response.status_code == 401
        assert 'no-store' in response.headers['cache-control']
    monkeypatch.setattr(server_app, 'CLOUD_MODE', False)
    response = client.post('/api/auth/login', json={'email': 'x', 'password': 'hidden-password'})
    assert response.status_code == 422
    assert 'hidden-password' not in response.text
    response = client.get('/')
    assert 'no-cache' in response.headers['cache-control']
    assert '/static/app.js?v=' in response.text
    assert '/static/app.css?v=' in response.text
    body = client.get('/api/ping').json()
    assert body['status'] == 'ok'
    assert body.get('layout_rev') == 2  # 发版标记，用于部署后核对线上版本


def test_auth_sdk_proxy_is_fixed_upstream_preserves_jwt_and_errors(client, monkeypatch):
    import app as server_app
    import httpx
    monkeypatch.setattr(server_app, 'CLOUD_MODE', True)
    monkeypatch.setattr(server_app, 'SUPABASE_URL', 'https://fixed.supabase.co')
    captured = []
    async def send(self, method, url, **kwargs):
        captured.append((method, url, kwargs))
        return httpx.Response(400, json={'msg': 'Invalid refresh token'}, headers={'retry-after': '30'})
    monkeypatch.setattr(httpx.AsyncClient, 'request', send)
    response = client.post('/api/auth/proxy/token?grant_type=refresh_token',
        json={'refresh_token': 'private-refresh'}, headers={'Authorization': 'Bearer user-jwt', 'X-Forwarded-For': 'forged'})
    assert response.status_code == 400
    assert response.json() == {'msg': 'Invalid refresh token'}
    assert 'no-store' in response.headers['cache-control']
    assert response.headers['retry-after'] == '30'
    assert captured[0][1] == 'https://fixed.supabase.co/auth/v1/token'
    assert captured[0][2]['headers']['Authorization'] == 'Bearer user-jwt'
    assert 'x-forwarded-for' not in captured[0][2]['headers']
    assert client.post('/api/auth/proxy/admin/users').status_code == 404
    assert client.post('/api/auth/proxy/token', content=b'a' * 16385).status_code == 413


def test_model_config_cloud_crud_and_no_secret_in_save_response(client, monkeypatch):
    import app as server_app
    import httpx
    data = {}
    async def get_user(self, *args, **kwargs):
        return httpx.Response(200, json={'id': 'owner-A'})
    monkeypatch.setattr(httpx.AsyncClient, 'get', get_user)
    monkeypatch.setattr(server_app, 'CLOUD_MODE', True)
    class ConfigStore:
        def get_model_config(self):
            from proposal.supabase_store import request_identity
            return data.get(request_identity.get()['user_id'])
        def save_model_config(self, config):
            from proposal.supabase_store import request_identity
            data[request_identity.get()['user_id']] = config
        def delete_model_config(self):
            from proposal.supabase_store import request_identity
            data.pop(request_identity.get()['user_id'], None)
    monkeypatch.setattr(server_app, 'store', ConfigStore())
    headers = {'Authorization': 'Bearer valid-user-jwt'}
    config = {'provider': 'openai_compatible', 'model': 'deepseek-chat',
              'base_url': 'https://api.deepseek.com/v1', 'api_key': 'private-key-test'}
    assert client.get('/api/user/llm-config', headers=headers).json()['config'] is None
    response = client.post('/api/user/llm-config', json=config, headers=headers)
    assert response.json() == {'saved': True}
    assert 'private-key-test' not in response.text
    assert client.get('/api/user/llm-config', headers=headers).json()['config']['api_key'] == config['api_key']
    assert client.delete('/api/user/llm-config', headers=headers).json() == {'deleted': True}
    assert client.get('/api/user/llm-config', headers=headers).json()['config'] is None
    config['base_url'] = 'http://127.0.0.1:8080'
    assert client.post('/api/user/llm-config', json=config, headers=headers).status_code == 422


def test_only_matching_content_hashed_assets_receive_immutable_cache(client):
    import app as server_app
    version = server_app.ASSET_VERSIONS['app.js']
    good = client.get('/static/app.js?v=' + version)
    assert good.status_code == 200
    assert 'immutable' in good.headers['cache-control']
    bad = client.get('/static/app.js?v=old-release')
    assert 'immutable' not in bad.headers['cache-control']
    assert 'must-revalidate' in bad.headers['cache-control']
