import io
import json
import sys
import urllib.parse
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import app
from proposal.agent import OllamaAgent
from proposal.storage import Store
from proposal.tools import ProposalTools


JOB_ID = "a" * 32
LEASE = "b" * 32
PROJECT_ID = "c" * 32
OWNER_ID = "11111111-1111-4111-8111-111111111111"
WORKER_SECRET = "w" * 64


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("MATERIAL_WORKER_READY", "true")
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    store = Store(tmp_path)
    tools = ProposalTools(store)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", tools)
    monkeypatch.setattr(app, "agent", OllamaAgent(store, tools))
    project = store.create_project(title="worker proxy test")
    with TestClient(app.app) as client:
        yield client, store, project


def setup_proxy(monkeypatch, context):
    calls = []

    class FakeBridge:
        def __init__(self, secret, job_id, lease):
            assert secret == WORKER_SECRET
            assert job_id == JOB_ID
            assert lease == LEASE

        def context(self):
            return context

        def worker_rpc(self, action, **args):
            calls.append((action, args))
            return {"status": action}

        def authorize_byok(self, call_id, operation):
            calls.append(("authorize_byok", {"call_id": call_id, "operation": operation}))
            return {"ok": True}
    monkeypatch.setattr(app, "CLOUD_MODE", True)
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("MATERIAL_WORKER_READY", "true")
    monkeypatch.setattr(app, "MaterialWorkerBridge", FakeBridge)
    return calls


def auth_headers():
    return {"Authorization": f"Bearer {WORKER_SECRET}"}


@pytest.mark.parametrize(("status", "expected"), [(503, ["reserve"]), (401, ["reserve", "refund"])])
def test_gateway_failure_does_not_invent_a_refund(api, monkeypatch, status, expected):
    client, _, _ = api
    calls = setup_proxy(monkeypatch, {
        "id": JOB_ID, "project_id": PROJECT_ID, "owner_id": OWNER_ID,
        "kind": "section", "payload": {"paid": True, "platform": True},
    })
    monkeypatch.setattr(app, "_platform_bundle_ready", lambda **_: True)
    monkeypatch.setenv("WOPALLY_MODEL_BASE_URL", "https://api.wopally.cn/v1")
    monkeypatch.setenv("WOPALLY_WORKBENCH_API_KEY", "test-only-provider-key")
    monkeypatch.setenv("WOPALLY_WORKBENCH_API_KEY_ID", "17")

    def failure(request, **_kwargs):
        raise urllib.error.HTTPError(request.full_url, status, "failed", {}, io.BytesIO(b""))

    monkeypatch.setattr(app, "wopally_urlopen", failure)
    response = client.post("/api/material/internal/model", headers=auth_headers(), json={
        "job_id": JOB_ID, "lease": LEASE, "request_body": {"messages": [], "stream": False},
    })
    assert response.status_code == 502
    assert [action for action, _ in calls] == expected


def test_internal_proxy_rejects_missing_capability(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(app, "CLOUD_MODE", True)
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("MATERIAL_WORKER_READY", "true")
    response = client.post("/api/material/internal/model", json={
        "job_id": JOB_ID, "lease": LEASE, "request_body": {"messages": []},
    })
    assert response.status_code == 401


def test_internal_proxy_is_closed_while_feature_flags_are_off(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(app, "CLOUD_MODE", True)
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "false")
    monkeypatch.setenv("MATERIAL_WORKER_READY", "false")
    response = client.post("/api/material/internal/model", json={
        "job_id": JOB_ID, "lease": LEASE, "request_body": {"messages": []},
    }, headers=auth_headers())
    assert response.status_code == 503


def test_platform_model_proxy_preserves_confirmation_metering_and_no_secret_echo(api, monkeypatch):
    client, _, _ = api
    context = {
        "id": JOB_ID,
        "project_id": PROJECT_ID,
        "owner_id": OWNER_ID,
        "kind": "section",
        "payload": {"paid": True, "platform": True, "config": {"provider": "preset"}},
    }
    calls = setup_proxy(monkeypatch, context)
    monkeypatch.setattr(app, "_platform_bundle_ready", lambda **_: True)
    monkeypatch.setenv("WOPALLY_MODEL_BASE_URL", "https://api.wopally.cn/v1")
    monkeypatch.setenv("WOPALLY_WORKBENCH_API_KEY", "test-only-provider-key")
    monkeypatch.setenv("WOPALLY_WORKBENCH_API_KEY_ID", "17")
    upstream_requests = []

    def fake_open(request, timeout=45):
        upstream_requests.append(request)
        response = io.BytesIO(json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "已生成"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }).encode())
        response.status = 200
        response.headers = {}
        return response

    monkeypatch.setattr(app, "wopally_urlopen", fake_open)
    response = client.post("/api/material/internal/model", headers=auth_headers(), json={
        "job_id": JOB_ID,
        "lease": LEASE,
        "request_body": {
            "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": "请写项目方法"}],
            "stream": False,
        },
    })
    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "已生成"
    request_id = response.headers["x-material-usage-request-id"]
    assert request_id.startswith("o2x1_")
    assert upstream_requests[0].full_url == "https://api.wopally.cn/v1/chat/completions"
    assert upstream_requests[0].get_header("User-agent") == f"StardustWorkbench/{request_id}"
    assert json.loads(upstream_requests[0].data)["max_tokens"] == 2048
    assert calls[0][0] == "reserve"
    assert "test-only-provider-key" not in response.text


def test_byok_model_proxy_decrypts_only_inside_vercel(api, monkeypatch):
    client, _, _ = api
    context = {
        "id": JOB_ID,
        "project_id": PROJECT_ID,
        "owner_id": OWNER_ID,
        "kind": "section",
        "payload": {
            "paid": True, "platform": False, "config_ciphertext": "opaque-ciphertext",
        },
    }
    calls = setup_proxy(monkeypatch, context)
    monkeypatch.setattr(app, "decrypt_config", lambda owner, cipher: {
        "provider": "openai_compatible", "model": "student-model",
        "base_url": "https://models.example/v1", "api_key": "private-user-key",
    })
    monkeypatch.setattr(app, "_agent_for_config", lambda cfg, **_: SimpleNamespace(
        model=cfg.model, base_url=cfg.base_url, api_key=cfg.api_key,
    ))
    upstream_requests = []

    def fake_open(request, timeout=45):
        upstream_requests.append(request)
        response = io.BytesIO(json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "BYOK 完成"}}],
        }).encode())
        response.status = 200
        response.headers = {}
        return response

    monkeypatch.setattr(app, "safe_urlopen", fake_open)
    response = client.post("/api/material/internal/model", headers=auth_headers(), json={
        "job_id": JOB_ID,
        "lease": LEASE,
        "request_body": {
            "model": "worker-proxy",
            "messages": [{"role": "user", "content": "写摘要"}],
            "stream": False,
        },
    })
    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "BYOK 完成"
    assert response.headers.get("x-material-usage-request-id") is None
    assert upstream_requests[0].full_url == "https://models.example/v1/chat/completions"
    assert upstream_requests[0].get_header("Authorization") == "Bearer private-user-key"
    assert calls[0][0] == "authorize_byok"
    assert calls[0][1]["operation"] == "text"


def test_platform_image_proxy_uploads_using_job_scoped_signed_url(api, monkeypatch):
    client, _, _ = api
    image_path = f"{OWNER_ID}/{PROJECT_ID}/_material/{JOB_ID}-image.png"
    context = {
        "id": JOB_ID,
        "project_id": PROJECT_ID,
        "owner_id": OWNER_ID,
        "kind": "figure",
        "payload": {
            "paid": True,
            "platform": True,
            "spec": {
                "id": "scene", "section_id": "method", "title": "示意",
                "renderer": "gpt", "prompt": "无字抽象场景",
            },
            "image_path": image_path,
            "image_upload_url": f"https://storage.example.supabase.co/storage/v1/object/upload/sign/stardust-project-files/{image_path}?token=upload",
            "image_download_url": f"https://storage.example.supabase.co/storage/v1/object/sign/stardust-project-files/{image_path}?token=download",
        },
    }
    calls = setup_proxy(monkeypatch, context)
    monkeypatch.setattr(app, "SUPABASE_URL", "https://storage.example.supabase.co")
    monkeypatch.setattr(app, "_platform_bundle_ready", lambda **_: True)
    monkeypatch.setenv("WOPALLY_WORKBENCH_API_KEY_ID", "17")
    monkeypatch.setattr(app, "generate_image_deferred", lambda prompt, meter, **_: (
        b"\x89PNG\r\n\x1a\n" + b"generated-image",
        meter.reserve("gpt-image-2", 2_000_000),
    ))
    upload_calls = []

    def fake_upload(request, timeout=20):
        upload_calls.append((request.full_url, request.data, request.get_method()))
        response = io.BytesIO(b"")
        response.status = 200
        response.headers = {}
        return response

    monkeypatch.setattr("proposal.supabase_http.supabase_urlopen", fake_upload)
    response = client.post("/api/material/internal/image", headers=auth_headers(), json={
        "job_id": JOB_ID, "lease": LEASE, "prompt": "无字背景图",
    })
    assert response.status_code == 200, response.text
    assert response.json()["download_url"] == context["payload"]["image_download_url"]
    assert response.json()["request_id"].startswith("o2x1_")
    assert upload_calls and upload_calls[0][2] == "PUT"
    assert image_path in urllib.parse.unquote(urllib.parse.urlsplit(upload_calls[0][0]).path)
    assert calls[0][0] == "reserve"
