from __future__ import annotations

import json
import hashlib
import hmac
import ipaddress
import logging
import os
import re
import sys
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Callable, Literal, TypeVar

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import mimetypes
from pydantic import BaseModel, Field
from fastapi.exceptions import RequestValidationError

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = Path(__file__).resolve().parent
STATIC_DIR = SERVER_DIR / "static"
ASSET_VERSIONS = {
    name: hashlib.sha256((STATIC_DIR / name).read_bytes()).hexdigest()[:16]
    for name in ("app.js", "app.css", "material.js")
}
MICRO_CNY_PER_CREDIT = 100_000  # 1 CNY = 10 workbench credits
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from proposal.agent import ModelUnavailable, OllamaAgent
from proposal.documents import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, Extraction, extract_file
from proposal.exporter import export_project
from proposal.credit_security import (
    CreditSecurityConfigError,
    card_code_digest,
    decrypt_card_code,
    encrypt_card_code,
    extract_workbench_voucher_code,
    normalize_card_code,
    workbench_voucher_digest,
)
from proposal.retrieval import ProjectRetriever
from proposal.storage import CreditRateLimitError, InsufficientCreditsError, PendingUsageError, Store
from proposal.supabase_store import SupabaseStore, request_identity
from proposal.workbench_metering import WorkbenchMeter
from proposal.workbench_images import generate_image, generate_custom_image
from proposal.wopally_usage import UsageUnavailable, WopallyUsage
from proposal.official_pricing import official_v1_charge, official_2x_charge
from proposal.wopally_transport import wopally_urlopen
from proposal.tools import ProposalTools
from proposal.jobs import GenerationJobRunner
from proposal.materials import MaterialConflict, enabled as material_enabled
from proposal.skills import normalize_skill_id, registry as skill_registry, valid_fact_key
from proposal.wopally_client import WopallyCardRejected, WopallyClient, WopallyUnavailable

try:
    from utils.dispatcher import Dispatcher
except Exception:  # pragma: no cover - runtime diagnostic endpoint only
    Dispatcher = None  # type: ignore[assignment,misc]


class CreateProject(BaseModel):
    title: str = Field(default="", max_length=160)
    level: str = Field(default="", max_length=40)
    discipline: str = Field(default="", max_length=100)
    school: str = Field(default="", max_length=120)
    has_template: bool | None = None
    skill_id: str = Field(default="", max_length=100)
    initial_request: str = Field(default="", max_length=4000)


class RouteRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


class LLMConfigInput(BaseModel):
    provider: Literal["ollama", "openai_compatible", "preset"] = "preset"
    model: str = Field(default="deepseek-chat", max_length=160)
    base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=1000)
    image_model: str = Field(default="", max_length=160)
    image_base_url: str = Field(default="", max_length=500)
    image_api_key: str = Field(default="", max_length=1000)
    image_reuse_text: bool = False


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    llm_config: LLMConfigInput | None = None
    stream: bool = False


class LLMRequest(BaseModel):
    llm_config: LLMConfigInput | None = None


class StorageDocumentInput(BaseModel):
    document_id: str = Field(min_length=12, max_length=80)
    original_name: str = Field(min_length=1, max_length=255)
    storage_path: str = Field(min_length=8, max_length=600)
    kind: Literal["source", "template", "photo"] = "source"
    content_type: str = Field(default="", max_length=150)
    is_leader: bool = False
    process_now: bool = True


class AuthLoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class AuthSignupInput(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=200)
    captcha_token: str | None = None


class DiagramProposalInput(BaseModel):
    title: str = Field(default="技术路线图", max_length=100)
    llm_config: LLMConfigInput | None = None


class GenerateImageInput(BaseModel):
    prompt: str = Field(min_length=5, max_length=2000)
    llm_config: LLMConfigInput | None = None


class ConfirmDocument(BaseModel):
    confirmed: bool
    corrected_text: str | None = Field(default=None, max_length=200000)


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    level: str | None = Field(default=None, max_length=40)
    discipline: str | None = Field(default=None, max_length=100)
    school: str | None = Field(default=None, max_length=120)


class OutlineUpdate(BaseModel):
    outline: list[dict[str, str]]


class SectionUpdate(BaseModel):
    content: str = Field(max_length=30000)
    expected_revision: int | None = None
    base_content: str | None = Field(default=None, max_length=30000)


class CreateJobInput(BaseModel):
    idempotency_key: str = Field(default="", max_length=120)
    llm_config: LLMConfigInput | None = None


class FactConfirm(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=2000)
    source_quote: str = Field(min_length=4, max_length=600)


class DiagramInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    nodes: list[str] = Field(min_length=2, max_length=12)
    diagram_id: str = Field(default="", max_length=80)


class ReferenceConfirm(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = Field(default="", max_length=300)
    doi: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=1000)
    abstract: str = Field(default="", max_length=5000)
    source_type: str = Field(default="paper", max_length=40)
    published_at: str = Field(default="", max_length=80)


class OfficialURLInput(BaseModel):
    url: str = Field(min_length=12, max_length=2000)


class KeywordOnlyEmbedder:
    """Cloud functions cannot assume a private Ollama embedding service is running."""

    @staticmethod
    def embed(_texts: list[str]) -> None:
        return None


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "").strip()
CLOUD_MODE = bool(SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY)
store = (
    SupabaseStore(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)
    if CLOUD_MODE
    else Store()
)
retriever = ProjectRetriever(store, KeywordOnlyEmbedder() if CLOUD_MODE else None)
tools = ProposalTools(store, retriever)
agent = OllamaAgent(store, tools)
job_runner = GenerationJobRunner(store)


def _current_job_runner() -> GenerationJobRunner:
    global job_runner
    if job_runner.store is not store:
        job_runner = GenerationJobRunner(store)
    return job_runner
dispatcher = Dispatcher() if Dispatcher else None

@asynccontextmanager
async def lifespan(application):
    import httpx
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=False,
        headers={"Cookie": ""},
        limits=httpx.Limits(max_connections=40, max_keepalive_connections=10, keepalive_expiry=30),
    ) as client:
        application.state.auth_http = client
        yield
        application.state.auth_http = None


@asynccontextmanager
async def auth_http():
    client = getattr(app.state, "auth_http", None)
    if client is not None:
        yield client
    else:
        # 兼容禁用 ASGI lifespan 的运行器和单元测试。
        import httpx
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, headers={"Cookie": ""}) as client:
            yield client


app = FastAPI(
    lifespan=lifespan,
    title="大学生申报材料 Agent",
    description="本地优先的申报材料工作台：Skill 自动路由、资料识别、项目内检索、章节写作与 Word 草稿。",
    version="0.1.0",
    docs_url=None if CLOUD_MODE else "/docs",
    redoc_url=None if CLOUD_MODE else "/redoc",
    openapi_url=None if CLOUD_MODE else "/openapi.json",
)
logger = logging.getLogger("proposal_agent.credits")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Pydantic 默认把 input 回显；凭据接口不能回显 Key、密码或 token。
    return JSONResponse({"detail": "请求字段格式不正确，请检查输入。"}, status_code=422,
                        headers={"Cache-Control": "no-store"})


@app.middleware("http")
async def require_supabase_session(request: Request, call_next):
    response = await _require_supabase_session(request, call_next)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
    elif request.url.path.startswith("/static/"):
        name = request.url.path.removeprefix("/static/")
        if name in ASSET_VERSIONS and request.query_params.get("v") == ASSET_VERSIONS[name]:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
    return response


@app.exception_handler(MaterialConflict)
async def material_conflict(request: Request, exc: MaterialConflict):
    return JSONResponse({"detail": str(exc)}, status_code=409)


async def _require_supabase_session(request: Request, call_next):
    if not CLOUD_MODE:
        return await call_next(request)
    path = request.url.path
    if (
        path == "/"
        or path in {
            "/health", "/api/health", "/api/config", "/api/skills", "/api/route",
            "/api/models/preset", "/api/pay/notify", "/api/admin/provider-health",
            "/api/auth/login", "/api/auth/signup",
            "/api/ping",
        }
        or path.startswith("/static/")
        or path.startswith("/api/auth/proxy/")
    ):
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    scheme, _, access_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not access_token.strip():
        return JSONResponse({"detail": "请先登录后继续。"}, status_code=401)
    try:
        import httpx

        async with auth_http() as client:
            response = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "apikey": SUPABASE_PUBLISHABLE_KEY,
                    "Authorization": f"Bearer {access_token.strip()}",
                },
                timeout=10,
            )
        if response.status_code != 200:
            return JSONResponse({"detail": "登录已过期，请重新登录。"}, status_code=401)
        verified_user = response.json()
        user_id = verified_user.get("id")
        if not user_id:
            return JSONResponse({"detail": "无法确认登录用户。"}, status_code=401)
    except Exception:
        return JSONResponse({"detail": "暂时无法验证登录状态，请稍后重试。"}, status_code=503)

    context_token = request_identity.set(
        {
            "access_token": access_token.strip(), "user_id": str(user_id),
            # Auth server-owned field, never client metadata or a request header.
            "registered_at": str(verified_user.get("created_at") or ""),
        }
    )
    try:
        return await call_next(request)
    finally:
        request_identity.reset(context_token)


class CreatePayOrderInput(BaseModel):
    plan_id: str
    pay_type: Literal["alipay", "wxpay"] = "alipay"


class RedeemCodeInput(BaseModel):
    code: str = Field(min_length=1, max_length=512)


class Sub2PaymentNotification(BaseModel):
    event_id: str = Field(min_length=8, max_length=160)
    workbench_user_id: str = Field(min_length=1, max_length=128)
    amount_cny: Decimal
    currency: Literal["CNY"] = "CNY"
    status: Literal["paid"]


def _agent_for_config(
    config: LLMConfigInput | None, request: Request | None = None, project_id: str = ""
) -> OllamaAgent:
    if config is None:
        return agent
    model = config.model.strip()
    if config.provider == "preset":
        if not _platform_bundle_ready():
            raise HTTPException(status_code=503, detail="工作台服务账户与实际用量结算尚未接通")
        key_id = int(os.environ["WOPALLY_WORKBENCH_API_KEY_ID"])
        return OllamaAgent(
            store, tools,
            base_url=os.environ["WOPALLY_MODEL_BASE_URL"].rstrip("/"),
            model="deepseek-v4-flash",
            provider="openai_compatible",
            api_key=os.environ["WOPALLY_WORKBENCH_API_KEY"],
            meter=WorkbenchMeter(store, _current_user_id(request), key_id, project_id),
            platform_transport=True,
        )
    if config.provider == "ollama":
        if CLOUD_MODE:
            raise HTTPException(
                status_code=422,
                detail="Vercel 云端版不能连接用户电脑上的 Ollama；请选择自定义 API。Ollama 可用于本机自托管版。",
            )
        if not model:
            model = agent.model
        return OllamaAgent(store, tools, base_url=agent.base_url, model=model)
    if not model or not config.api_key.strip() or not config.base_url.strip():
        raise HTTPException(status_code=422, detail="自定义 API 需要填写 API 地址、模型名称和 API Key。")
    parsed = urllib.parse.urlparse(config.base_url.strip())
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or hostname in {"localhost", "localhost.localdomain"}
        or hostname.endswith(".local")
    ):
        raise HTTPException(status_code=422, detail="自定义 API 地址必须是 HTTPS 根地址，不能包含账号、查询参数或片段。")
    try:
        address = ipaddress.ip_address(hostname)
        if not address.is_global:
            raise HTTPException(status_code=422, detail="自定义 API 地址不能指向本机或私有网络。")
    except ValueError:
        pass
    return OllamaAgent(
        store,
        tools,
        base_url=config.base_url.strip().rstrip("/"),
        model=model,
        provider="openai_compatible",
        api_key=config.api_key.strip(),
    )


def _public_document(document: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: document.get(key)
        for key in (
            "id",
            "original_name",
            "kind",
            "content_type",
            "extracted_text",
            "extraction_status",
            "extraction_warning",
            "low_confidence_count",
            "confirmed",
            "created_at",
            "storage_path",
        )
    }
    result["confirmed"] = bool(result.get("confirmed"))
    return result


def _safe_project(project_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return "<h1>大创 Agent</h1><p>前端正在初始化，请稍后重试。</p>"
    html = index.read_text(encoding="utf-8")
    for filename in ("app.js", "app.css"):
        digest = ASSET_VERSIONS[filename]
        html = html.replace(f'/static/{filename}"', f'/static/{filename}?v={digest}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, must-revalidate"})


@app.get("/api/config")
def app_config() -> dict[str, Any]:
    redemption_enabled = _card_redemption_enabled() or _voucher_redemption_enabled()
    raw_shop_url = os.environ.get("WOPALLY_CARD_SHOP_URL", "").strip()
    parsed_shop_url = urllib.parse.urlparse(raw_shop_url)
    shop_url = (
        raw_shop_url
        if redemption_enabled
        and os.environ.get("WORKBENCH_SHOW_SHOP_LINK", "").lower() == "true"
        and parsed_shop_url.scheme == "https" and parsed_shop_url.hostname
        else ""
    )
    return {
        "cloud_mode": CLOUD_MODE,
        "supabase_url": SUPABASE_URL if CLOUD_MODE else "",
        "supabase_publishable_key": SUPABASE_PUBLISHABLE_KEY if CLOUD_MODE else "",
        "turnstile_site_key": TURNSTILE_SITE_KEY,
        "payment_enabled": False,
        "card_redemption_enabled": redemption_enabled,
        "voucher_redemption_enabled": _voucher_redemption_enabled(),
        "card_shop_url": shop_url,
        "preset_enabled": _platform_bundle_ready(),
        # Enable only after the Cloudflare route, secrets and bucket limit are verified.
        "storage_upload_endpoint": "/uploads/resumable"
        if CLOUD_MODE and os.environ.get("STORAGE_UPLOAD_PROXY_ENABLED", "").lower() == "true" else "",
        "max_upload_bytes": MAX_UPLOAD_BYTES,
    }


def _friendly_auth_error(msg: str) -> str:
    m = msg.lower()
    if "invalid login credentials" in m:
        return "邮箱或密码错误，请重新核对。"
    if "user already registered" in m:
        return "该邮箱已被注册，请直接登录。"
    if "password should be at least" in m:
        return "密码长度至少需要 6 个字符。"
    if "email not confirmed" in m:
        return "该账号邮箱尚未激活，请查收验证邮件。"
    if "rate limit" in m:
        return "操作过于频繁，请稍后再试。"
    return msg or "认证服务请求失败，请稍后重试。"


@app.post("/api/auth/login")
async def auth_login(payload: AuthLoginInput, request: Request) -> dict[str, Any]:
    if not CLOUD_MODE:
        raise HTTPException(status_code=400, detail="本地自托管模式无需登录。")
    email = payload.email.strip().lower()
    req_headers = {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Content-Type": "application/json",
    }

    import httpx

    async with auth_http() as client:
        try:
            resp = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers=req_headers,
                json={"email": email, "password": payload.password},
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="无法连接云端认证服务，请稍后重试。") from exc

    if resp.status_code != 200:
        try:
            err_data = resp.json()
            raw_msg = err_data.get("msg") or err_data.get("error_description") or err_data.get("message") or ""
        except Exception:
            raw_msg = ""
        raise HTTPException(status_code=resp.status_code, detail=_friendly_auth_error(raw_msg))
    return resp.json()


@app.post("/api/auth/signup")
async def auth_signup(payload: AuthSignupInput, request: Request) -> dict[str, Any]:
    if not CLOUD_MODE:
        raise HTTPException(status_code=400, detail="本地自托管模式无需注册。")
    email = payload.email.strip().lower()
    body: dict[str, Any] = {"email": email, "password": payload.password}
    if payload.captcha_token:
        body["gotrue_meta_security"] = {"captcha_token": payload.captcha_token}

    req_headers = {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Content-Type": "application/json",
    }

    import httpx

    async with auth_http() as client:
        try:
            resp = await client.post(
                f"{SUPABASE_URL}/auth/v1/signup",
                headers=req_headers,
                json=body,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="无法连接云端认证服务，请稍后重试。") from exc

    if resp.status_code != 200:
        try:
            err_data = resp.json()
            raw_msg = err_data.get("msg") or err_data.get("error_description") or err_data.get("message") or ""
        except Exception:
            raw_msg = ""
        raise HTTPException(status_code=resp.status_code, detail=_friendly_auth_error(raw_msg))
    return resp.json()


@app.api_route("/api/auth/proxy/{path:path}", methods=["GET", "POST", "PUT"])
async def auth_proxy(path: str, request: Request):
    """SDK 会话刷新、验证和退出也走同源，而不只是首次密码登录。"""
    import httpx
    allowed = {
        "token": {"POST"}, "signup": {"POST"}, "user": {"GET", "PUT"},
        "logout": {"POST"}, "verify": {"POST"}, "recover": {"POST"},
        "resend": {"POST"}, "settings": {"GET"},
        ".well-known/jwks.json": {"GET"},
    }
    if not CLOUD_MODE or request.method not in allowed.get(path, set()):
        raise HTTPException(404, "认证接口不存在。")
    body = await request.body()
    if len(body) > 16384:
        raise HTTPException(413, "请求过大。")
    headers = {"apikey": SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json"}
    authorization = request.headers.get("authorization", "")
    if authorization:
        headers["Authorization"] = authorization
    try:
        async with auth_http() as client:
            upstream = await client.request(
                request.method, f"{SUPABASE_URL}/auth/v1/{path}",
                params=list(request.query_params.multi_items()),
                content=body, headers=headers,
            )
        return Response(
            upstream.content, status_code=upstream.status_code,
            media_type="application/json",
            headers={"Cache-Control": "no-store", **(
                {"Retry-After": upstream.headers["retry-after"]}
                if "retry-after" in upstream.headers else {}
            )},
        )
    except httpx.HTTPError:
        return JSONResponse({"msg": "认证服务暂不可用，请稍后重试。"}, status_code=503)


def _cloud_config_store():
    if not CLOUD_MODE:
        raise HTTPException(400, "本地模式不启用云端凭据同步。")
    return store


@app.api_route("/api/storage/proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def storage_proxy(path: str, request: Request):
    """材料存储请求代理：走同源连接，避免国内浏览器直连 Supabase Storage 遭遇阻断。"""
    if not CLOUD_MODE:
        raise HTTPException(404, "云端存储代理仅在云端模式启用。")
    ident = request_identity.get()
    if not ident or not ident.get("access_token"):
        raise HTTPException(401, "请先登录后操作材料存储。")

    user_id = str(ident["user_id"])
    clean_path = path.lstrip("/")
    expected_prefix = f"object/stardust-project-files/{user_id}/"
    # 严格校验：防越权读写他人目录
    if clean_path.startswith("object/stardust-project-files/") and not clean_path.startswith(expected_prefix):
        raise HTTPException(403, "无权操作其他用户的存储对象。")

    import httpx
    headers = {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": f"Bearer {ident['access_token']}",
    }
    content_type = request.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type
    x_upsert = request.headers.get("x-upsert")
    if x_upsert:
        headers["x-upsert"] = x_upsert

    body = await request.body()
    try:
        async with auth_http() as client:
            upstream = await client.request(
                request.method,
                f"{SUPABASE_URL}/storage/v1/{clean_path}",
                params=list(request.query_params.multi_items()),
                content=body,
                headers=headers,
                timeout=45,
            )
        return Response(
            upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/json"),
            headers={"Cache-Control": "private, no-store"},
        )
    except httpx.HTTPError:
        return JSONResponse({"message": "材料存储服务暂不可用，请稍后重试。"}, status_code=503)


@app.get("/api/user/llm-config")
def get_user_model_config():
    try:
        config = _cloud_config_store().get_model_config()
        return {"config": config}
    except RuntimeError:
        raise HTTPException(503, "云端配置读取失败，请稍后重试。") from None


@app.post("/api/user/llm-config")
def save_user_model_config(payload: LLMConfigInput):
    if payload.provider not in {"openai_compatible", "preset"}:
        raise HTTPException(422, "云端仅支持平台模型或自定义 API。")
    if payload.provider == "openai_compatible":
        # 沿用推理端点的 HTTPS 与私网校验，但不发起模型调用或扣费。
        _agent_for_config(payload)
    config = payload.model_dump()
    if payload.provider == "preset":
        config = {"provider": "preset", "model": "workbench-bundle",
                  "base_url": "", "api_key": "", "image_api_key": ""}
    try:
        _cloud_config_store().save_model_config(config)
    except RuntimeError:
        raise HTTPException(503, "云端配置保存失败，请稍后重试。") from None
    return {"saved": True}


@app.delete("/api/user/llm-config")
def delete_user_model_config():
    try:
        _cloud_config_store().delete_model_config()
    except RuntimeError:
        raise HTTPException(503, "云端配置删除失败，请稍后重试。") from None
    return {"deleted": True}


# 发版标记：凡涉及排版/导出行为的改动 +1。部署后用 /api/ping 核对，
# 不依赖任何环境变量——CLI 直接部署时 Vercel 不会注入 commit sha。
LAYOUT_REV = 1


@app.get("/api/ping")
def ping():
    # 只验证服务存活，不探测 Ollama、数据库或模型，不触发扣费。
    commit = (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "")[:7]
    payload = {"status": "ok", "layout_rev": LAYOUT_REV}
    if commit:
        payload["commit"] = commit
    return payload


@app.get("/api/skills")
def list_skills() -> dict[str, Any]:
    return {"total": len(skill_registry.skills), "skills": skill_registry.list()}


@app.post("/api/route")
def route_skill(payload: RouteRequest) -> dict[str, Any]:
    """Match a natural-language request to a skill, asking for clarification when weak."""
    if not dispatcher:
        raise HTTPException(status_code=503, detail="Skill 路由器不可用")
    routing = dispatcher.route(payload.query, top_n=5)
    matches = routing["candidates"]
    candidates = []
    for item in matches:
        skill = skill_registry.get(item.get("name", ""))
        if not skill:
            continue
        candidates.append(
            {
                "id": skill["id"],
                "name": skill.get("display_name") or skill.get("name", ""),
                "description": skill.get("description", ""),
                "category": skill.get("category", ""),
                "score": int(item.get("score", 0)),
                "matched": item.get("matched", []),
            }
        )
    if not candidates:
        return {
            "selected": None,
            "needs_clarification": True,
            "candidates": [],
            "message": "我还不能确定你要准备哪类材料，请选择赛道，或补充材料名称/用途。",
        }
    selected_id = routing["selected"]
    selected = next((item for item in candidates if item["id"] == selected_id), None)
    return {
        "selected": selected,
        "needs_clarification": selected is None,
        "candidates": candidates[:5],
        "message": "" if selected else "我找到几个可能的赛道，请确认最符合你需求的一项。",
    }


def _extract_uploaded_document(name: str, content: bytes, kind: str) -> Extraction:
    if CLOUD_MODE and kind == "photo":
        return Extraction(
            text="",
            warning="云端版保留照片原图，暂不对照片执行 OCR。",
            status="ready",
        )
    return extract_file(name, content)


def _document_extraction_error(exc: Exception) -> str:
    if CLOUD_MODE and any(
        marker in str(exc).lower()
        for marker in ("pypdfium2", "rapidocr", "onnxruntime", "no module named")
    ):
        return "云端测试版暂不支持扫描件 OCR。请上传可复制文字的 Word/PDF，或粘贴识别后的文字。"
    return str(exc)


@app.get("/health")
def health() -> dict[str, Any]:
    skills_loaded = 35
    if dispatcher:
        skills_loaded = len(dispatcher.skills)
    model_status = agent.status()
    return {
        "status": "ok",
        "skills_loaded": skills_loaded,
        "ollama_available": model_status["running"],
        "ollama_model": model_status["model"],
        "ollama_model_installed": model_status["model_installed"],
        "ollama_local": model_status["local"],
    }


def _current_user_id(request: Request | None) -> str:
    ident = request_identity.get()
    if ident and ident.get("user_id"):
        return str(ident["user_id"])
    # Local-only single-user development mode; never trust a client-supplied identity.
    return "local_user"


def _require_admin(request: Request) -> None:
    expected = os.environ.get("ADMIN_DASHBOARD_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="管理员报表未配置")
    import hmac
    provided = request.headers.get("x-admin-token", "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="无权查看管理员报表")


def _allowed_wopally_card_values() -> set[Decimal]:
    raw = os.environ.get("WOPALLY_ALLOWED_CARD_VALUES_CNY", "")
    values: set[Decimal] = set()
    for item in raw.split(","):
        try:
            value = Decimal(item.strip()).quantize(Decimal("0.000001"))
            if value > 0:
                values.add(value)
        except (InvalidOperation, ValueError):
            continue
    return values


def _card_redemption_enabled() -> bool:
    required = (
        os.environ.get("WORKBENCH_CARD_REDEMPTION_APPROVED", "").lower() == "true"
        and os.environ.get("WORKBENCH_CARD_REDEMPTION_PAUSED", "").lower() != "true"
        and os.environ.get("WOPALLY_REDEEM_API_VERIFIED", "").lower() == "true"
        and bool(
            os.environ.get("WOPALLY_SERVICE_ACCESS_TOKEN", "").strip()
            or (os.environ.get("WOPALLY_SERVICE_EMAIL", "").strip()
                and os.environ.get("WOPALLY_SERVICE_PASSWORD", ""))
        )
        and os.environ.get("WOPALLY_CARD_REDEEM_PATH", "").strip().startswith("/")
        and os.environ.get("WOPALLY_CARD_REDEEM_HISTORY_PATH", "").strip().startswith("/")
        and bool(os.environ.get("WOPALLY_CARD_SHOP_URL", "").strip())
        and bool(os.environ.get("WORKBENCH_REDEEM_ENCRYPTION_KEY", "").strip())
        and bool(_allowed_wopally_card_values())
    )
    if CLOUD_MODE:
        return required and bool(
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.environ.get("WORKBENCH_BACKEND_SECRET", "").strip()
        )
    return required and os.environ.get("WORKBENCH_LOCAL_CARD_REDEMPTION", "").lower() == "true"


def _platform_bundle_ready(*, require_ledger: bool = True) -> bool:
    # Explicit operator gate: a credential alone never opens paid inference.
    url = urllib.parse.urlparse(os.environ.get("WOPALLY_MODEL_BASE_URL", ""))
    key_id = os.environ.get("WOPALLY_WORKBENCH_API_KEY_ID", "")
    return (
        os.environ.get("WORKBENCH_MODEL_BUNDLE_READY", "").lower() == "true"
        and os.environ.get("WORKBENCH_MODEL_BUNDLE_PAUSED", "true").lower() == "false"
        and bool(os.environ.get("WOPALLY_WORKBENCH_API_KEY", "").strip())
        and bool(
            os.environ.get("WOPALLY_SERVICE_ACCESS_TOKEN", "").strip()
            or (os.environ.get("WOPALLY_SERVICE_EMAIL", "").strip()
                and os.environ.get("WOPALLY_SERVICE_PASSWORD", ""))
        )
        and key_id.isdigit() and int(key_id) > 0
        and url.scheme == "https" and bool(url.hostname)
        and (not require_ledger or not CLOUD_MODE or bool(
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.environ.get("WORKBENCH_BACKEND_SECRET", "").strip()
        ))
    )


def _voucher_redemption_enabled() -> bool:
    approved = (
        os.environ.get("WORKBENCH_VOUCHERS_APPROVED", "").lower() == "true"
        and os.environ.get("WORKBENCH_VOUCHERS_PAUSED", "true").lower() == "false"
        and os.environ.get("WORKBENCH_MODEL_BUNDLE_READY", "").lower() == "true"
        and os.environ.get("WOPALLY_REDEEM_API_VERIFIED", "").lower() == "true"
        and bool(os.environ.get("WOPALLY_CARD_SHOP_URL", "").strip())
        and bool(os.environ.get("WORKBENCH_REDEEM_ENCRYPTION_KEY", "").strip())
        and bool(os.environ.get("WOPALLY_SERVICE_USER_ID", "").strip())
        and bool(os.environ.get("WOPALLY_CARD_REDEEM_PATH", "").strip())
        and bool(os.environ.get("WOPALLY_CARD_REDEEM_HISTORY_PATH", "").strip())
        and (not CLOUD_MODE or bool(
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            or os.environ.get("WORKBENCH_BACKEND_SECRET", "").strip()
        ))
    )
    return approved and _platform_bundle_ready() and (
        CLOUD_MODE or os.environ.get("WORKBENCH_LOCAL_VOUCHERS", "").lower() == "true"
    )


def _maybe_deduct_credits(
    config: LLMConfigInput | None, request: Request | None, action: str, project_id: str = ""
) -> dict[str, Any] | None:
    # Each upstream request (including tool-call turns) is reserved inside the
    # model transport, not here at the enclosing HTTP action boundary.
    return None


T = TypeVar("T")


def _metered_invoke(
    config: LLMConfigInput | None,
    request: Request | None,
    action: str,
    project_id: str,
    invoke: Callable[[OllamaAgent], T],
) -> T:
    candidate = (
        _agent_for_config(config, request, project_id)
        if config is not None and config.provider == "preset"
        else _agent_for_config(config)
    )
    reservation = _maybe_deduct_credits(config, request, action, project_id)
    try:
        return invoke(candidate)
    except InsufficientCreditsError as exc:
        detail = "积分不足，请充值后继续，或使用自带 API Key。" if action == "chat" else str(exc)
        raise HTTPException(status_code=402, detail=detail) from exc
    except PendingUsageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BaseException:
        if reservation:
            store.add_credits(
                reservation["user_id"], reservation["deducted"],
                action=f"refund:{action}", model=config.model, project_id=project_id,
            )
        raise


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    return health()


@app.post("/api/model-config/test")
def test_model_config(payload: LLMConfigInput) -> dict[str, Any]:
    if payload.provider == "preset":
        if not _platform_bundle_ready():
            raise HTTPException(status_code=503, detail="平台模型暂未开通")
        return {
            "success": True, "provider": "preset", "model": "workbench-bundle",
            "message": "平台配置就绪；实际生成时按积分结算。",
        }
    candidate = _agent_for_config(payload)
    try:
        result = candidate.test_connection()
    except ModelUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # Never echo the submitted API key back to the browser.
    return {
        "success": True,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "message": "连接成功",
    }


@app.get("/api/models/preset")
def get_preset_models() -> dict[str, Any]:
    if not _platform_bundle_ready():
        return {"models": [], "plans": []}
    return {
        "models": [{
            "id": "workbench-bundle", "name": "DeepSeek Flash + GPT Image",
            "available": True, "description": "写作与生图按任务自动路由，按实际用量结算积分",
        }],
        "plans": [],
    }


@app.get("/api/user/balance")
def get_user_balance(request: Request) -> dict[str, Any]:
    user_id = _current_user_id(request)
    try:
        if _platform_bundle_ready():
            for pending in store.pending_workbench_usage(user_id):
                if pending.get("api_key_id") != int(os.environ["WOPALLY_WORKBENCH_API_KEY_ID"]):
                    continue
                try:
                    WorkbenchMeter(store, user_id, int(pending["api_key_id"])).settle(
                        pending["request_id"], pending["model"]
                    )
                except (RuntimeError, ValueError):
                    logger.exception("Pending usage reconciliation failed")
        bal = store.get_workbench_credit_balance(user_id)
        txs = store.get_workbench_credit_transactions(user_id, limit=20)
    except (RuntimeError, PermissionError) as exc:
        raise HTTPException(status_code=503, detail="云端积分账本尚未配置") from exc
    balance_units = int(bal["balance_micro_cny"])
    credited_units = int(bal.get("total_credited_micro_cny", 0))
    spent_units = int(bal.get("total_spent_micro_cny", 0))
    free_chats = int(bal.get("free_chat_count", 0))
    return {
        "user_id": user_id,
        "credits": round(balance_units / MICRO_CNY_PER_CREDIT, 4),
        "total_credited": round(credited_units / MICRO_CNY_PER_CREDIT, 4),
        "total_consumed": round(spent_units / MICRO_CNY_PER_CREDIT, 4),
        "free_chats_remaining": free_chats,
        "billing_mode": "trial" if bal.get("trial_eligible") else "credits",
        "transactions": txs,
    }


@app.get("/api/pay/orders/{order_id}")
def get_payment_order(order_id: str, request: Request) -> dict[str, Any]:
    if CLOUD_MODE:
        raise HTTPException(status_code=503, detail="云端支付账本尚未接通")
    order = store.get_order(order_id)
    if not order or order["user_id"] != _current_user_id(request):
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"order_id": order_id, "status": order["status"], "credits_added": order["credits_added"]}


@app.post("/api/pay/create")
def create_payment_order(payload: CreatePayOrderInput, request: Request) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail="已切换为卡密兑换，直接支付接口已关闭")


@app.post("/api/pay/notify")
async def payment_notify(request: Request) -> Response:
    """Credit a workbench wallet only from a verified, paid Sub2 event.

    The payment provider must sign the exact raw JSON body with HMAC-SHA256
    using SUB2_PAYMENT_WEBHOOK_SECRET and include it as
    ``X-Sub2-Payment-Signature: sha256=<hex>``. Never expose that secret to the
    browser. event_id is globally idempotent to prevent replay across users.
    """
    if not CLOUD_MODE:
        raise HTTPException(status_code=503, detail="云端付款入账未启用")
    secret = os.environ.get("SUB2_PAYMENT_WEBHOOK_SECRET", "").encode("utf-8")
    if not secret:
        raise HTTPException(status_code=503, detail="付款回调尚未配置")
    raw_body = await request.body()
    supplied = request.headers.get("x-sub2-payment-signature", "").strip()
    if supplied.lower().startswith("sha256="):
        supplied = supplied[7:]
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(supplied.lower(), expected):
        raise HTTPException(status_code=401, detail="付款回调签名无效")
    try:
        payload = Sub2PaymentNotification.model_validate_json(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="付款回调内容无效") from exc

    amount = payload.amount_cny
    max_amount = Decimal(os.environ.get("SUB2_PAYMENT_MAX_CNY", "10000"))
    if amount <= 0 or amount > max_amount:
        raise HTTPException(status_code=400, detail="付款金额超出允许范围")
    amount_micro_cny = int((amount * Decimal(1_000_000)).to_integral_value())
    if Decimal(amount_micro_cny) != amount * Decimal(1_000_000):
        raise HTTPException(status_code=400, detail="付款金额精度无效")

    try:
        result = store.grant_workbench_payment_credits(
            payload.workbench_user_id, payload.event_id, amount_micro_cny
        )
    except (RuntimeError, PermissionError) as exc:
        raise HTTPException(status_code=503, detail="积分账本暂不可用") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return JSONResponse(
        {
            "success": True,
            "duplicate": bool(result.get("duplicate")),
            "workbench_user_id": payload.workbench_user_id,
            "credits_added": round(
                int(result.get("credited_micro_cny", amount_micro_cny)) / MICRO_CNY_PER_CREDIT, 4
            ),
            "balance": round(int(result["balance_micro_cny"]) / MICRO_CNY_PER_CREDIT, 4),
        }
    )


@app.post("/api/pay/redeem")
def redeem_recharge_code(payload: RedeemCodeInput, request: Request) -> dict[str, Any]:
    if "AGT1-" in payload.code.upper():
        try:
            voucher_code = extract_workbench_voucher_code(payload.code)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not _voucher_redemption_enabled():
            raise HTTPException(status_code=503, detail="工作台卡密尚未启用")
        user_id = _current_user_id(request)
        try:
            digest = workbench_voucher_digest(voucher_code)
            voucher = store.lookup_paired_voucher(digest)
            if voucher["status"] == "redeemed":
                if str(voucher["redeemed_by"]) != user_id:
                    raise ValueError("卡密已被其他用户兑换。")
                balance = store.get_workbench_credit_balance(user_id)
                return {
                    "success": True, "duplicate": True, "credits_added": 0,
                    "balance": round(int(balance["balance_micro_cny"]) / MICRO_CNY_PER_CREDIT, 4),
                    "message": "此卡密已兑换到账。",
                }
            ciphertext = voucher["provider_code_ciphertext"]
            if isinstance(ciphertext, str):
                ciphertext = bytes.fromhex(ciphertext)
            provider_code = decrypt_card_code(ciphertext)
            intent = store.begin_workbench_card_redemption(user_id, digest, ciphertext)
            intent_id = str(intent["id"])
            if intent.get("status") == "credited":
                balance = store.get_workbench_credit_balance(user_id)
                return {"success": True, "duplicate": True, "credits_added": 0,
                        "balance": round(int(balance["balance_micro_cny"]) / MICRO_CNY_PER_CREDIT, 4),
                        "message": "此卡密已兑换到账。"}
            client = WopallyClient()
            if intent.get("duplicate"):
                # Never submit an uncertain provider request twice. Only this
                # service account's confirmed redemption history can recover it.
                previous = client.find_redeemed_balance_code(provider_code)
                if not previous or previous.get("type") != "balance":
                    return JSONResponse(
                        {"success": False, "pending": True, "message": "兑换结果待核对，请勿重复提交。"},
                        status_code=202,
                    )
                provider_face = Decimal(str(previous["value_cny"]))
                provider_user_id = int(os.environ["WOPALLY_SERVICE_USER_ID"])
            else:
                upstream = client.redeem_balance_code(provider_code)
                provider_face = Decimal(str(upstream["value_cny"]))
                provider_user_id = upstream.get("provider_user_id")
            expected_user_id = int(os.environ["WOPALLY_SERVICE_USER_ID"])
            value_micro = int(provider_face * 1_000_000)
            if (
                provider_face * 1_000_000 != value_micro
                or value_micro != int(voucher["face_value_micro_cny"])
                or provider_user_id != expected_user_id
            ):
                store.set_workbench_card_redemption_status(
                    intent_id, "needs_review", "上游面值或接收账户不匹配"
                )
                raise HTTPException(status_code=409, detail="上游兑换结果待人工核对，暂未发放积分。")
            redeemed = store.complete_paired_voucher(intent_id, value_micro, expected_user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except CreditSecurityConfigError as exc:
            raise HTTPException(status_code=503, detail="卡密加密配置不完整") from exc
        except WopallyCardRejected as exc:
            # A rejected redemption may mean a code was already redeemed by
            # the service account; retain the intent for reconciliation.
            raise HTTPException(status_code=409, detail="中转站拒绝卡密，结果待核对。") from exc
        except WopallyUnavailable as exc:
            raise HTTPException(status_code=503, detail="中转站兑换结果待核对，请勿重复提交。") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        credited = value_micro
        balance = int(redeemed["balance_micro_cny"])
        return {
            "success": True,
            "duplicate": bool(redeemed.get("duplicate")),
            "credits_added": round(credited / MICRO_CNY_PER_CREDIT, 4),
            "balance": round(balance / MICRO_CNY_PER_CREDIT, 4),
            "message": "卡密已兑换到账。" if redeemed.get("duplicate")
                else f"兑换成功，到账 {round(credited / MICRO_CNY_PER_CREDIT, 4)} 积分。",
        }
    if not _card_redemption_enabled():
        raise HTTPException(
            status_code=400,
            detail="该卡密暂不能在工作台兑换；请核对店铺发放内容并保留付款订单。",
        )
    user_id = _current_user_id(request)
    client = WopallyClient()
    try:
        normalized = normalize_card_code(payload.code)
        digest = card_code_digest(normalized)
        ciphertext = encrypt_card_code(normalized)
        intent = store.begin_workbench_card_redemption(user_id, digest, ciphertext)
        intent_id = str(intent["id"])
        if intent.get("status") == "credited":
            balance = store.get_workbench_credit_balance(user_id)
            return {
                "success": True,
                "duplicate": True,
                "balance": round(int(balance["balance_micro_cny"]) / MICRO_CNY_PER_CREDIT, 4),
                "message": "此卡密已经兑换到账。",
            }
        if intent.get("status") == "rejected":
            raise HTTPException(status_code=400, detail=intent.get("safe_message") or "此卡密无效或已使用")
        if intent.get("duplicate"):
            saved = store.get_workbench_redemption_intent(intent_id, user_id)
            try:
                recovered_code = decrypt_card_code(bytes(saved["code_ciphertext"])) if saved else ""
                previous = client.find_redeemed_balance_code(recovered_code) if recovered_code else None
            except Exception:
                previous = None
            if previous and previous.get("type") == "balance" and previous.get("value_cny") is not None:
                face = Decimal(str(previous["value_cny"])).quantize(Decimal("0.000001"))
            else:
                return JSONResponse(
                    {"success": False, "pending": True, "message": "兑换结果正在核对，请勿重复提交。"},
                    status_code=202,
                )
        else:
            provider_result = client.redeem_balance_code(normalized)
            face = Decimal(str(provider_result["value_cny"])).quantize(Decimal("0.000001"))
        if face not in _allowed_wopally_card_values():
            store.set_workbench_card_redemption_status(
                intent_id, "needs_review", "兑换面值不在已批准范围内"
            )
            logger.error("Wopally card redemption needs review: unapproved face value; intent_id=%s", intent_id)
            raise HTTPException(status_code=409, detail="卡密已在中转站兑换，面值待人工核对。")
        value_micro = int(face * 1_000_000)
        provider_user_id = (
            provider_result.get("provider_user_id")
            if "provider_result" in locals()
            else os.environ.get("WOPALLY_SERVICE_USER_ID")
        )
        completed = store.complete_workbench_card_redemption(
            intent_id, value_micro, int(provider_user_id) if provider_user_id else None
        )
        balance = store.get_workbench_credit_balance(user_id)
        return {
            "success": True,
            "duplicate": bool(completed.get("duplicate")),
            "credits_added": round(value_micro / MICRO_CNY_PER_CREDIT, 4),
            "balance": round(int(balance["balance_micro_cny"]) / MICRO_CNY_PER_CREDIT, 4),
            "message": f"兑换成功，到账 {round(value_micro / MICRO_CNY_PER_CREDIT, 4)} 积分。",
        }
    except CreditSecurityConfigError as exc:
        raise HTTPException(status_code=503, detail="卡密安全配置不完整") from exc
    except WopallyCardRejected as exc:
        try:
            if "intent_id" in locals():
                store.set_workbench_card_redemption_status(intent_id, "rejected", str(exc))
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WopallyUnavailable as exc:
        try:
            if "intent_id" in locals():
                store.set_workbench_card_redemption_status(intent_id, "needs_review", "中转站兑换结果待核对")
                logger.error("Wopally card redemption outcome needs review; intent_id=%s", intent_id)
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="暂时无法确认兑换结果，请勿重复提交，稍后刷新或联系客服。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CreditRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="云端积分账本暂不可用，请稍后重试。") from exc


@app.post("/api/pay/card-fingerprint")
def card_fingerprint(payload: RedeemCodeInput) -> dict[str, str]:
    """A safe paid-pilot reference: never submit or redeem the bearer code."""
    try:
        digest = workbench_voucher_digest(extract_workbench_voucher_code(payload.code))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"fingerprint": digest.hex()}


@app.get("/api/admin/profit-summary")
def get_profit_summary(request: Request) -> dict[str, Any]:
    _require_admin(request)
    raise HTTPException(status_code=503, detail="真实卡密销售与上游成本对账尚未接通，暂不提供利润结论")


@app.get("/api/admin/usage-details")
def get_admin_usage_details(
    request: Request, limit: int = 50, offset: int = 0, project_id: str | None = None
) -> dict[str, Any]:
    _require_admin(request)
    stats = store.get_token_stats(project_id)
    logs = store.get_detailed_usage_logs(limit=limit, offset=offset, project_id=project_id)
    return {
        "stats": stats,
        "logs": logs,
        "billing_status": "provider_cost_reconciliation_pending",
    }


@app.get("/api/admin/provider-health")
def get_provider_health(request: Request) -> dict[str, Any]:
    """Read-only diagnostics; never invoke a model or return any credential."""
    _require_admin(request)
    key_id = int(os.environ.get("WOPALLY_WORKBENCH_API_KEY_ID", "0") or 0)
    result: dict[str, Any] = {
        "account_login": False, "usage_query": False,
        "key_bound": False, "models_listed": [],
        "preset_enabled": _platform_bundle_ready(),
    }
    try:
        with wopally_urlopen(urllib.request.Request(
            os.environ.get("WOPALLY_API_URL", "").rstrip("/") + "/health"
        ), timeout=5) as upstream:
            result["station_health_http"] = upstream.status
    except urllib.error.HTTPError as exc:
        result["station_health_http"] = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result["station_health_error"] = type(exc).__name__
    try:
        keys = WopallyClient()._request("/api/v1/keys?page=1&page_size=100")
        rows = keys.get("items", []) if isinstance(keys, dict) else []
        result["account_login"] = True
        result["key_bound"] = any(
            isinstance(row, dict) and int(row.get("id") or 0) == key_id
            and int(row.get("group_id") or 0) == 127 and row.get("status") == "active"
            for row in rows
        )
    except (WopallyUnavailable, ValueError) as exc:
        result["error"] = str(exc)
        return result
    try:
        WopallyUsage().find("health-check-no-charge", key_id, "deepseek-v4-flash")
        result["usage_query"] = True
    except UsageUnavailable:
        pass
    # Validate the user-facing usage API's field contract without calling a
    # model, charging a wallet, or exposing any usage records/credentials.
    try:
        sample = WopallyClient()._request(
            f"/api/v1/usage?page=1&page_size=100&api_key_id={key_id}"
        )
        usage_rows = sample if isinstance(sample, list) else sample.get("items", [])
        audit = {m: {"verified": 0, "unverifiable": 0}
                 for m in ("deepseek-v4-flash", "gpt-image-2")}
        for row in usage_rows:
            if not isinstance(row, dict) or row.get("api_key_id") != key_id:
                continue
            model = row.get("model")
            if model not in audit:
                continue
            try:
                official_2x_charge(row, model)
                audit[model]["verified"] += 1
            except (KeyError, ValueError, TypeError, InvalidOperation):
                audit[model]["unverifiable"] += 1
        result["official_price_sample_audit"] = audit
    except (WopallyUnavailable, ValueError, TypeError):
        result["official_price_sample_audit"] = "unavailable"
    base = os.environ.get("WOPALLY_MODEL_BASE_URL", "").rstrip("/")
    if base.startswith("https://") and os.environ.get("WOPALLY_WORKBENCH_API_KEY"):
        model_request = urllib.request.Request(
            base + "/models",
            headers={"Authorization": f"Bearer {os.environ['WOPALLY_WORKBENCH_API_KEY']}"},
        )
        try:
            with wopally_urlopen(model_request, timeout=8) as response:
                models = json.load(response)
            names = {
                item.get("id") for item in models.get("data", [])
                if isinstance(item, dict)
            }
            result["models_listed"] = sorted(
                name for name in ("deepseek-v4-flash", "gpt-image-2") if name in names
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError):
            pass
    return result


@app.get("/api/projects/{project_id}/usage")
def get_project_usage(project_id: str, limit: int = 50) -> dict[str, Any]:
    _safe_project(project_id)
    stats = store.get_token_stats(project_id)
    logs = store.get_detailed_usage_logs(limit=limit, project_id=project_id)
    return {
        "project_id": project_id,
        "stats": stats,
        "logs": logs,
    }


@app.post("/api/projects")
def create_project(payload: CreateProject) -> dict[str, Any]:
    requested_skill = normalize_skill_id(payload.skill_id) or "innovation-research"
    selected_skill = skill_registry.get(requested_skill)
    if not selected_skill:
        raise HTTPException(status_code=422, detail="未找到该申报赛道")
    project_title = payload.title.strip()
    default_title = (
        "我的大创项目"
        if selected_skill["id"] == "innovation-research"
        else f"我的{selected_skill.get('display_name') or '申报'}项目"
    )
    project = store.create_project(
        title=project_title or default_title,
        level=payload.level,
        discipline=payload.discipline,
        school=payload.school,
    )
    state = dict(project["state"])
    state["skill_id"] = selected_skill["id"]
    state["skill_name"] = selected_skill.get("display_name") or selected_skill.get("name", "")
    state["skill_category"] = selected_skill.get("category", "")
    if payload.initial_request.strip():
        state["initial_request"] = payload.initial_request.strip()
    state["template_preference"] = (
        "not_asked"
        if payload.has_template is None
        else "has_template" if payload.has_template else "generic"
    )
    if project_title and project_title != "我的大创项目":
        state["project_name"] = project_title
        state["confirmed_facts"] = {"project_name": project_title}
        state["fact_sources"] = {"project_name": "学生在新建项目表单中填写"}
    store.update_project(project["id"], state=state)
    if payload.initial_request.strip():
        greeting = f"已为你选择「{state['skill_name']}」赛道。接下来我会按该赛道要求收集信息并协助撰写；先从你刚才的需求开始。"
    elif state["template_preference"] == "has_template":
        greeting = f"好，我们按「{state['skill_name']}」赛道和学校模板来。请上传模板，再告诉我你目前准备到哪一步。"
    elif state["template_preference"] == "generic":
        greeting = f"好，我们开始准备「{state['skill_name']}」。没有模板时先使用通用结构，并提醒你提交前核对学校要求。你可以先说说目前已有的材料或想法。"
    else:
        greeting = f"我们先一步一步准备「{state['skill_name']}」。你可以先说说目前的想法，或上传已有材料。"
    store.add_message(project["id"], "assistant", greeting)
    project = store.get_project(project["id"]) or project
    return project


@app.post("/api/projects/start")
def start_conversation_project() -> dict[str, Any]:
    """Start with a conversational template question instead of a long setup form."""
    project = store.create_project()
    state = dict(project["state"])
    state["template_preference"] = "not_asked"
    store.update_project(project["id"], state=state)
    greeting = (
        "你好！我们先一步一步来。首先想确认：你手头有学校下发的大创申报模板吗？"
        "有的话可以在聊天框下方点“添加材料”，选择“学校模板”上传；没有的话，我会使用通用模板并提醒你提交前核对。"
    )
    store.add_message(project["id"], "assistant", greeting)
    result = store.get_project(project["id"]) or project
    result["messages"] = store.messages(project["id"])
    return result


@app.get("/api/projects")
def list_projects() -> dict[str, Any]:
    return {"projects": store.list_projects()}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    project = _safe_project(project_id)
    raw_docs = store.list_documents(project_id)
    for d in raw_docs:
        if not material_enabled(project) and not d.get("confirmed") and d.get("extracted_text", "").strip() and d.get("kind") != "template":
            try:
                store.update_document_extraction(
                    d["id"],
                    d["extracted_text"],
                    d.get("extraction_status", "ready"),
                    d.get("extraction_warning", ""),
                    d.get("low_confidence_count", 0),
                    confirmed=True,
                )
                retriever.index_document(d["id"], d["extracted_text"])
                d["confirmed"] = True
            except Exception:
                pass
    project["documents"] = [_public_document(d) for d in raw_docs]
    project["messages"] = store.messages(project_id, limit=80)
    return project


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate) -> dict[str, Any]:
    _safe_project(project_id)
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    project = store.update_project(project_id, **fields)
    return project or {}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, bool]:
    return {"deleted": store.delete_project(project_id)}


@app.post("/api/projects/{project_id}/documents")
async def upload_documents(
    project_id: str,
    files: list[UploadFile] = File(...),
    kind: str = "source",
) -> dict[str, Any]:
    _safe_project(project_id)
    if kind not in {"source", "template", "photo"}:
        raise HTTPException(status_code=400, detail="kind 只能是 source、template 或 photo")
    if not files or len(files) > 12:
        raise HTTPException(status_code=400, detail="一次可上传 1–12 个文件")
    project_folder = store.files_dir / project_id
    project_folder.mkdir(parents=True, exist_ok=True)
    results = []
    for upload in files:
        name = Path(upload.filename or "upload").name
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"不支持文件类型：{ext or '无扩展名'}")
        content = await upload.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"{name} 超过 50 MB")
        if kind == "photo" and ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(status_code=415, detail="项目照片只支持 PNG/JPG/WebP")
        document_id = os.urandom(16).hex()
        stored_path = project_folder / f"{document_id}{ext}"
        stored_path.write_bytes(content)
        document = store.add_document(
            project_id,
            name,
            str(stored_path),
            kind,
            mimetypes.guess_type(name)[0] or "application/octet-stream",
            document_id=document_id,
        )
        try:
            extraction = _extract_uploaded_document(name, content, kind)
            # 自动确认并入库建立检索索引，无需用户手动确认
            confirmed = True if kind == "template" else (
                bool(extraction.text.strip()) and not material_enabled(_safe_project(project_id)))
            store.update_document_extraction(
                document_id,
                extraction.text,
                extraction.status,
                extraction.warning,
                extraction.low_confidence_count,
                confirmed=confirmed,
            )
            if confirmed and extraction.text.strip():
                chunks = retriever.index_document(document_id, extraction.text)
            else:
                chunks = 0
            if kind == "template":
                store.set_template_document(project_id, document_id)
                current_project = store.get_project(project_id)
                if current_project:
                    current_state = dict(current_project["state"])
                    current_state["template_preference"] = "has_template"
                    current_state["template_answer"] = f"已上传模板：{name}"
                    store.update_project(project_id, state=current_state)
            updated = store.get_document(document_id) or document
            results.append(
                {
                    "document": _public_document(updated),
                    "chunk_count": chunks,
                    "needs_confirmation": False,
                }
            )
        except Exception as exc:
            store.update_document_extraction(
                document_id,
                "",
                "error",
                _document_extraction_error(exc),
                0,
                confirmed=False,
            )
            results.append(
                {
                    "document": _public_document(store.get_document(document_id) or document),
                    "chunk_count": 0,
                    "needs_confirmation": True,
                    "error": _document_extraction_error(exc),
                }
            )
    return {"documents": results, "note": "材料已上传并自动建立检索。"}


@app.post("/api/projects/{project_id}/leader-photo")
async def upload_leader_photo(
    project_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    project = _safe_project(project_id)
    name = Path(file.filename or "photo.png").name
    ext = Path(name).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=415, detail="照片只支持 PNG/JPG/WebP")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{name} 超过 50 MB")
    project_folder = store.files_dir / project_id
    project_folder.mkdir(parents=True, exist_ok=True)
    document_id = os.urandom(16).hex()
    stored_path = project_folder / f"{document_id}{ext}"
    stored_path.write_bytes(content)

    old_photo_id = project.get("state", {}).get("leader_photo")
    if old_photo_id:
        try:
            store.delete_document(old_photo_id)
            for old_f in project_folder.glob(f"{old_photo_id}.*"):
                old_f.unlink(missing_ok=True)
        except Exception:
            pass

    document = store.add_document(
        project_id,
        name,
        str(stored_path),
        "photo",
        mimetypes.guess_type(name)[0] or "image/png",
        document_id=document_id,
    )
    store.update_document_extraction(
        document_id,
        "",
        "ready",
        "",
        0,
        confirmed=True,
    )
    state = dict(project["state"])
    state["leader_photo"] = document_id
    confirmed = dict(state.get("confirmed_facts", {}))
    confirmed["leader_photo"] = document_id
    state["confirmed_facts"] = confirmed
    state.setdefault("fact_sources", {})
    state["fact_sources"]["leader_photo"] = "用户在网页中上传负责人照片"
    store.update_project(project_id, state=state)
    return {
        "success": True,
        "document_id": document_id,
        "document": _public_document(store.get_document(document_id) or document),
        "url": f"/api/documents/{document_id}/file",
    }


@app.delete("/api/projects/{project_id}/leader-photo")
def delete_leader_photo(project_id: str) -> dict[str, Any]:
    project = _safe_project(project_id)
    photo_id = project.get("state", {}).get("leader_photo")
    if photo_id:
        store.delete_document(photo_id)
        project_folder = store.files_dir / project_id
        for old_f in project_folder.glob(f"{photo_id}.*"):
            old_f.unlink(missing_ok=True)
        state = dict(project["state"])
        state.pop("leader_photo", None)
        confirmed = dict(state.get("confirmed_facts", {}))
        confirmed.pop("leader_photo", None)
        state["confirmed_facts"] = confirmed
        store.update_project(project_id, state=state)
    return {"success": True}


@app.post("/api/projects/{project_id}/documents/from-storage")
def register_cloud_upload(project_id: str, payload: StorageDocumentInput) -> dict[str, Any]:
    _safe_project(project_id)
    if not hasattr(store, "register_document"):
        raise HTTPException(status_code=400, detail="此接口仅用于云端直传材料。")
    try:
        document = store.register_document(
            project_id=project_id,
            document_id=payload.document_id,
            original_name=Path(payload.original_name).name,
            storage_path=payload.storage_path,
            kind=payload.kind,
            content_type=payload.content_type or mimetypes.guess_type(payload.original_name)[0] or "",
            download=False,
        )
        if payload.is_leader:
            current_project = store.get_project(project_id)
            current_state = dict(current_project["state"])
            current_state["leader_photo"] = document["id"]
            confirmed_facts = dict(current_state.get("confirmed_facts", {}))
            confirmed_facts["leader_photo"] = document["id"]
            current_state["confirmed_facts"] = confirmed_facts
            store.update_project(project_id, state=current_state)
        if not payload.process_now:
            return {
                "documents": [{"document": _public_document(document), "chunk_count": 0}],
                "note": "原文件已保存，文字识别单独进行；识别失败不会删除原文件。",
            }
        return _process_cloud_document(document)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"云端材料登记失败：{_document_extraction_error(exc)}",
        ) from exc


def _process_cloud_document(document: dict[str, Any]) -> dict[str, Any]:
    """Processing is separate from upload/registration, and can be retried by ID."""
    document_id = document["id"]
    project_id = document["project_id"]
    try:
        loaded = store.get_document(document_id)
        path = Path(loaded["stored_path"])
        if path.stat().st_size > MAX_UPLOAD_BYTES:
            raise ValueError("单个文件最大支持 50 MB。")
        file_bytes = path.read_bytes()
        extraction = _extract_uploaded_document(document["original_name"], file_bytes, document["kind"])
        # 自动确认并入库建立检索索引，无需用户手动确认
        confirmed = True if document["kind"] == "template" else (
            bool(extraction.text.strip()) and not material_enabled(_safe_project(project_id)))
        store.update_document_extraction(
            document["id"],
            extraction.text,
            extraction.status,
            extraction.warning,
            extraction.low_confidence_count,
            confirmed=confirmed,
        )
        chunks = (
            retriever.index_document(document["id"], extraction.text)
            if confirmed and extraction.text.strip()
            else 0
        )
        if document["kind"] == "template":
            store.set_template_document(project_id, document["id"])
            current_project = store.get_project(project_id)
            if current_project:
                current_state = dict(current_project["state"])
                current_state["template_preference"] = "has_template"
                current_state["template_answer"] = f"已上传模板：{document['original_name']}"
                store.update_project(project_id, state=current_state)
        updated = store.get_document(document["id"])
        return {
            "documents": [
                {
                    "document": _public_document(updated or document),
                    "chunk_count": chunks,
                    "needs_confirmation": False,
                }
            ],
            "note": "材料已上传并自动建立检索。",
        }
    except Exception as exc:
        warning = _document_extraction_error(exc)
        store.update_document_extraction(document_id, "", "error", warning, 0, confirmed=False)
        return {"documents": [{
            "document": _public_document(store.get_document(document_id, download=False) or document),
            "error": warning, "chunk_count": 0,
        }], "note": "原文件已保存，识别失败可单独重试。"}


@app.post("/api/documents/{document_id}/process")
def process_cloud_document(document_id: str) -> dict[str, Any]:
    if not CLOUD_MODE:
        raise HTTPException(status_code=400, detail="此接口仅用于云端材料。")
    document = store.get_document(document_id, download=False)
    if not document:
        raise HTTPException(status_code=404, detail="材料不存在")
    _safe_project(document["project_id"])
    return _process_cloud_document(document)


@app.patch("/api/documents/{document_id}/confirm")
def confirm_document(document_id: str, payload: ConfirmDocument) -> dict[str, Any]:
    document = store.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="材料不存在")
    if document["kind"] == "template":
        raise HTTPException(status_code=400, detail="Word/PDF 模板不作为项目事实材料索引")
    text = payload.corrected_text if payload.corrected_text is not None else document["extracted_text"]
    if payload.confirmed and not text.strip():
        raise HTTPException(status_code=400, detail="识别文本为空，请补充或取消确认")
    store.update_document_extraction(
        document_id,
        text,
        "ready" if payload.confirmed else document["extraction_status"],
        document["extraction_warning"],
        document["low_confidence_count"],
        confirmed=payload.confirmed,
    )
    chunks = retriever.index_document(document_id, text) if payload.confirmed else 0
    if not payload.confirmed:
        store.replace_chunks(document_id, [])
    if payload.confirmed and document["kind"] == "official":
        match = re.search(r"\[来源链接\]\s*(https://\S+)", text)
        if match:
            project = store.get_project(document["project_id"])
            state_data = dict(project["state"]) if project else {}
            sources = list(state_data.get("official_sources", []))
            if not any(item.get("url") == match.group(1) for item in sources if isinstance(item, dict)):
                sources.append(
                    {
                        "title": document["original_name"].removesuffix(".txt"),
                        "url": match.group(1),
                        "source_type": "official",
                    }
                )
            state_data["official_sources"] = sources
            store.update_project(document["project_id"], state=state_data)
    return {
        "document": _public_document(store.get_document(document_id) or document),
        "indexed_chunks": chunks,
    }


@app.get("/api/documents/{document_id}/file")
def document_file(document_id: str) -> FileResponse:
    document = store.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="材料不存在")
    path = Path(document["stored_path"]).resolve()
    try:
        path.relative_to(store.files_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="材料路径无效") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="材料文件不存在")
    return FileResponse(path, media_type=document["content_type"], filename=document["original_name"])


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str) -> dict[str, bool]:
    document = store.delete_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="材料不存在")
    path = Path(document["stored_path"])
    try:
        path.resolve().relative_to(store.files_dir.resolve())
        path.unlink(missing_ok=True)
    except (ValueError, OSError):
        pass
    project = store.get_project(document["project_id"])
    if project and project.get("template_document_id") == document_id:
        store.set_template_document(document["project_id"], None)
    if project and project.get("state", {}).get("leader_photo") == document_id:
        state_data = dict(project["state"])
        state_data.pop("leader_photo", None)
        confirmed = dict(state_data.get("confirmed_facts", {}))
        confirmed.pop("leader_photo", None)
        state_data["confirmed_facts"] = confirmed
        store.update_project(document["project_id"], state=state_data)
    if project and document["kind"] == "official":
        match = re.search(r"\[来源链接\]\s*(https://\S+)", document["extracted_text"])
        if match:
            state_data = dict(project["state"])
            state_data["official_sources"] = [
                source
                for source in state_data.get("official_sources", [])
                if not isinstance(source, dict) or source.get("url") != match.group(1)
            ]
            store.update_project(document["project_id"], state=state_data)
    return {"deleted": True}


@app.post("/api/projects/{project_id}/chat")
def chat(project_id: str, payload: ChatInput, request: Request) -> dict[str, Any]:
    project = _safe_project(project_id)
    text = payload.message.strip()
    state = dict(project["state"])
    fields: dict[str, Any] = {}
    template_preference = state.get("template_preference", "generic")
    normalized = re.sub(r"\s+", "", text).lower()
    mentions_template = "模板" in normalized
    negative_template = mentions_template and any(
        marker in normalized for marker in ("没有", "没", "无模板", "不需要", "通用模板")
    )
    positive_template = mentions_template and any(
        marker in normalized for marker in ("有", "收到", "已经拿到")
    )
    if template_preference == "not_asked":
        if negative_template or normalized in {"没有", "没", "不用", "没有的"}:
            state["template_preference"] = "generic"
            state["template_answer"] = text[:300]
        elif positive_template or normalized in {"有", "有的", "有学校模板"}:
            state["template_preference"] = "has_template"
            state["template_answer"] = text[:300]
    previous_assistant = next(
        (
            message["content"]
            for message in reversed(store.messages(project_id, limit=8))
            if message["role"] == "assistant"
        ),
        "",
    )
    levels = ("国家级", "省级", "校级")
    level = text.strip()
    if level not in levels or not any(
        marker in previous_assistant for marker in ("申报级别", "项目级别", "哪个级别", "什么级别")
    ):
        match = re.search(
            r"(?:我想申报|我打算申报|我申报|我申请|计划申报|申报级别(?:是|为)?|项目级别(?:是|为)?|级别(?:是|为)?|定为)\s*(国家级|省级|校级)",
            text,
        )
        level = match.group(1) if match else None
    if level:
        fields["level"] = level
    discipline_match = re.search(
        r"(?:我的专业是|专业是|专业为|学科方向是|学科是|研究方向是|方向是)\s*([^，,。；;\n]{2,40})",
        text,
    )
    if discipline_match:
        fields["discipline"] = discipline_match.group(1).strip()
    school_match = re.search(r"(?:学校是|就读于|来自)\s*([^，,。；;\n]{2,50})", text)
    if school_match:
        fields["school"] = school_match.group(1).strip()
    if payload.llm_config:
        cfg = payload.llm_config
        key_hint = f"sk-...{cfg.api_key[-4:]}" if len(cfg.api_key) > 6 else "—"
        state["last_model_config"] = {
            "provider": cfg.provider,
            "model": cfg.model,
            "base_url": cfg.base_url,
            "key_hint": key_hint,
        }
    if state != project["state"]:
        fields["state"] = state
    if fields:
        store.update_project(project_id, **fields)
    cfg = payload.llm_config
    user_id = _current_user_id(request)
    is_free = False
    remaining_free = -1

    if cfg is not None and cfg.provider == "preset":
        wallet = store.get_workbench_credit_balance(user_id)
        if wallet.get("trial_eligible") and wallet["free_chat_count"] > 0:
            # The atomic store operation rechecks eligibility in case recharge
            # races this balance read.
            remaining_free = store.consume_free_chat(user_id)
            if remaining_free >= 0:
                is_free = True

    is_stream = bool(payload.stream or (request.headers.get("accept") == "text/event-stream") or (request.query_params.get("stream") == "true"))
    if is_stream:
        if is_free:
            if not _platform_bundle_ready():
                raise HTTPException(status_code=503, detail="工作台服务账户与实际用量结算尚未接通")
            stream_candidate = OllamaAgent(
                store, tools,
                base_url=os.environ["WOPALLY_MODEL_BASE_URL"].rstrip("/"),
                model="deepseek-v4-flash",
                provider="openai_compatible",
                api_key=os.environ["WOPALLY_WORKBENCH_API_KEY"],
                meter=None,
                platform_transport=True,
            )
        else:
            stream_candidate = (
                _agent_for_config(payload.llm_config, request, project_id)
                if payload.llm_config is not None and payload.llm_config.provider == "preset"
                else _agent_for_config(payload.llm_config)
            )

        def sse_event_generator():
            try:
                for event in stream_candidate.chat_stream(project_id, text):
                    event["setup_updated"] = bool(fields)
                    event["free_chat"] = is_free
                    event["free_chats_remaining"] = remaining_free if is_free else int(store.get_workbench_credit_balance(user_id).get("free_chat_count", 0))
                    yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            except InsufficientCreditsError:
                if is_free:
                    store.refund_free_chat(user_id)
                err = {"type": "error", "error": "积分不足，请充值后继续，或使用自带 API Key。"}
                yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"
            except ModelUnavailable as exc:
                if is_free:
                    store.refund_free_chat(user_id)
                err = {"type": "error", "error": str(exc)}
                yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"
            except Exception as exc:
                if is_free:
                    store.refund_free_chat(user_id)
                err = {"type": "error", "error": str(exc)}
                yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            sse_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    try:
        if is_free:
            if not _platform_bundle_ready():
                raise HTTPException(status_code=503, detail="工作台服务账户与实际用量结算尚未接通")
            candidate = OllamaAgent(
                store, tools,
                base_url=os.environ["WOPALLY_MODEL_BASE_URL"].rstrip("/"),
                model="deepseek-v4-flash",
                provider="openai_compatible",
                api_key=os.environ["WOPALLY_WORKBENCH_API_KEY"],
                meter=None,
                platform_transport=True,
            )
            result = candidate.chat(project_id, text)
            result["free_chat"] = True
            result["free_chats_remaining"] = remaining_free
        else:
            result = _metered_invoke(
                payload.llm_config, request, "chat", project_id,
                lambda model: model.chat(project_id, text),
            )
            result["free_chat"] = False
            bal = store.get_workbench_credit_balance(user_id)
            result["free_chats_remaining"] = int(bal.get("free_chat_count", 0))
        result["setup_updated"] = bool(fields)
        return result
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status_code=402,
            detail="积分不足，请充值后继续，或使用自带 API Key。"
        ) from exc
    except ModelUnavailable as exc:
        if is_free:
            store.refund_free_chat(user_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BaseException:
        if is_free:
            store.refund_free_chat(user_id)
        raise


@app.post("/api/projects/{project_id}/outline/generate")
def generate_outline(project_id: str, payload: LLMRequest | None = None, request: Request = None) -> dict[str, Any]:
    project = _safe_project(project_id)
    try:
        outline = _metered_invoke(
            payload.llm_config if payload else None, request, "outline", project_id,
            lambda model: model.propose_outline(project_id),
        )
        warning = ""
    except ModelUnavailable as exc:
        # The fallback is transparent and editable; it is a skeleton, not generated content.
        discipline = project["discipline"] or "本项目方向"
        outline = [
            {"id": "project_info", "title": "项目基本信息"},
            {"id": "abstract", "title": "项目摘要"},
            {"id": "background", "title": f"项目背景与{discipline}问题"},
            {"id": "research_content", "title": "研究目标与研究内容"},
            {"id": "research_route", "title": "研究方法与实施方案"},
            {"id": "schedule", "title": "进度安排与资源预算"},
            {"id": "foundation", "title": "团队基础与条件"},
            {"id": "references", "title": "参考文献与资料来源"},
        ]
        warning = f"本地模型不可用，先提供可编辑的通用目录：{exc}"
    store.update_project(project_id, outline=outline)
    state_data = dict(project["state"])
    state_data["outline_confirmed"] = False
    store.update_project(project_id, state=state_data)
    return {"outline": outline, "warning": warning, "confirmed": False}


@app.post("/api/projects/{project_id}/sections/{section_id}/jobs")
def create_section_job(
    project_id: str,
    section_id: str,
    payload: CreateJobInput | None = None,
    request: Request = None,
) -> dict[str, Any]:
    project = _safe_project(project_id)
    current_content = (project.get("sections") or {}).get(section_id, "")
    cfg = payload.llm_config if payload else None
    idemp = payload.idempotency_key if payload else ""

    def _run():
        return _metered_invoke(
            cfg, request, f"section:{section_id}", project_id,
            lambda model: model.generate_section(project_id, section_id, persist=False),
        )

    runner = _current_job_runner()
    job = runner.submit_job(
        project_id=project_id,
        section_id=section_id,
        invoke_fn=_run,
        idempotency_key=idemp,
        current_section_content=current_content,
    )
    return job


@app.get("/api/projects/{project_id}/sections/{section_id}/jobs/{job_id}")
def get_section_job(project_id: str, section_id: str, job_id: str) -> dict[str, Any]:
    _safe_project(project_id)
    runner = _current_job_runner()
    job = runner.get_job_status(job_id)
    if not job or job.get("project_id") != project_id or job.get("section_id") != section_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.post("/api/projects/{project_id}/sections/{section_id}/jobs/{job_id}/cancel")
def cancel_section_job(project_id: str, section_id: str, job_id: str) -> dict[str, Any]:
    _safe_project(project_id)
    runner = _current_job_runner()
    job = runner.get_job_status(job_id)
    if not job or job.get("project_id") != project_id or job.get("section_id") != section_id:
        raise HTTPException(404, "任务不存在")
    cancelled = runner.cancel_job(job_id)
    return {"cancelled": cancelled}


@app.get("/api/projects/{project_id}/sections/{section_id}/versions")
def list_section_versions(project_id: str, section_id: str, limit: int = 10) -> dict[str, Any]:
    _safe_project(project_id)
    versions = store.list_section_versions(project_id, section_id, limit=limit)
    return {"versions": versions}


@app.post("/api/projects/{project_id}/sections/{section_id}/versions/{version_id}/restore")
def restore_section_version(project_id: str, section_id: str, version_id: str) -> dict[str, Any]:
    project = _safe_project(project_id)
    ver = store.get_section_version(version_id)
    if not ver or ver.get("project_id") != project_id or ver.get("section_id") != section_id:
        raise HTTPException(status_code=404, detail="版本不存在")
    content = ver.get("content", "")
    tools.save_section(project_id, section_id, content)
    store.save_section_version(project_id, section_id, content, source="restore")
    return {"restored": True, "version_id": version_id, "content": content}


@app.post("/api/projects/{project_id}/sections/{section_id}/generate")
def generate_section(
    project_id: str, section_id: str, payload: LLMRequest | None = None, request: Request = None
) -> dict[str, Any]:
    project = _safe_project(project_id)
    try:
        if material_enabled(project):
            result = _metered_invoke(
                payload.llm_config if payload else None, request, f"section:{section_id}", project_id,
                lambda model: model.generate_section(project_id, section_id, persist=False))
            try:
                store.update_project(project_id, expected_revision=project["material_revision"],
                    sections={**project["sections"], section_id: result["content"]})
                source = "ai_generated"
            except MaterialConflict:
                source = "ai_generated_alternative"
                result.update(conflict_status="user_edit_preserved",
                              notice="项目在生成期间发生变化，正文未覆盖，结果已存为备选版本")
            store.save_section_version(project_id, section_id, result["content"],
                                       source=source, review_card=result.get("review_card"))
            return result
        return _metered_invoke(
            payload.llm_config if payload else None, request, f"section:{section_id}", project_id,
            lambda model: model.generate_section(project_id, section_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.put("/api/projects/{project_id}/outline")
def update_outline(project_id: str, payload: OutlineUpdate) -> dict[str, Any]:
    _safe_project(project_id)
    if not 1 <= len(payload.outline) <= 20:
        raise HTTPException(status_code=400, detail="章节数须为 1–20")
    outline = []
    seen: set[str] = set()
    for index, item in enumerate(payload.outline):
        section_id = re.sub(r"[^a-zA-Z0-9_-]", "_", item.get("id", ""))[:80] or f"section_{index+1}"
        if section_id in seen:
            raise HTTPException(status_code=400, detail="章节标识不能重复")
        seen.add(section_id)
        title = item.get("title", "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="章节标题不能为空")
        outline.append({"id": section_id, "title": title[:100]})
    project = _safe_project(project_id)
    existing_sections = project["sections"]
    confirmed_state = dict(project["state"])
    confirmed_state["outline_confirmed"] = True
    for item in outline:
        existing_sections.setdefault(item["id"], "")
    store.update_project(
        project_id,
        outline=outline,
        sections=existing_sections,
        state=confirmed_state,
    )
    return {"outline": outline}


@app.put("/api/projects/{project_id}/sections/{section_id}")
def update_section(project_id: str, section_id: str, payload: SectionUpdate) -> dict[str, Any]:
    project = _safe_project(project_id)
    if material_enabled(project) and payload.expected_revision is not None:
        if payload.base_content is not None and project["sections"].get(section_id, "") != payload.base_content:
            raise HTTPException(409, "该章节已在其他页面修改，请核对版本，未覆盖您的输入")
        if section_id not in {s["id"] for s in project["outline"]}:
            raise HTTPException(422, "章节不存在")
        updated = store.update_project(project_id, expected_revision=payload.expected_revision,
            sections={**project["sections"], section_id: payload.content})
        return {"success": True, "section_id": section_id, "character_count": len(payload.content),
                "material_revision": updated["material_revision"]}
    result = tools.save_section(project_id, section_id, payload.content)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.delete("/api/projects/{project_id}/diagrams/{diagram_id}")
def delete_diagram(project_id: str, diagram_id: str) -> dict[str, Any]:
    project = _safe_project(project_id)
    diagrams = [dict(d) for d in project.get("diagrams", []) if d.get("id") != diagram_id]
    store.update_project(project_id, diagrams=diagrams)
    return {"ok": True, "diagram_id": diagram_id}


@app.post("/api/projects/{project_id}/diagrams")
def save_diagram(project_id: str, payload: DiagramInput) -> dict[str, Any]:
    _safe_project(project_id)
    result = tools.save_diagram(project_id, payload.title, payload.nodes, payload.diagram_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    diagram = result["diagram"]
    if diagram.get("preview") and hasattr(store, "persist_generated_file"):
        storage_path = store.persist_generated_file(
            project_id, f"{diagram['id']}.png", diagram["preview"], "image/png"
        )
        project = _safe_project(project_id)
        diagrams = [dict(item) for item in project["diagrams"]]
        for item in diagrams:
            if item.get("id") == diagram["id"]:
                item["preview"] = f"storage://{storage_path}"
                diagram["preview"] = item["preview"]
        store.update_project(project_id, diagrams=diagrams)
    if diagram.get("preview"):
        diagram["preview_url"] = f"/api/projects/{project_id}/diagrams/{diagram['id']}/preview"
    return result


@app.post("/api/projects/{project_id}/diagrams/propose")
def propose_diagram(project_id: str, payload: DiagramProposalInput, request: Request = None) -> dict[str, Any]:
    _safe_project(project_id)
    title = payload.title.strip() or "技术路线图"
    try:
        return _metered_invoke(
            payload.llm_config, request, "diagram", project_id,
            lambda model: model.propose_diagram(project_id, title),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/images/generate")
def generate_project_image(
    project_id: str, payload: GenerateImageInput, request: Request
) -> dict[str, Any]:
    project = _safe_project(project_id)
    cfg = payload.llm_config
    use_custom_image = bool(
        cfg and cfg.provider == "openai_compatible" and (
            cfg.image_model.strip() or cfg.image_base_url.strip() or cfg.image_reuse_text
        )
    )

    if use_custom_image:
        effective_base = (
            cfg.base_url.strip()
            if cfg.image_reuse_text or not cfg.image_base_url.strip()
            else cfg.image_base_url.strip()
        )
        effective_key = (
            cfg.api_key.strip()
            if cfg.image_reuse_text or not cfg.image_api_key.strip()
            else cfg.image_api_key.strip()
        )
        effective_model = cfg.image_model.strip() or "dall-e-3"
        if not effective_base.startswith("https://") or not effective_key:
            raise HTTPException(status_code=422, detail="自定义生图需配置有效的 HTTPS API 地址和 API Key。")
        try:
            content = generate_custom_image(
                payload.prompt.strip(),
                effective_base,
                effective_model,
                effective_key,
            )
        except ModelUnavailable as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"自定义生图失败：{str(exc)}") from exc
    else:
        if not _platform_bundle_ready():
            raise HTTPException(
                status_code=503,
                detail="未配置自定义生图模型，且平台融合生图未开通。请在「模型配置」中配置生图 API（如硅基流动 FLUX / OpenAI DALL-E）。"
            )
        meter = WorkbenchMeter(
            store, _current_user_id(request), int(os.environ["WOPALLY_WORKBENCH_API_KEY_ID"]), project_id
        )
        try:
            content = generate_image(payload.prompt.strip(), meter)
        except InsufficientCreditsError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        except PendingUsageError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ModelUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    mime = "image/jpeg" if content.startswith(bytes([255, 216, 255])) else "image/webp" if content.startswith(b"RIFF") else "image/png"
    ext = ".jpg" if mime == "image/jpeg" else ".webp" if mime == "image/webp" else ".png"
    image_id = os.urandom(16).hex()
    image_dir = store.files_dir / project_id
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / f"{image_id}{ext}"
    image_path.write_bytes(content)
    preview = str(image_path)
    if hasattr(store, "persist_generated_file"):
        try:
            preview = "storage://" + store.persist_generated_file(
                project_id, image_path.name, image_path, mime
            )
        finally:
            image_path.unlink(missing_ok=True)
    diagram = {
        "id": image_id, "title": payload.prompt.strip()[:80],
        "nodes": [], "preview": preview, "kind": "generated_image",
    }
    diagrams = [*project["diagrams"], diagram]
    store.update_project(project_id, diagrams=diagrams)
    diagram["preview_url"] = f"/api/projects/{project_id}/diagrams/{image_id}/preview"
    return {"diagram": diagram}


@app.post("/api/projects/{project_id}/search/papers")
def search_papers(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _safe_project(project_id)
    query = str(payload.get("query", "")).strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="请输入论文主题关键词")
    return tools.search_papers(query, int(payload.get("limit", 5)))


@app.post("/api/projects/{project_id}/search/official")
def search_official(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project = _safe_project(project_id)
    query = str(payload.get("query", "")).strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="请输入要查询的官方要求")
    return tools.search_official_notices(query, project["school"])


@app.post("/api/projects/{project_id}/official/preview")
def preview_official_source(project_id: str, payload: OfficialURLInput) -> dict[str, Any]:
    _safe_project(project_id)
    result = tools.fetch_official_notice(payload.url)
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return result


@app.post("/api/projects/{project_id}/official/import")
def import_official_source(project_id: str, payload: OfficialURLInput) -> dict[str, Any]:
    _safe_project(project_id)
    result = tools.fetch_official_notice(payload.url)
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    project_folder = store.files_dir / project_id
    project_folder.mkdir(parents=True, exist_ok=True)
    document_id = os.urandom(16).hex()
    stored_path = project_folder / f"{document_id}.txt"
    content = (
        f"[官方通知：{result['title']}]\n"
        f"[来源链接] {result['url']}\n"
        f"[页面发布日期] {result.get('published_at') or '页面未提供'}\n"
        f"[抓取时间 UTC] {result['retrieved_at_utc']}\n\n"
        f"{result['content']}"
    )
    stored_path.write_text(content, encoding="utf-8")
    document = store.add_document(
        project_id,
        f"{result['title'][:120]}.txt",
        str(stored_path),
        "official",
        "text/plain",
        document_id=document_id,
    )
    store.update_document_extraction(
        document_id,
        content,
        "ready",
        "请核对官方页面内容后，确认加入当前项目 RAG。",
        0,
        confirmed=False,
    )
    return {
        "document": _public_document(store.get_document(document_id) or document),
        "note": "通知已读取但尚未索引；核对文字并确认后，Agent 才能引用。",
    }


@app.post("/api/projects/{project_id}/references/confirm")
def confirm_reference(project_id: str, payload: ReferenceConfirm) -> dict[str, Any]:
    project = _safe_project(project_id)
    ref = payload.model_dump()
    ref["authors"] = [str(a)[:160] for a in payload.authors[:12]]
    if ref["doi"]:
        doi = ref["doi"].removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        ref["doi"] = doi
        request = urllib.request.Request(
            f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}",
            headers={"User-Agent": "AwesomeStudentAIProposalAgent/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                verified = json.loads(response.read().decode("utf-8")).get("message", {})
            verified_title = (verified.get("title") or [""])[0]
            normalize_title = lambda text: re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text.casefold())
            if (
                verified_title
                and normalize_title(verified_title) != normalize_title(payload.title)
            ):
                raise HTTPException(status_code=422, detail=f"DOI 对应标题为“{verified_title}”，与输入标题不一致。")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"无法核验该 DOI：{exc}") from exc
    state = dict(project["state"])
    if ref["source_type"] in {"official", "policy", "school_notice"}:
        from proposal.tools import _official_url

        if not _official_url(ref.get("url", "")):
            raise HTTPException(status_code=422, detail="官方通知只接受 edu.cn 或 gov.cn 来源链接。")
        refs = list(state.get("official_sources", []))
        if not any(r.get("url") == ref["url"] for r in refs if isinstance(r, dict)):
            refs.append(ref)
        state["official_sources"] = refs
    else:
        refs = list(state.get("references", []))
        if not any((r.get("doi") and r.get("doi") == ref["doi"]) for r in refs if isinstance(r, dict)):
            refs.append(ref)
        state["references"] = refs
    store.update_project(project_id, state=state)
    return {"references": refs, "confirmed": True, "source_type": ref["source_type"]}


@app.put("/api/projects/{project_id}/facts")
def update_project_facts(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project = _safe_project(project_id)
    if len(payload) > 100:
        raise HTTPException(status_code=413, detail="一次最多保存 100 个信息字段")
    facts = {
        key: str(value).strip()[:2000]
        for key, value in payload.items()
        if valid_fact_key(key) and str(value).strip()
    }
    state = dict(project["state"])
    confirmed = dict(state.get("confirmed_facts", {}))
    confirmed.update(facts)
    state["confirmed_facts"] = confirmed
    state.update(facts)
    state.setdefault("fact_sources", {})
    for key in facts:
        state["fact_sources"][key] = "学生在网页中手动确认"
    update_fields: dict[str, Any] = {"state": state}
    if facts.get("project_name"):
        update_fields["title"] = facts["project_name"]
    store.update_project(project_id, **update_fields)
    return {"confirmed_facts": confirmed}


@app.post("/api/projects/{project_id}/facts/propose")
def propose_project_facts(project_id: str, payload: LLMRequest | None = None, request: Request = None) -> dict[str, Any]:
    _safe_project(project_id)
    try:
        return _metered_invoke(
            payload.llm_config if payload else None, request, "facts", project_id,
            lambda model: model.propose_facts(project_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/facts/confirm")
def confirm_project_fact(project_id: str, payload: FactConfirm) -> dict[str, Any]:
    project = _safe_project(project_id)
    if not valid_fact_key(payload.key):
        raise HTTPException(status_code=400, detail="事实字段标识无效")
    if payload.value != payload.source_quote:
        raise HTTPException(
            status_code=422,
            detail="候选事实必须与原文保持一致；如需规范化，请在事实面板中手动修改。",
        )
    supported = any(
        payload.source_quote in message["content"]
        for message in store.messages(project_id, limit=40)
        if message["role"] == "user"
    )
    if not supported:
        supported = any(
            doc["confirmed"]
            and payload.source_quote in doc["extracted_text"]
            for doc in store.list_documents(project_id)
        )
    if not supported:
        raise HTTPException(status_code=422, detail="来源原文已找不到，请重新提取或手动填写事实")
    value_numbers = re.findall(r"\d+(?:\.\d+)?", payload.value)
    quote_numbers = re.findall(r"\d+(?:\.\d+)?", payload.source_quote)
    if any(number not in quote_numbers for number in value_numbers):
        raise HTTPException(status_code=422, detail="候选事实的数字与来源原文不一致，请手动核对")
    state = dict(project["state"])
    confirmed = dict(state.get("confirmed_facts", {}))
    sources = dict(state.get("fact_sources", {}))
    confirmed[payload.key] = payload.value.strip()
    sources[payload.key] = payload.source_quote
    state.update(
        {
            "confirmed_facts": confirmed,
            "fact_sources": sources,
            payload.key: payload.value.strip(),
        }
    )
    store.update_project(project_id, state=state)
    return {"confirmed": True, "key": payload.key, "value": payload.value.strip(), "source_quote": payload.source_quote}


@app.get("/api/projects/{project_id}/diagrams/{diagram_id}/preview")
def diagram_preview(project_id: str, diagram_id: str) -> Response:
    project = _safe_project(project_id)
    diagram = next((d for d in project["diagrams"] if d.get("id") == diagram_id), None)
    if not diagram or not diagram.get("preview"):
        raise HTTPException(status_code=404, detail="图表预览不存在")
    if diagram["preview"].startswith("storage://") and hasattr(store, "read_generated_file"):
        return Response(
            content=store.read_generated_file(diagram["preview"].removeprefix("storage://")),
            media_type="image/png",
        )
    path = Path(diagram["preview"]).resolve()
    try:
        path.relative_to((store.files_dir / project_id).resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="图表路径无效") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="图表文件不存在")
    return FileResponse(path, media_type="image/png")


@app.post("/api/projects/{project_id}/validate")
def validate_project(project_id: str) -> dict[str, Any]:
    _safe_project(project_id)
    return tools.validate_project(project_id)


@app.post("/api/projects/{project_id}/review")
def simulate_review(project_id: str) -> dict[str, Any]:
    _safe_project(project_id)
    return tools.simulate_review(project_id)


@app.post("/api/projects/{project_id}/export")
def export_docx(project_id: str) -> dict[str, Any]:
    _safe_project(project_id)
    preflight = tools.validate_project(project_id)
    output_path = store.files_dir / project_id / "申报书草稿.docx"
    try:
        result = export_project(store, project_id, output_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Word 草稿生成失败：{exc}") from exc
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Word 导出失败"))

    # 排版硬化 + 质检：35 个子 skill 各自手写 docx，表格防拆/图注绑定/页码/大纲
    # 的覆盖率是 0，在这一层统一补齐，用户拿到的每一份都过同一把尺子。
    try:
        from utils.docx_layout_fix import fix as _harden
        from utils.layout_audit import audit as _audit

        _harden(output_path)
        _qa = _audit(Path(output_path), render=False)
        result["layout"] = {
            "score": _qa.score,
            "fails": [{"rule": i.rule, "detail": i.detail, "fix": i.fix} for i in _qa.fails],
            "warns": [{"rule": i.rule, "detail": i.detail} for i in _qa.warns],
        }
    except Exception as exc:  # 质检失败不影响导出
        logging.getLogger(__name__).warning("排版硬化失败：%s", exc)
        result["layout"] = {"score": None, "error": str(exc)[:200]}

    if hasattr(store, "persist_generated_file"):
        storage_path = store.persist_generated_file(
            project_id,
            "申报书草稿.docx",
            output_path,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        project = _safe_project(project_id)
        state_data = dict(project["state"])
        state_data["exported_docx_storage_path"] = storage_path
        store.update_project(project_id, state=state_data)
    result["download_url"] = f"/api/projects/{project_id}/download"
    result["validation"] = preflight
    return result


@app.get("/api/projects/{project_id}/download")
def download_docx(project_id: str) -> Response:
    project = _safe_project(project_id)
    download_name = f"{project.get('state', {}).get('skill_name') or '申报材料'}草稿.docx"
    storage_path = project["state"].get("exported_docx_storage_path")
    if storage_path and hasattr(store, "read_generated_file"):
        return Response(
            content=store.read_generated_file(storage_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(download_name)}"},
        )
    path = store.files_dir / project_id / "申报书草稿.docx"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="请先导出 Word 草稿")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_name,
    )


# Compatibility endpoints for the repository's previous service tests/clients.
@app.get("/types")
def legacy_types() -> dict[str, Any]:
    if not dispatcher:
        raise HTTPException(status_code=503, detail="Dispatcher 不可用")
    return {"total": len(dispatcher.skills), "skills": dispatcher.skills}


@app.post("/route")
def legacy_route(payload: dict[str, Any]) -> dict[str, Any]:
    if not dispatcher:
        raise HTTPException(status_code=503, detail="Dispatcher 不可用")
    query = str(payload.get("query", ""))
    top_n = max(1, min(int(payload.get("top_n", 3)), 10))
    candidates = dispatcher.dispatch(query, top_n=top_n)
    for item in candidates:
        if isinstance(item.get("name"), str):
            item["name"] = item["name"].replace("-", "_")
    return {"query": query, "candidates": candidates}


@app.get("/fields")
def legacy_fields(skill_id: str) -> dict[str, Any]:
    if not dispatcher:
        raise HTTPException(status_code=503, detail="Dispatcher 不可用")
    normalized = skill_id.replace("_", "-")
    info = dispatcher.info(normalized) or dispatcher.info(skill_id)
    if not info:
        raise HTTPException(status_code=404, detail="未找到该赛道")
    path = ROOT / info["skill_md_path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="赛道指南文件不存在")
    field_names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] not in {"字段", "项目"} and not set(cells[0]) <= {"-", ":"}:
            field_names.append(cells[0])
    return {"skill_id": skill_id, "info_fields": field_names[:80], "skill_info": info}


@app.post("/generate")
def legacy_generate(payload: dict[str, Any]) -> dict[str, Any]:
    skill_name = str(payload.get("skill_id", "")).replace("_", "-")
    if skill_name not in {
        skill.get("name") for skill in (dispatcher.skills if dispatcher else [])
    }:
        raise HTTPException(status_code=404, detail="未找到该赛道")
    if not os.environ.get("LLM_API_KEY"):
        raise HTTPException(status_code=503, detail="LLM_API_KEY 未配置；请使用网页 Agent 的本地 Ollama 流程")
    raise HTTPException(status_code=410, detail="请改用 /api/projects 工作流，避免跳过事实确认和草稿检查")

@app.get("/api/projects/{project_id}/token-stats")
def get_project_token_stats(project_id: str) -> dict[str, Any]:
    project = _safe_project(project_id)
    stats = store.get_token_stats(project_id)
    return {"project_id": project_id, "title": project.get("title", ""), "stats": stats}


@app.get("/api/token-stats")
def get_global_token_stats() -> dict[str, Any]:
    return {"stats": store.get_token_stats()}


from proposal.material_api import register_material_api
def _validate_material_config(config):
    normalized = LLMConfigInput(**config)
    _agent_for_config(normalized)
    return normalized.model_dump()

register_material_api(app, lambda: store, _validate_material_config)
