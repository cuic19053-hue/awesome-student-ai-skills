from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
for path in (str(SERVER), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from proposal.supabase_store import SupabaseStore, request_identity  # noqa: E402


def test_rest_requests_forward_the_current_user_jwt_and_insert_owner(monkeypatch, tmp_path):
    captured = {}
    user_id = "b1d96922-0042-47c5-a1ec-f82c16bf226e"

    def fake_urlopen(request, timeout=0):
        captured["request"] = request
        captured["payload"] = json.loads(request.data.decode())
        return io.BytesIO(
            json.dumps(
                [
                    {
                        "id": "a" * 32,
                        "owner_id": user_id,
                        "title": "测试项目",
                        "level": "",
                        "discipline": "",
                        "school": "",
                        "state_json": {},
                        "outline_json": [],
                        "sections_json": {},
                        "diagrams_json": [],
                        "template_document_id": None,
                        "created_at": "2026-10-09T00:00:00Z",
                        "updated_at": "2026-10-09T00:00:00Z",
                    }
                ]
            ).encode()
        )

    import proposal.supabase_store as module

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    store = SupabaseStore("https://example.supabase.co", "sb_publishable_test", tmp_path)
    context = request_identity.set({"user_id": user_id, "access_token": "user-jwt"})
    try:
        result = store.create_project(title="测试项目")
    finally:
        request_identity.reset(context)

    assert captured["request"].get_header("Authorization") == "Bearer user-jwt"
    assert captured["request"].get_header("Apikey") == "sb_publishable_test"
    assert captured["payload"]["owner_id"] == user_id
    assert result["state"] == {}
    assert result["outline"] == []


def test_supabase_store_rejects_calls_without_authenticated_request_context(tmp_path):
    store = SupabaseStore("https://example.supabase.co", "sb_publishable_test", tmp_path)
    with pytest.raises(PermissionError, match="登录"):
        store.list_projects()


def test_cloud_upload_storage_path_must_match_user_and_project(tmp_path):
    store = SupabaseStore("https://example.supabase.co", "sb_publishable_test", tmp_path)
    context = request_identity.set(
        {"user_id": "owner-id", "access_token": "user-jwt"}
    )
    try:
        with pytest.raises(PermissionError, match="不匹配"):
            store.register_document(
                project_id="project-id",
                document_id="document-id-1234",
                original_name="notes.txt",
                storage_path="someone-else/project-id/document-id-1234.txt",
                kind="source",
                content_type="text/plain",
            )
    finally:
        request_identity.reset(context)
