import asyncio
import io
import json
from pathlib import Path
import sys
import uuid
import urllib.error
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "ops"))
from proposal import observability as obs
from stardust_ops.archive import (
    Archiver, OpsError, atomic_write, backup_keys, canonical, daily_slot,
    private_path, restore_keys, seal, sha, unseal,
)
from stardust_ops.cli import merge_events, run

NOW = datetime(2026, 10, 25, 2, tzinfo=timezone.utc)
KID = "c" * 32


class Keys:
    def __init__(self):
        self.value = bytes(range(32))

    def encryption_key(self, kid):
        if kid != KID:
            raise OpsError("KEYCHAIN_ITEM_MISSING")
        return self.value

    def get(self, account):
        return "synthetic-ops-capability-" + "a" * 32


class Cloud:
    def __init__(self, rows):
        self.rows = rows
        raw = b"".join(canonical(row) + b"\n" for row in rows)
        self.batch = {"id": str(uuid.uuid4()), "event_count": len(rows),
                      "plaintext_sha256": sha(raw), "schema_version": 1}
        self.acked = None
        self.purges = 0
        self.drop_ack = False
        self.fail_page = False
        self.pages = []

    def call(self, method, route, body=None, params=None):
        if route == "/archive/batches":
            return {"batch": None if self.acked else self.batch}
        if route == "/archive/status":
            return {"capacity_warning": False, "database_bytes": 18000000}
        if route == "/archive/inventory":
            return {"batches": [{**self.batch, **self.acked, "verified_at": NOW.isoformat()}] if self.acked else []}
        if route.endswith("/ack"):
            if self.acked:
                assert self.acked == body
            self.acked = body
            if self.drop_ack:
                self.drop_ack = False
                raise OpsError("OPS_NETWORK_OR_PROTOCOL_UNAVAILABLE")
            return {"verified": True}
        if route == "/archive/purge":
            assert self.acked is not None
            self.purges += 1
            return {"deleted": 0}
        assert method == "GET"
        if self.fail_page:
            raise OpsError("OPS_NETWORK_OR_PROTOCOL_UNAVAILABLE")
        offset = params["offset"]
        self.pages.append(offset)
        return {"batch": self.batch, "lines": [canonical(e).decode() for e in self.rows[offset:offset+200]]}


def rows(count=1):
    return [{"event_id": str(uuid.uuid4()), "trace_id": "b" * 32, "operation": "model",
             "status": "completed", "ingested_at": NOW.isoformat(), "metadata": {"prompt_tokens": 12}}
            for _ in range(count)]


@pytest.fixture
def archive(tmp_path):
    config = {"archive_dir": str(tmp_path / "private"), "key_id": KID}
    private_path(config["archive_dir"])
    cloud = Cloud(rows())
    return Archiver(cloud, Keys(), config, now=lambda: NOW,
                    disk_usage=lambda _: SimpleNamespace(free=10 * 1024**3))


def test_whitelist_and_telemetry_failure_cannot_escape(monkeypatch, caplog):
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("APP_VERSION", "private-secret-value")
    assert obs.safe_meta({"mime_type": {}, "transaction_kind": [], "body": "secret",
                          "filename": "secret.docx", "file_bytes": 42}) == {"file_bytes": 42}
    monkeypatch.setattr(obs, "rpc", lambda *a: (_ for _ in ()).throw(ValueError("private-key")))
    obs.emit("model.completed", metadata={"body": "secret", "prompt_tokens": 10}, code="private-secret")
    obs.emit("model.completed", duration_ms=object())
    text = caplog.text
    for secret in ("private-key", "private-secret", "secret.docx", '"body"'):
        assert secret not in text
    assert "observability_gap" in text
    assert obs.component_version() == "unknown"


def test_middleware_concurrency_download_transport_and_support_id(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    saved = []
    monkeypatch.setattr(obs, "send_events", lambda es: saved.extend(es))

    async def scenario():
        async def endpoint(scope, receive, send):
            obs.bind(owner_id=scope["user"])
            await asyncio.sleep(0)
            await send({"type": "http.response.start", "status": scope["status"], "headers": []})
            await send({"type": "http.response.body", "body": b"never inspect private content"})
        app = obs.ObservabilityMiddleware(endpoint)
        async def request(user, status):
            messages = []
            async def send(message):
                messages.append(message)
            await app({"type": "http", "path": "/api/projects/x/download", "method": "GET",
                       "user": user, "status": status}, None, send)
            return messages
        return await asyncio.gather(request("a" * 32, 200), request("b" * 32, 403))
    messages = asyncio.run(scenario())
    final = [e for e in saved if e["stage"] == "response_returned"]
    assert {e["owner_id"] for e in final} == {"a" * 32, "b" * 32}
    assert len({e["trace_id"] for e in final}) == 2
    assert dict(messages[1][0]["headers"])[b"x-support-id"]
    assert {e["status"] for e in final} == {"completed", "failed"}
    assert "never inspect" not in json.dumps(saved)
    assert obs.context.get() is None
    assert obs.operation("/api/material/jobs/x", "GET") is None
    assert obs.operation("/api/ops/logs/ingest", "POST") is None


def test_interrupted_send_is_not_success(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    saved = []
    monkeypatch.setattr(obs, "send_events", lambda es: saved.extend(es))
    async def endpoint(scope, receive, send):
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"content"})
    async def send(message):
        if message["type"] == "http.response.body":
            raise ConnectionError("private transport exception")
    with pytest.raises(ConnectionError):
        asyncio.run(obs.ObservabilityMiddleware(endpoint)(
            {"type": "http", "path": "/api/projects/a/download", "method": "GET"}, None, send))
    assert saved[-1]["status"] == "failed"
    assert saved[-1]["stage"] == "response_interrupted"


def test_archive_roundtrip_paging_and_duplicate_run(archive):
    archive.api = Cloud(rows(401))
    assert archive.run()["archived_batches"] == 1
    assert archive.api.pages == [0, 200, 400]
    path = next(archive.directory.glob("*.slog"))
    assert path.stat().st_mode & 0o777 == 0o600
    header, events = unseal(path.read_bytes(), archive.keys)
    assert len(events) == 401 and header["batch_id"] == archive.api.batch["id"]
    assert archive.run()["archived_batches"] == 0
    assert b"prompt_tokens" not in path.read_bytes()


def test_lost_ack_response_is_idempotently_recovered(archive):
    archive.api.drop_ack = True
    with pytest.raises(OpsError):
        archive.run()
    assert archive.api.acked and archive.api.purges == 0
    assert len(list(archive.directory.glob("*.slog"))) == 1
    archive.run()
    assert len(list(archive.directory.glob("*.receipt.json"))) == 1
    assert archive.api.purges == 1


@pytest.mark.parametrize("failure", ["tamper", "missing_file", "wrong_key", "disk", "offline", "keychain"])
def test_failures_never_purge(archive, failure):
    if failure in {"tamper", "missing_file", "wrong_key"}:
        archive.run()
        archive.api.purges = 0
        if failure == "missing_file":
            next(archive.directory.glob("*.slog")).unlink()
        elif failure == "tamper":
            path = next(archive.directory.glob("*.slog"))
            data = bytearray(path.read_bytes()); data[-1] ^= 1
            path.write_bytes(data)
        else:
            archive.keys.value = b"x" * 32
    elif failure == "disk":
        archive.disk_usage = lambda _: SimpleNamespace(free=0)
    elif failure == "offline":
        archive.api.fail_page = True
    else:
        archive.keys.encryption_key = lambda _: (_ for _ in ()).throw(OpsError("KEYCHAIN_LOCKED_OR_UNAVAILABLE"))
    with pytest.raises(OpsError):
        archive.run()
    assert archive.api.purges == 0


def test_mismatched_batch_and_retention_from_completion(archive):
    archive.run()
    path = next(archive.directory.glob("*.slog"))
    with pytest.raises(OpsError, match="ARCHIVE_BATCH_MISMATCH"):
        archive.receipt(path, {**archive.api.batch, "id": str(uuid.uuid4())})
    archive.now = lambda: NOW + timedelta(days=179)
    assert archive.run()["expired_local_batches"] == 0
    archive.now = lambda: NOW + timedelta(days=181)
    assert archive.run()["expired_local_batches"] == 1
    assert not path.exists()


def test_recovery_key_encryption_and_bad_password():
    encrypted = backup_keys(Keys(), [KID], "synthetic-passphrase")
    recovered = restore_keys(encrypted, "synthetic-passphrase")
    assert KID in recovered
    with pytest.raises(OpsError):
        restore_keys(encrypted, "different-passphrase")


def test_private_paths_and_atomic_interruption(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; repo.mkdir(); (repo / ".git").mkdir()
    with pytest.raises(OpsError, match="GIT"):
        private_path(repo / "archive")
    link = tmp_path / "link"; link.symlink_to(repo, target_is_directory=True)
    with pytest.raises(OpsError, match="SYMLINK"):
        private_path(link / "archive")
    target = tmp_path / "safe.slog"; atomic_write(target, b"old encrypted")
    monkeypatch.setattr("stardust_ops.archive.os.replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        atomic_write(target, b"new encrypted")
    assert target.read_bytes() == b"old encrypted"
    assert not list(tmp_path.glob("*.partial"))


def test_beijing_slot_and_local_only_query_without_cloud_key(archive, tmp_path, capsys):
    assert daily_slot(datetime(2026, 10, 25, 0, 59, tzinfo=timezone.utc)) == "2026-10-24"
    assert daily_slot(datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)) == "2026-10-25"
    archive.run()
    home = private_path(tmp_path / "ops")
    atomic_write(home / "config.json", canonical({**archive.config, "endpoint": "https://agent.stardust.website",
                                                "schema_version": 1, "single_copy_accepted": True}))
    archive.keys.get = lambda _: (_ for _ in ()).throw(OpsError("KEYCHAIN_LOCKED_OR_UNAVAILABLE"))
    assert run(["logs", "list", "--source", "local"], home=home, keys=archive.keys) == 0
    assert json.loads(capsys.readouterr().out)["events"]
    with pytest.raises(OpsError):
        run(["scheduled-run"], home=home, keys=archive.keys)
    assert json.loads((home / "state.json").read_text())["status"] == "failed"


def test_merge_deduplicates_cloud_and_local():
    e = rows()[0]
    assert merge_events([e], [e]) == [e]
    assert merge_events([e], [], {"operation": "upload"}) == []


def test_error_classification_preserves_business_error_body():
    raw = b'{"error":"InvalidMimeType","private":"synthetic body"}'
    error = urllib.error.HTTPError("https://fixed.test", 400, "error", {}, io.BytesIO(raw))
    assert obs.error_code(error) == ("STORAGE_UNSUPPORTED_MIME", 400)
    assert error.read() == raw


def test_ops_http_requires_separate_capability_and_does_not_echo_payload(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from proposal.ops_api import register_ops_api
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    app = FastAPI()
    register_ops_api(app)
    client = TestClient(app)
    calls = []
    def rpc(key, action, args):
        calls.append((key, action, args))
        if key != "synthetic-ops-capability-" + "a" * 32:
            raise urllib.error.HTTPError("https://fixed.test", 403, "denied", {}, None)
        return {"events": []}
    monkeypatch.setattr(obs, "rpc", rpc)
    assert client.get("/api/ops/logs/events").status_code == 403
    assert calls == []
    assert client.get("/api/ops/logs/events", headers={"Authorization": "Bearer " + "user-jwt-" * 8}).status_code == 403
    assert client.get("/api/ops/logs/events", headers={
        "Authorization": "Bearer synthetic-ops-capability-" + "a" * 32}).json() == {"events": []}
    assert len(calls) == 2
