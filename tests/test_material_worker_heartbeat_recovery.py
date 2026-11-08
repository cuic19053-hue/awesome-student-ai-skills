"""A temporary queue outage must not discard a long-running draft."""
import io
import sys
import threading
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import material_worker


def test_transient_heartbeat_failure_recovers_and_completes_without_replaying_model(monkeypatch):
    monkeypatch.setattr(material_worker, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(material_worker, "HEARTBEAT_RETRY_SECONDS", 0.01)
    recovered = threading.Event()
    calls = []
    model_calls = []

    class Queue:
        def call(self, action, _job=None, **args):
            calls.append((action, args))
            if action == "claim":
                return {"id": "job", "lease": "lease", "project_id": "project",
                        "kind": "section", "payload": {"paid": True}}
            if action == "heartbeat":
                if sum(action == "heartbeat" for action, _ in calls) == 1:
                    raise urllib.error.URLError("temporary network error")
                recovered.set()
            return {"ok": True}

    def execute(_job, workspace, checkpoint, _local, _queue):
        model_calls.append("single paid call")
        (workspace / "output").mkdir()
        assert recovered.wait(1), "heartbeat did not recover"
        checkpoint("draft_saved", partial={"partial_content": "原稿"})
        return {"content": "原稿"}

    monkeypatch.setattr(material_worker, "execute", execute)
    assert material_worker.run_one(queue=Queue())
    assert model_calls == ["single paid call"]
    assert any(action == "finish" and args["status"] == "completed" and args["result"]["content"] == "原稿"
               for action, args in calls)


def test_rejected_lease_is_not_retried(monkeypatch):
    monkeypatch.setattr(material_worker, "HEARTBEAT_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(material_worker, "HEARTBEAT_RETRY_SECONDS", 0.001)
    stop, lost = threading.Event(), threading.Event()
    calls = []
    def update(_action):
        calls.append(1)
        raise urllib.error.HTTPError("https://example.invalid", 403, "rejected", {}, io.BytesIO())
    worker = threading.Thread(target=material_worker._maintain_lease, args=(stop, lost, update))
    worker.start()
    assert lost.wait(1)
    worker.join(1)
    assert calls == [1]


def test_persistent_transport_failure_has_a_bounded_retry(monkeypatch):
    monkeypatch.setattr(material_worker, "HEARTBEAT_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(material_worker, "HEARTBEAT_RETRY_SECONDS", 0.001)
    stop, lost = threading.Event(), threading.Event()
    calls = []
    def update(_action):
        calls.append(1)
        raise urllib.error.URLError("network unavailable")
    worker = threading.Thread(target=material_worker._maintain_lease, args=(stop, lost, update))
    worker.start()
    assert lost.wait(1)
    worker.join(1)
    assert len(calls) == material_worker.HEARTBEAT_MAX_ATTEMPTS
