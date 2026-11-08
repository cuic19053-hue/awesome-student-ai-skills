"""Cloud job actions use a server capability without exposing it to users."""
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from proposal.material_api import register_material_api
from proposal.material_jobs import MaterialJobs, MaterialSecurityUnavailable
from proposal.storage import Store
from proposal.supabase_store import SupabaseStore


SECRET = "local-test-only-" + "x" * 40


class CloudStore:
    def __init__(self):
        self.calls = []

    def _rest(self, path, method="GET", params=None, payload=None):
        self.calls.append((path, method, payload))
        if payload.get("p_action") == "find":
            return {"id": "existing", "status": "completed"}
        return {"id": "result", "status": "pending"}


def test_cloud_sensitive_actions_are_bound_to_a_separate_server_secret(monkeypatch):
    monkeypatch.setenv("MATERIAL_SUBMIT_SECRET", SECRET)
    store = CloudStore()
    queue = MaterialJobs(store)
    payload = {"job_id": "job", "base_revision": 2}
    result = queue.submit("project", "section", "intro", payload, "click")
    assert result == {"id": "result", "status": "pending"}
    assert store.calls[-1][2]["p_secret"] == SECRET
    assert "p_secret" not in store.calls[-1][2]["p_args"]["payload"]
    assert SECRET not in str(result)
    queue.call("raw", project_id="project", id="job")
    assert store.calls[-1][2]["p_secret"] == SECRET
    queue.apply({"id": "job", "project_id": "project", "payload": {"base_revision": 2}}, {})
    assert store.calls[-1][0] == "rpc/material_apply"
    assert store.calls[-1][2]["p_secret"] == SECRET
    assert SECRET not in str(store.calls[-1][2]["p_args"])


def test_find_and_ordinary_owner_actions_do_not_send_the_capability(monkeypatch):
    monkeypatch.setenv("MATERIAL_SUBMIT_SECRET", SECRET)
    store = CloudStore()
    queue = MaterialJobs(store)
    assert queue.find("project", "click")["id"] == "existing"
    assert store.calls[-1][0] == "rpc/material_jobs_api"
    assert store.calls[-1][2] == {"p_action": "find", "p_args": {"project_id": "project", "idempotency": "click"}}
    queue.call("cancel", project_id="project", id="job")
    assert "p_secret" not in store.calls[-1][2]


@pytest.mark.parametrize("secret", ["", "short", " " * 40, " " + "x" * 40])
def test_missing_or_invalid_capability_fails_before_any_sensitive_request(monkeypatch, secret):
    monkeypatch.setenv("MATERIAL_SUBMIT_SECRET", secret)
    store = CloudStore()
    queue = MaterialJobs(store)
    with pytest.raises(MaterialSecurityUnavailable):
        queue.call("raw", project_id="project", id="job")
    with pytest.raises(MaterialSecurityUnavailable):
        queue.submit("project", "section", "intro", {"job_id": "job"}, "click")
    assert store.calls == []


def test_upstream_error_cannot_echo_capability_to_http_user_or_logs(monkeypatch, caplog):
    monkeypatch.setenv("MATERIAL_SUBMIT_SECRET", SECRET)

    class FailingCloud(CloudStore):
        def _rest(self, path, method="GET", params=None, payload=None):
            raise RuntimeError(f"upstream echoed {payload}")

    app = FastAPI()
    register_material_api(app, lambda: None, lambda config: config)

    @app.get("/test-sensitive")
    def trigger():
        return MaterialJobs(FailingCloud()).call("raw", project_id="project", id="job")

    response = TestClient(app).get("/test-sensitive")
    assert response.status_code == 503
    assert SECRET not in response.text
    assert "upstream echoed" not in response.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("operation", ["apply", "files/proposal.docx"])
def test_review_required_material_shows_clear_message_without_reading_raw(tmp_path, monkeypatch, operation):
    import proposal.material_api as material_api

    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    store = Store(tmp_path)
    project = store.create_project()

    class ReviewQueue:
        def __init__(self, _store):
            pass

        def call(self, action, **_args):
            assert action == "get", "untrusted historical task must never reach raw"
            return {"status": "needs_review"}

    monkeypatch.setattr(material_api, "MaterialJobs", ReviewQueue)
    app = FastAPI()
    register_material_api(app, lambda: store, lambda config: config)
    client = TestClient(app)
    url = f"/api/projects/{project['id']}/material/jobs/old/{operation}"
    response = client.post(url) if operation == "apply" else client.get(url)
    assert response.status_code == 409
    assert "核对后才能使用" in response.json()["detail"]


def cloud_store(tmp_path, monkeypatch, has_jobs, rows):
    store = SupabaseStore("https://example.test", "publishable", tmp_path)
    monkeypatch.setattr(store, "get_project", lambda _id: {"state": {}, "diagrams": []})
    monkeypatch.setattr(store, "list_documents", lambda *a, **kw: [])
    monkeypatch.setattr(store, "_identity", lambda: {"user_id": "owner"})
    removed, calls = [], []
    monkeypatch.setattr(store, "_delete_storage", lambda paths: removed.extend(paths))

    def rest(path, method="GET", params=None, payload=None):
        calls.append((path, method, params, payload))
        if path == "rpc/material_jobs_api" and payload["p_action"] == "has_jobs":
            return has_jobs
        if path == "rpc/material_jobs_api" and payload["p_action"] == "cleanup_paths":
            return rows
        if path == "projects" and method == "DELETE":
            return []
        raise AssertionError("unexpected request")

    monkeypatch.setattr(store, "_rest", rest)
    return store, removed, calls


def test_project_without_jobs_can_be_deleted_without_capability(tmp_path, monkeypatch):
    monkeypatch.delenv("MATERIAL_SUBMIT_SECRET", raising=False)
    store, removed, calls = cloud_store(tmp_path, monkeypatch, False, [])
    assert store.delete_project("project") is True
    assert removed == []
    assert any(path == "projects" and method == "DELETE" for path, method, _, _ in calls)


def test_legacy_project_without_jobs_is_deletable_without_capability(tmp_path, monkeypatch):
    monkeypatch.delenv("MATERIAL_SUBMIT_SECRET", raising=False)
    store, removed, calls = cloud_store(tmp_path, monkeypatch, None, [])
    original = store._rest
    def rest(path, method="GET", params=None, payload=None):
        if path == "rpc/material_jobs_api" and payload["p_action"] == "list":
            calls.append((path, method, params, payload))
            return []
        return original(path, method, params, payload)
    monkeypatch.setattr(store, "_rest", rest)
    assert store.delete_project("project") is True
    assert removed == []
    assert any(path == "projects" and method == "DELETE" for path, method, _, _ in calls)
    assert [payload["p_action"] for path, _, _, payload in calls if path == "rpc/material_jobs_api"] == ["has_jobs", "list"]


@pytest.mark.parametrize("legacy_result", [[{"id": "historical"}], {}, None])
def test_legacy_uncertain_or_existing_jobs_stop_deletion(tmp_path, monkeypatch, legacy_result):
    monkeypatch.delenv("MATERIAL_SUBMIT_SECRET", raising=False)
    store, removed, calls = cloud_store(tmp_path, monkeypatch, None, [])
    original = store._rest
    def rest(path, method="GET", params=None, payload=None):
        if path == "rpc/material_jobs_api" and payload["p_action"] == "list":
            return legacy_result
        return original(path, method, params, payload)
    monkeypatch.setattr(store, "_rest", rest)
    with pytest.raises(RuntimeError, match="历史材料任务"):
        store.delete_project("project")
    assert removed == []
    assert not any(path == "projects" and method == "DELETE" for path, method, _, _ in calls)


def test_legacy_list_permission_failure_never_deletes_project(tmp_path, monkeypatch):
    store, removed, calls = cloud_store(tmp_path, monkeypatch, None, [])
    original = store._rest
    def rest(path, method="GET", params=None, payload=None):
        if path == "rpc/material_jobs_api" and payload["p_action"] == "list":
            raise PermissionError("not authorized")
        return original(path, method, params, payload)
    monkeypatch.setattr(store, "_rest", rest)
    with pytest.raises(PermissionError):
        store.delete_project("project")
    assert removed == []
    assert not any(path == "projects" and method == "DELETE" for path, method, _, _ in calls)


def test_project_with_jobs_fails_before_delete_if_capability_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("MATERIAL_SUBMIT_SECRET", raising=False)
    store, removed, calls = cloud_store(tmp_path, monkeypatch, True, [])
    with pytest.raises(MaterialSecurityUnavailable):
        store.delete_project("project")
    assert removed == []
    assert not any(path == "projects" and method == "DELETE" for path, method, _, _ in calls)


def test_project_cleanup_uses_trusted_paths_and_enforces_owner_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("MATERIAL_SUBMIT_SECRET", SECRET)
    identifier = "a" * 32
    store, removed, calls = cloud_store(tmp_path, monkeypatch, True, [
        {"output_path": f"owner/project/_material/{identifier}.zip", "image_path": f"owner/project/_material/{identifier}-image.png"},
        {"output_path": f"other/project/_material/{identifier}.zip", "image_path": f"owner/another/_material/{identifier}.png"},
        {"output_path": "owner/project/_material/../../private.zip"},
    ])
    assert store.delete_project("project") is True
    assert removed == [f"owner/project/_material/{identifier}.zip", f"owner/project/_material/{identifier}-image.png"]
    payload = next(payload for path, _, _, payload in calls if path == "rpc/material_jobs_api" and payload["p_action"] == "cleanup_paths")
    assert payload["p_secret"] == SECRET


def test_project_cleanup_reads_all_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("MATERIAL_SUBMIT_SECRET", SECRET)
    store, removed, calls = cloud_store(tmp_path, monkeypatch, True, [])
    prior_rest = store._rest

    def paginated(path, method="GET", params=None, payload=None):
        if path == "rpc/material_jobs_api" and payload["p_action"] == "cleanup_paths":
            calls.append((path, method, params, payload))
            offset = payload["p_args"]["offset"]
            size = 500 if offset == 0 else 1
            return [{"output_path": f"owner/project/_material/{offset + i:032x}.zip"} for i in range(size)]
        return prior_rest(path, method, params, payload)

    monkeypatch.setattr(store, "_rest", paginated)
    assert store.delete_project("project") is True
    assert len(removed) == 501
    assert [payload["p_args"]["offset"] for path, _, _, payload in calls
            if path == "rpc/material_jobs_api" and payload["p_action"] == "cleanup_paths"] == [0, 500]
