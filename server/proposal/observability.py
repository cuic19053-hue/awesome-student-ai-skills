"""Content-free business events. Credentials, bodies and exception text never enter events."""
from __future__ import annotations

from contextlib import contextmanager
import contextvars
import functools
import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

log = logging.getLogger("stardust.observability")
context = contextvars.ContextVar("stardust_event_context", default=None)
MIMES = {
    "application/zip", "application/pdf", "text/plain", "text/markdown",
    "image/png", "image/jpeg", "image/webp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
NUMBERS = {"file_bytes", "chapter_count", "outline_count", "record_count",
           "prompt_tokens", "completion_tokens", "attempt", "response_bytes"}
TEXT_ENUMS = {"transaction_kind": {"card_redeem", "usage_reserve", "usage_settle",
                                  "usage_refund", "admin_adjustment", "payment_credit"}}
ID = re.compile(r"^[a-f0-9-]{16,64}$")
USAGE = re.compile(r"^[a-zA-Z0-9_:-]{1,100}$")
_get_store = lambda: None


def configure(get_store):
    global _get_store
    _get_store = get_store


def enabled():
    return os.environ.get("OBSERVABILITY_ENABLED", "").lower() == "true"


def no_throw(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            # Never interpolate the input or exception (could contain user content).
            try:
                log.warning('{"observability_gap":"EVENT_ENCODING_FAILED"}')
            except Exception:
                pass
    return wrapped


def correlated(kind, owner, identifier):
    return hashlib.sha256(f"{kind}:{owner}:{identifier}".encode()).hexdigest()[:32]


@no_throw
def bind(owner_id=None, project_id=None, trace_id=None, job_id=None):
    state = context.get()
    if state is None:
        return
    for key, value in (("owner_id", owner_id), ("project_id", project_id), ("job_id", job_id)):
        if value and ID.fullmatch(str(value)):
            state[key] = str(value)
    if trace_id and ID.fullmatch(str(trace_id)):
        old = state["trace_id"]
        state["trace_id"] = trace_id
        for event in state["events"]:
            if event["trace_id"] == old:
                event["trace_id"] = trace_id


def component_version():
    value = os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("APP_VERSION") or "unknown"
    return value if re.fullmatch(r"[a-f0-9]{7,40}", value) else "unknown"


def environment():
    value = os.environ.get("VERCEL_ENV", "local")
    return value if value in {"production", "preview", "local", "test"} else "local"


@no_throw
def identify_auth(result):
    user = result.get("user") or result
    if isinstance(user, dict):
        bind(owner_id=user.get("id"))


def safe_meta(value=None):
    result = {}
    for key, item in (value if isinstance(value, dict) else {}).items():
        if key in NUMBERS and type(item) is int and 0 <= item <= 10**12:
            result[key] = item
        elif key == "billable" and type(item) is bool:
            result[key] = item
        elif key == "mime_type" and isinstance(item, str) and item in MIMES:
            result[key] = item
        elif key in TEXT_ENUMS and isinstance(item, str) and item in TEXT_ENUMS[key]:
            result[key] = item
    return result if len(json.dumps(result).encode()) <= 1024 else {}


def error_code(exc=None, http_status=None):
    if isinstance(exc, urllib.error.HTTPError):
        http_status = exc.code
        # Bounded inspection for classification only; never return or log this body.
        if exc.code == 400:
            try:
                # Classification must not consume a response used by business error handling.
                if not exc.fp or not exc.fp.seekable():
                    return "INVALID_REQUEST", 400
                position = exc.fp.tell()
                try:
                    body = exc.read(4096)
                finally:
                    exc.fp.seek(position)
                if b"InvalidMimeType" in body or b"mime type" in body:
                    return "STORAGE_UNSUPPORTED_MIME", 400
            except Exception:
                pass
    if isinstance(exc, (TimeoutError,)):
        return "UPSTREAM_TIMEOUT", http_status
    if isinstance(exc, (ConnectionError, urllib.error.URLError)):
        return "UPSTREAM_UNAVAILABLE", http_status
    return ({400: "INVALID_REQUEST", 401: "AUTH_REQUIRED", 403: "ACCESS_DENIED",
             404: "NOT_FOUND", 409: "REVISION_CONFLICT", 413: "FILE_TOO_LARGE",
             415: "UNSUPPORTED_MEDIA_TYPE", 422: "VALIDATION_FAILED",
             429: "RATE_LIMITED", 502: "UPSTREAM_FAILED", 503: "SERVICE_UNAVAILABLE",
             504: "UPSTREAM_TIMEOUT"}.get(http_status, "OPERATION_FAILED"), http_status)


@no_throw
def emit(event, *, stage="", status="completed", level="info", job_id=None,
         usage_request_id=None, metadata=None, http_status=None, error=None,
         code=None, duration_ms=None):
    if not enabled():
        return
    if not re.fullmatch(r"[a-z_]+(?:\.[a-z_]+){1,3}", event):
        return
    state = context.get()
    state = state if state is not None else {
        "trace_id": uuid.uuid4().hex, "http_request_id": None, "events": []}
    classified, http_status = error_code(error, http_status)
    item = {
        "event_id": str(uuid.uuid4()), "trace_id": state["trace_id"],
        "http_request_id": state.get("http_request_id"),
        "owner_id": state.get("owner_id"), "project_id": state.get("project_id"),
        "job_id": job_id if job_id and ID.fullmatch(str(job_id)) else state.get("job_id"),
        "usage_request_id": usage_request_id if usage_request_id and USAGE.fullmatch(usage_request_id) else None,
        "occurred_at": datetime.now(timezone.utc).isoformat(), "event": event,
        "operation": event.split(".")[0], "stage": stage[:64] if re.fullmatch(r"[a-z_]{0,64}", stage) else "",
        "status": status if status in {"started", "completed", "failed", "accepted", "pending", "cancelled"} else "pending",
        "level": level if level in {"info", "warning", "error"} else "info",
        "error_code": (code if isinstance(code, str) and re.fullmatch(r"[A-Z_]{1,80}", code) else classified) if error or code or (http_status and http_status >= 400) else None,
        "http_status": http_status, "duration_ms": max(0, int(duration_ms)) if duration_ms is not None else None,
        "version": component_version(),
        "environment": environment(),
        "metadata": safe_meta(metadata),
    }
    if context.get() is not None:
        if len(state["events"]) < 48:
            state["events"].append(item)
        else:
            fallback([item], "EVENT_BUFFER_LIMIT")
    else:
        send_events([item])


@no_throw
def record_model_usage(response, usage_request_id=None):
    # API and detached legacy jobs have a request context. Production document
    # Workers use the lease-verified collector; their Vercel relay records usage.
    if context.get() is None:
        return
    usage = response.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    emit("model.usage_recorded", stage="response_received", usage_request_id=usage_request_id,
         metadata={"prompt_tokens": usage.get("prompt_tokens"),
                   "completion_tokens": usage.get("completion_tokens")})


def fallback(events, reason):
    for event in events:
        try:
            log.warning(json.dumps({"observability_gap": reason, **event}, ensure_ascii=False))
        except Exception:
            pass


def rpc(key, action, args):
    store = _get_store()
    if not store or not hasattr(store, "project_url"):
        raise RuntimeError("observability backend unavailable")
    from .supabase_http import supabase_urlopen
    request = urllib.request.Request(
        store.project_url + "/rest/v1/rpc/observability_api",
        data=json.dumps({"p_key": key, "p_action": action, "p_args": args}).encode(),
        headers={"apikey": store.publishable_key, "Authorization": "Bearer " + store.publishable_key,
                 "Content-Type": "application/json"}, method="POST")
    with supabase_urlopen(request, timeout=3) as response:
        return json.load(response)


def enrich(events, state):
    for event in events:
        event["owner_id"] = event.get("owner_id") or state.get("owner_id")
        event["project_id"] = event.get("project_id") or state.get("project_id")
        event["job_id"] = event.get("job_id") or state.get("job_id")
    return events


def send_events(events):
    if not events:
        return
    try:
        result = rpc(os.environ.get("OBSERVABILITY_WRITE_KEY", ""), "append", {"events": events})
        if result.get("written", 0) != len(events):
            fallback(events, "PERSISTENCE_LIMIT_OR_DUPLICATE")
    except Exception:
        fallback(events, "PERSISTENCE_UNAVAILABLE")


@contextmanager
def background_scope(job_id, project_id):
    parent = context.get() or {}
    owner = parent.get("owner_id")
    state = {"trace_id": correlated("job", owner or "local", job_id), "owner_id": owner, "job_id": job_id,
             "project_id": project_id, "http_request_id": None, "events": []}
    token = context.set(state)
    try:
        yield
    finally:
        try:
            send_events(enrich(state["events"], state))
        finally:
            context.reset(token)


def operation(path, method):
    if path.startswith("/api/ops/") or path.startswith("/static/"):
        return None
    if path.startswith("/api/auth/") and method == "POST":
        return "auth.operation"
    if method == "GET" and (path.endswith("/download") or "/files/" in path):
        return "download.served"
    if method not in {"POST", "PUT", "DELETE"}:
        return None
    if path.startswith("/api/material/internal/"):
        return "billing.http" if path.endswith("/settle") else "model.http"
    if "redeem" in path or path.startswith("/api/pay/"):
        return "billing.recharge"
    if "/chat" in path:
        return "model.http"
    if "documents" in path or "upload" in path:
        return "upload.operation"
    if "export" in path:
        return "export.operation"
    if "/material/jobs" in path:
        return "task.operation"
    if "/sections/" in path or "/chat-drafts/" in path or path.endswith("/outline"):
        return "draft.operation"
    return None


class ObservabilityMiddleware:
    """Pure ASGI: observe final body send, never buffer or inspect response content."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not enabled():
            return await self.app(scope, receive, send)
        import asyncio
        request_id = uuid.uuid4().hex
        state = {"trace_id": request_id, "http_request_id": request_id, "events": []}
        token = context.set(state)
        scope.setdefault("state", {})["observability"] = state
        kind = operation(scope["path"], scope["method"])
        started, http_status, size, complete = time.monotonic(), 500, 0, False
        if kind:
            emit(kind, status="started", stage="received")

        async def observe(message):
            nonlocal http_status, size, complete
            if message["type"] == "http.response.start":
                http_status = message["status"]
                headers = list(message.get("headers", []))
                headers.extend([(b"x-request-id", request_id.encode()),
                                (b"x-trace-id", state["trace_id"].encode())])
                if http_status >= 400:
                    headers.append((b"x-support-id", request_id.encode()))
                message = {**message, "headers": headers}
            elif message["type"] == "http.response.body":
                size += len(message.get("body", b""))
            await send(message)
            if message["type"] == "http.response.body":
                complete = not message.get("more_body", False)
        try:
            await self.app(scope, receive, observe)
        finally:
            if kind:
                emit(kind, status="completed" if complete and http_status < 400 else "failed",
                     level="error" if http_status >= 500 or not complete else "warning" if http_status >= 400 else "info",
                     stage="response_returned" if complete else "response_interrupted",
                     http_status=http_status, duration_ms=(time.monotonic()-started)*1000,
                     metadata={"response_bytes": size})
            events = enrich(state["events"], state)
            try:
                # Awaited, bounded telemetry only; never submit identity/billing work to a background thread.
                if events:
                    await asyncio.to_thread(send_events, events)
            finally:
                context.reset(token)
