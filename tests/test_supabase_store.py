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


def test_explicit_revision_uses_atomic_cas_even_for_legacy_type(monkeypatch, tmp_path):
    monkeypatch.delenv("MATERIAL_PIPELINE_ENABLED", raising=False)
    store = SupabaseStore("https://example.supabase.co", "public-test", tmp_path)
    p = {"id": "a" * 32, "state": {"skill_id": "national-scholarship"},
         "material_revision": 4, "sections": {}, "outline": []}
    monkeypatch.setattr(store, "get_project", lambda _: p)
    calls = []
    monkeypatch.setattr(store, "_project_row", lambda row: row)
    def rest(table, method, payload):
        calls.append((table, method, payload))
        return {"material_revision": 5}
    monkeypatch.setattr(store, "_rest", rest)
    assert store.update_project(p["id"], expected_revision=4, sections={"a": "正文"})["material_revision"] == 5
    assert calls[0][0] == "rpc/material_patch"
    assert calls[0][2]["p_revision"] == 4
    from proposal.materials import MaterialConflict
    with pytest.raises(MaterialConflict):
        store.update_project(p["id"], expected_revision=3, sections={})
    assert len(calls) == 1


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

    monkeypatch.setattr(module, "supabase_urlopen", fake_urlopen)
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


def test_generated_file_uses_ascii_storage_key_for_chinese_filename(monkeypatch, tmp_path):
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = request.data
        captured["upsert"] = request.get_header("X-upsert")
        return io.BytesIO(b"")

    import proposal.supabase_store as module

    monkeypatch.setattr(module, "supabase_urlopen", fake_urlopen)
    store = SupabaseStore("https://example.supabase.co", "sb_publishable_test", tmp_path)
    source = tmp_path / "draft.docx"
    source.write_bytes(b"word document")
    context = request_identity.set(
        {"user_id": "owner-id", "access_token": "user-jwt"}
    )
    try:
        storage_path = store.persist_generated_file(
            "project-id",
            "申报书草稿.docx",
            source,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    finally:
        request_identity.reset(context)

    assert storage_path == "owner-id/project-id/_generated/generated-docx"
    assert "generated-docx" in captured["url"]
    assert "申报书草稿" not in captured["url"]
    assert captured["body"] == b"word document"
    assert captured["upsert"] == "true"


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


def test_cloud_registration_is_idempotent_and_can_skip_downloading(monkeypatch, tmp_path):
    store = SupabaseStore("https://example.supabase.co", "sb_publishable_test", tmp_path)
    project, document_id = "a" * 32, "b" * 32
    path = f"owner/{project}/{document_id}.txt"
    calls = []
    saved = {}
    monkeypatch.setattr(store, "get_project", lambda _: {"id": project})
    monkeypatch.setattr(store, "get_document", lambda _id, download=False: saved.get(_id))
    monkeypatch.setattr(store, "_storage", lambda *args: calls.append(args) or b"")
    def rest(_table, _method, payload):
        calls.append("insert")
        saved[document_id] = payload
        return [payload]
    monkeypatch.setattr(store, "_rest", rest)
    context = request_identity.set({"user_id": "owner", "access_token": "user-jwt"})
    try:
        for _ in range(2):
            result = store.register_document(
                project_id=project, document_id=document_id, original_name="material.txt",
                storage_path=path, kind="source", content_type="text/plain", download=False,
            )
            assert result["id"] == document_id
    finally:
        request_identity.reset(context)
    assert calls == [("HEAD", path), "insert"]
    assert not Path(result["stored_path"]).exists()
