from __future__ import annotations

import json
import ipaddress
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import mimetypes
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = Path(__file__).resolve().parent
STATIC_DIR = SERVER_DIR / "static"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from proposal.agent import ModelUnavailable, OllamaAgent
from proposal.documents import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, Extraction, extract_file
from proposal.exporter import export_project
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.supabase_store import SupabaseStore, request_identity
from proposal.tools import ProposalTools
from proposal.skills import normalize_skill_id, registry as skill_registry, valid_fact_key

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
    provider: Literal["ollama", "openai_compatible"] = "ollama"
    model: str = Field(default="", max_length=160)
    base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=1000)


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    llm_config: LLMConfigInput | None = None


class LLMRequest(BaseModel):
    llm_config: LLMConfigInput | None = None


class StorageDocumentInput(BaseModel):
    document_id: str = Field(min_length=12, max_length=80)
    original_name: str = Field(min_length=1, max_length=255)
    storage_path: str = Field(min_length=8, max_length=600)
    kind: Literal["source", "template", "photo"] = "source"
    content_type: str = Field(default="", max_length=150)


class DiagramProposalInput(BaseModel):
    title: str = Field(default="技术路线图", max_length=100)
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
CLOUD_MODE = bool(SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY)
store = (
    SupabaseStore(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)
    if CLOUD_MODE
    else Store()
)
retriever = ProjectRetriever(store, KeywordOnlyEmbedder() if CLOUD_MODE else None)
tools = ProposalTools(store, retriever)
agent = OllamaAgent(store, tools)
dispatcher = Dispatcher() if Dispatcher else None

app = FastAPI(
    title="大学生申报材料 Agent",
    description="本地优先的申报材料工作台：Skill 自动路由、资料识别、项目内检索、章节写作与 Word 草稿。",
    version="0.1.0",
    docs_url=None if CLOUD_MODE else "/docs",
    redoc_url=None if CLOUD_MODE else "/redoc",
    openapi_url=None if CLOUD_MODE else "/openapi.json",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def require_supabase_session(request: Request, call_next):
    if not CLOUD_MODE:
        return await call_next(request)
    path = request.url.path
    if (
        path == "/"
        or path in {"/health", "/api/health", "/api/config", "/api/skills", "/api/route"}
        or path.startswith("/static/")
    ):
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    scheme, _, access_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not access_token.strip():
        return JSONResponse({"detail": "请先登录后继续。"}, status_code=401)
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "apikey": SUPABASE_PUBLISHABLE_KEY,
                    "Authorization": f"Bearer {access_token.strip()}",
                },
            )
        if response.status_code != 200:
            return JSONResponse({"detail": "登录已过期，请重新登录。"}, status_code=401)
        user_id = response.json().get("id")
        if not user_id:
            return JSONResponse({"detail": "无法确认登录用户。"}, status_code=401)
    except Exception:
        return JSONResponse({"detail": "暂时无法验证登录状态，请稍后重试。"}, status_code=503)

    context_token = request_identity.set(
        {"access_token": access_token.strip(), "user_id": str(user_id)}
    )
    try:
        return await call_next(request)
    finally:
        request_identity.reset(context_token)


def _agent_for_config(config: LLMConfigInput | None) -> OllamaAgent:
    if config is None:
        return agent
    model = config.model.strip()
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
    return index.read_text(encoding="utf-8")


@app.get("/api/config")
def app_config() -> dict[str, Any]:
    return {
        "cloud_mode": CLOUD_MODE,
        "supabase_url": SUPABASE_URL if CLOUD_MODE else "",
        "supabase_publishable_key": SUPABASE_PUBLISHABLE_KEY if CLOUD_MODE else "",
    }


@app.get("/api/skills")
def list_skills() -> dict[str, Any]:
    return {"total": len(skill_registry.skills), "skills": skill_registry.list()}


@app.post("/api/route")
def route_skill(payload: RouteRequest) -> dict[str, Any]:
    """Match a natural-language request to a skill, asking for clarification when weak."""
    if not dispatcher:
        raise HTTPException(status_code=503, detail="Skill 路由器不可用")
    matches = dispatcher.dispatch(payload.query, top_n=5)
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
    top = candidates[0]
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0
    confident = top["score"] >= 5 and top["score"] - second_score >= 2
    return {
        "selected": top if confident else None,
        "needs_clarification": not confident,
        "candidates": candidates[:5],
        "message": "" if confident else "我找到几个可能的赛道，请确认最符合你需求的一项。",
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


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    return health()


@app.post("/api/model-config/test")
def test_model_config(payload: LLMConfigInput) -> dict[str, Any]:
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
    project["documents"] = [_public_document(d) for d in store.list_documents(project_id)]
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
            raise HTTPException(status_code=413, detail=f"{name} 超过 20 MB")
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
            confirmed = kind == "template"
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
                    "needs_confirmation": kind != "template",
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
    return {"documents": results, "note": "来源材料须先核对提取文本；确认后才进入本项目的 RAG 检索。"}


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
        )
        file_bytes = Path(document["stored_path"]).read_bytes()
        extraction = _extract_uploaded_document(document["original_name"], file_bytes, document["kind"])
        confirmed = document["kind"] == "template"
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
                    "needs_confirmation": document["kind"] != "template",
                }
            ],
            "note": "来源材料须先核对提取文本；确认后才进入本项目的 RAG 检索。",
        }
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"云端材料处理失败：{_document_extraction_error(exc)}",
            ) from exc


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
def chat(project_id: str, payload: ChatInput) -> dict[str, Any]:
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
    try:
        result = _agent_for_config(payload.llm_config).chat(project_id, text)
        result["setup_updated"] = bool(fields)
        return result
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/outline/generate")
def generate_outline(project_id: str, payload: LLMRequest | None = None) -> dict[str, Any]:
    project = _safe_project(project_id)
    try:
        outline = _agent_for_config(payload.llm_config if payload else None).propose_outline(project_id)
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


@app.post("/api/projects/{project_id}/sections/{section_id}/generate")
def generate_section(
    project_id: str, section_id: str, payload: LLMRequest | None = None
) -> dict[str, Any]:
    _safe_project(project_id)
    try:
        return _agent_for_config(payload.llm_config if payload else None).generate_section(project_id, section_id)
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
    _safe_project(project_id)
    result = tools.save_section(project_id, section_id, payload.content)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


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
def propose_diagram(project_id: str, payload: DiagramProposalInput) -> dict[str, Any]:
    _safe_project(project_id)
    title = payload.title.strip() or "技术路线图"
    try:
        return _agent_for_config(payload.llm_config).propose_diagram(project_id, title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
def propose_project_facts(project_id: str, payload: LLMRequest | None = None) -> dict[str, Any]:
    _safe_project(project_id)
    try:
        return _agent_for_config(payload.llm_config if payload else None).propose_facts(project_id)
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
