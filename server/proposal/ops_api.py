"""Narrow metadata-only operations API. No user JWT, model or wallet mutation."""
import urllib.error
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import observability as obs


class Receipt(BaseModel):
    event_count: int = Field(ge=1, le=5000)
    plaintext_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    ciphertext_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    key_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class UploadEvent(BaseModel):
    event_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    trace_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    owner_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    project_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    occurred_at: datetime
    event: str = Field(pattern=r"^upload\.(started|completed|failed)$")
    stage: str = Field(default="transfer", pattern=r"^[a-z_]{1,64}$")
    status: str = Field(pattern=r"^(started|completed|failed)$")
    http_status: int | None = Field(default=None, ge=100, le=599)
    metadata: dict = Field(default_factory=dict)


def register_ops_api(app):
    router = APIRouter(prefix="/api/ops/logs")

    def call(authorization, action, args=None):
        if not obs.enabled():
            raise HTTPException(503, "业务日志尚未启用")
        scheme, _, key = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not 32 <= len(key) <= 256:
            raise HTTPException(403, "运维凭据无效")
        try:
            return obs.rpc(key, action, args or {})
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise HTTPException(403, "运维凭据无效或权限不足") from None
            raise HTTPException(409 if action == "ack" else 503, "日志服务请求未完成；未绕过归档校验") from None
        except (TimeoutError, OSError, ValueError, RuntimeError):
            raise HTTPException(503, "日志服务暂不可用；没有执行未经确认的清理") from None

    @router.get("")
    @router.get("/events")
    def events(authorization: str | None = Header(default=None), since: datetime | None = None,
               until: datetime | None = None, operation: str | None = Query(None, pattern=r"^[a-z_]{1,40}$"),
               job_id: str | None = Query(None, pattern=r"^[a-f0-9]{32}$"),
               usage_request_id: str | None = Query(None, pattern=r"^[a-zA-Z0-9_:-]{1,100}$"),
               owner_id: str | None = Query(None, pattern=r"^[a-f0-9-]{36}$"),
               error_code: str | None = Query(None, pattern=r"^[A-Z_]{1,80}$"),
               level: str | None = Query(None, pattern=r"^(info|warning|error)$"),
               environment: str | None = Query(None, pattern=r"^(production|preview|local|test)$"),
               after_time: datetime | None = None,
               after_id: str | None = Query(None, pattern=r"^[a-f0-9-]{36}$"),
               limit: int = Query(200, ge=1, le=200)):
        args = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in locals().items()
                if k != "authorization" and v is not None}
        return call(authorization, "list", args)

    @router.get("/traces/{trace_id}")
    def trace(trace_id: str, authorization: str | None = Header(default=None),
              after_time: datetime | None = None, after_id: str | None = None):
        if not obs.ID.fullmatch(trace_id):
            raise HTTPException(422, "追踪编号无效")
        return call(authorization, "trace", {"trace_id": trace_id, "after_time": after_time.isoformat() if after_time else None,
                                            "after_id": after_id})

    @router.get("/stats")
    @router.get("/archive/status")
    def stats(authorization: str | None = Header(default=None), since: datetime | None = None):
        return call(authorization, "stats", {"since": since.isoformat()} if since else {})

    @router.post("/archive/batches")
    def claim(authorization: str | None = Header(default=None)):
        return {"batch": call(authorization, "claim")}

    @router.get("/archive/inventory")
    def inventory(authorization: str | None = Header(default=None),
                  after_time: datetime | None = None,
                  after_id: str | None = Query(None, pattern=r"^[a-f0-9-]{36}$")):
        return call(authorization, "inventory", {
            "after_time": after_time.isoformat() if after_time else None, "after_id": after_id})

    @router.get("/archive/batches/{batch_id}")
    def page(batch_id: str, offset: int = Query(0, ge=0, le=5000),
             authorization: str | None = Header(default=None)):
        if not obs.ID.fullmatch(batch_id):
            raise HTTPException(422, "批次编号无效")
        return call(authorization, "page", {"batch_id": batch_id, "offset": offset})

    @router.post("/archive/batches/{batch_id}/ack")
    def ack(batch_id: str, payload: Receipt, authorization: str | None = Header(default=None)):
        if not obs.ID.fullmatch(batch_id):
            raise HTTPException(422, "批次编号无效")
        return call(authorization, "ack", {"batch_id": batch_id, **payload.model_dump()})

    @router.post("/archive/purge")
    def purge(authorization: str | None = Header(default=None)):
        return call(authorization, "purge")

    @router.post("/ingest")
    def upload(payload: UploadEvent, authorization: str | None = Header(default=None)):
        item = payload.model_dump(mode="json")
        item.update(metadata=obs.safe_meta(payload.metadata), level="error" if payload.status == "failed" else "info",
                    version="unknown", environment="production",
                    error_code=obs.error_code(http_status=payload.http_status)[0] if payload.status == "failed" else None)
        return call(authorization, "append", {"events": [item]})

    app.include_router(router)
