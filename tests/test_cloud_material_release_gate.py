"""Safe cloud staging without requiring a production schema change."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from server.proposal.material_release_gate import gate_cloud_material_api
from server.proposal.materials import enabled


@pytest.mark.parametrize("ready,secret", [
    ("", ""), ("true", ""), ("false", "a" * 32),
    ("true", "too-short"), ("true", " " + "a" * 32),
])
def test_cloud_old_flags_cannot_enable_unprepared_pipeline(monkeypatch, ready, secret):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("MATERIAL_WORKER_READY", "true")
    monkeypatch.setenv("MATERIAL_HARDENED_READY", ready)
    monkeypatch.setenv("MATERIAL_SUBMIT_SECRET", secret)
    assert not gate_cloud_material_api(True)
    assert not enabled({"state": {"skill_id": "internet-plus"}})
    assert os.environ["MATERIAL_WORKER_READY"] == "false"


def test_hardened_cloud_protocol_requires_explicit_ready_and_valid_capability(monkeypatch):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("MATERIAL_WORKER_READY", "true")
    monkeypatch.setenv("MATERIAL_HARDENED_READY", "true")
    monkeypatch.setenv("MATERIAL_SUBMIT_SECRET", "a" * 32)
    assert gate_cloud_material_api(True)
    assert enabled({"state": {"skill_id": "internet-plus"}})
    assert os.environ["MATERIAL_WORKER_READY"] == "true"


def test_local_pipeline_and_local_worker_do_not_need_cloud_capability(monkeypatch):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "true")
    monkeypatch.setenv("MATERIAL_WORKER_READY", "true")
    monkeypatch.delenv("MATERIAL_HARDENED_READY", raising=False)
    monkeypatch.delenv("MATERIAL_SUBMIT_SECRET", raising=False)
    assert gate_cloud_material_api(False)
    assert enabled({"state": {"skill_id": "internet-plus"}})
    assert os.environ["MATERIAL_WORKER_READY"] == "true"


@pytest.mark.parametrize("ready,secret,expected", [
    ("", "", False), ("false", "x" * 32, False), ("true", "x" * 32, True),
])
def test_cloud_app_gates_view_and_worker_entry_at_startup_without_network(tmp_path, ready, secret, expected):
    root = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "PYTHONPATH": str(root / "server"),
                   "SUPABASE_URL": "https://example.invalid", "SUPABASE_PUBLISHABLE_KEY": "test-key",
                   "PROPOSAL_AGENT_TEMP_DIR": str(tmp_path), "MATERIAL_PIPELINE_ENABLED": "true",
                   "MATERIAL_WORKER_READY": "true", "MATERIAL_HARDENED_READY": ready,
                   "MATERIAL_SUBMIT_SECRET": secret}
    script = r'''
import os, app
from fastapi.testclient import TestClient
import proposal.material_api as api
assert app.CLOUD_MODE
expected = os.environ["EXPECTED_RESULT"] == "true"
assert (os.environ["MATERIAL_PIPELINE_ENABLED"] == "true") == expected
assert (os.environ["MATERIAL_WORKER_READY"] == "true") == expected
pid = "a" * 32
project = {"id": pid, "title": "合成项目", "level": "", "discipline": "", "school": "",
           "state": {"skill_id": "internet-plus"}, "outline": [], "sections": {},
           "diagrams": [], "material_revision": 0}
assert app.material_enabled(project) == expected
app.store.get_project = lambda _id: project
app.store.list_documents = lambda *_args: []
app.store.chunks_for_project = lambda *_args: []
app.store.messages = lambda *_args, **_kwargs: []
class Queue:
    cloud = False
    def __init__(self, _store): pass
    def call(self, action, **_kwargs):
        assert action == "list"
        return []
    def find(self, *_args): return None
    def submit(self, *_args): return {"id": "b" * 32, "status": "pending"}
api.MaterialJobs = Queue
# Isolate the API gate test from JWT verification and any network access.
app.CLOUD_MODE = False
with TestClient(app.app) as client:
    view = client.get(f"/api/projects/{pid}/material")
    submit = client.post(f"/api/projects/{pid}/material/jobs", json={
        "revision": 0, "kind": "export", "idempotency_key": "test", "allow_empty_draft": True})
assert view.status_code == (200 if expected else 404), view.text
assert submit.status_code == (202 if expected else 404), submit.text
if expected:
    assert view.json()["context"]["enabled"] and view.json()["worker_ready"]
'''
    environment["EXPECTED_RESULT"] = str(expected).lower()
    result = subprocess.run([sys.executable, "-c", script], cwd=root, env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
