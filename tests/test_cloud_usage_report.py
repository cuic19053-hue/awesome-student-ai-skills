"""The cloud report uses the same request-scoped data adapter as project work."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from proposal.supabase_store import SupabaseStore
from proposal.supabase_store import request_identity


def test_cloud_usage_logs_join_project_title_and_bound_pagination(tmp_path, monkeypatch):
    store = SupabaseStore("https://example.supabase.co", "public-test", tmp_path)
    calls = []

    def rest(table, params):
        calls.append((table, dict(params)))
        return [{"id": "usage-one", "model": "model-a", "projects": {"title": "我的申请"}},
                {"id": "usage-two", "model": "model-b", "projects": None}]

    monkeypatch.setattr(store, "_rest", rest)
    rows = store.get_detailed_usage_logs(limit=999, offset=-3, project_id="project-one")
    assert calls == [("token_usages", {"select": "*,projects(title)", "order": "created_at.desc",
                                      "limit": "200", "offset": "0", "project_id": "eq.project-one"})]
    assert rows[0]["project_title"] == "我的申请" and "projects" not in rows[0]
    assert rows[1]["project_title"] == ""


def test_cloud_usage_stats_include_model_breakdown(tmp_path, monkeypatch):
    store = SupabaseStore("https://example.supabase.co", "public-test", tmp_path)
    monkeypatch.setattr(store, "_rest", lambda *args, **kwargs: [
        {"task_type": "chat", "model": "model-a", "prompt_tokens": 2, "completion_tokens": 3,
         "total_tokens": 5, "latency_ms": 10},
        {"task_type": "section", "model": "model-a", "prompt_tokens": 3, "completion_tokens": 4,
         "total_tokens": 7, "latency_ms": 20},
    ])
    assert store.get_token_stats()["by_model"] == [{"model": "model-a", "count": 2, "tokens": 12}]


def test_cleanup_only_accepts_a_generated_export_in_current_owned_project(tmp_path, monkeypatch):
    store = SupabaseStore("https://example.supabase.co", "public-test", tmp_path)
    deleted = []
    monkeypatch.setattr(store, "_delete_storage", deleted.extend)
    token = request_identity.set({"user_id": "owner-one", "access_token": "test-jwt"})
    valid = "owner-one/project-one/_generated/export-" + "a" * 32 + ".docx"
    try:
        store.discard_generated_export("project-one", valid)
        store.discard_generated_export("project-two", valid)
        store.discard_generated_export("project-one", valid.replace("owner-one", "another-owner"))
        store.discard_generated_export("project-one", "owner-one/project-one/_generated/original.docx")
    finally:
        request_identity.reset(token)
    assert deleted == [valid]
