import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import material_worker


def test_cloud_worker_relays_openai_body_and_settles_only_after_response(monkeypatch):
    queue = material_worker.CloudQueue.__new__(material_worker.CloudQueue)
    queue.secret = "private-worker-capability"
    job = {"id": "a" * 32, "lease": "b" * 32}
    calls = []

    def fake_request(path, job_arg, body, *, timeout):
        calls.append((path, job_arg, body, timeout))
        if path.endswith("/model"):
            return httpx.Response(
                200,
                headers={"X-Material-Usage-Request-ID": "o2x1_" + "c" * 32},
                json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
            )
        return httpx.Response(200, json={"settled": True})

    monkeypatch.setattr(queue, "_internal_request", fake_request)
    request_body = {"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hi"}]}
    request = urllib.request.Request(
        "https://worker-proxy.invalid/v1/chat/completions",
        data=json.dumps(request_body).encode(),
        headers={"Authorization": "Bearer dummy"},
        method="POST",
    )
    with queue.model_opener(job)(request) as response:
        assert json.load(response)["choices"][0]["message"]["content"] == "ok"
    assert calls[0][0] == "/api/material/internal/model"
    assert calls[0][1] == job
    assert calls[0][2]["request_body"] == request_body
    assert calls[1][0] == "/api/material/internal/settle"
    assert calls[1][2] == {
        "request_id": "o2x1_" + "c" * 32,
        "model": "deepseek-v4-flash",
    }


def test_cloud_worker_does_not_retry_or_settle_rejected_model_request(monkeypatch):
    queue = material_worker.CloudQueue.__new__(material_worker.CloudQueue)
    queue.secret = "private-worker-capability"
    calls = []

    def fake_request(path, job_arg, body, *, timeout):
        calls.append(path)
        return httpx.Response(503, json={"detail": "unavailable"})

    monkeypatch.setattr(queue, "_internal_request", fake_request)
    request = urllib.request.Request(
        "https://worker-proxy.invalid/v1/chat/completions",
        data=b'{"model":"deepseek-v4-flash","messages":[]}',
        method="POST",
    )
    try:
        queue.model_opener({"id": "a" * 32, "lease": "b" * 32})(request)
        assert False, "expected HTTPError"
    except urllib.error.HTTPError as exc:
        assert exc.code == 503
    assert calls == ["/api/material/internal/model"]


def test_cloud_worker_downloads_image_from_private_signed_url(monkeypatch):
    queue = material_worker.CloudQueue.__new__(material_worker.CloudQueue)
    queue.secret = "private-worker-capability"
    job = {"id": "a" * 32, "lease": "b" * 32}
    calls = []
    expected_png = b"\x89PNG\r\n\x1a\n" + b"test-image"

    def fake_request(path, job_arg, body, *, timeout):
        calls.append(path)
        if path.endswith("/image"):
            return httpx.Response(200, json={
                "download_url": "https://example.supabase.co/storage/v1/object/sign/bucket/x.png?token=cap",
                "request_id": "o2x1_" + "d" * 32,
            })
        return httpx.Response(200, json={"settled": True})

    monkeypatch.setattr(queue, "_internal_request", fake_request)
    monkeypatch.setattr(material_worker, "transfer", lambda url: expected_png)

    assert queue.generate_image(job, "a bounded prompt") == expected_png
    assert calls == ["/api/material/internal/image", "/api/material/internal/settle"]
