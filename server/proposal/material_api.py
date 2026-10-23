"""Pilot-only APIs, mounted alongside (not replacing) the legacy workbench."""
from __future__ import annotations

import copy
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from .material_figures import FigureSpec
from .material_jobs import MaterialJobs, checked_bundle, job_id
from .materials import (
    MaterialConflict, Requirement, RULES, TRACKING, enabled, material_view, digest, prepare_update,
)
from .model_config_security import encrypt_config


class RequirementsInput(BaseModel):
    revision: int
    items: list[Requirement] = Field(max_length=50)


class AcknowledgeInput(BaseModel):
    revision: int
    snapshot: str
    nodes: list[str] = Field(max_length=100)


class PlansInput(BaseModel):
    revision: int
    items: list[FigureSpec] = Field(max_length=30)


class JobInput(BaseModel):
    revision: int
    kind: Literal["section", "figure", "export", "outline", "plan"]
    target: str = Field(default="", max_length=80)
    idempotency_key: str = Field(min_length=1, max_length=120)
    llm_config: dict | None = None
    confirm_paid: bool = False


def signed_url(store, path: str, *, upload=False) -> str:
    owner = store._identity()["user_id"]
    if not path.startswith(owner + "/"):
        raise PermissionError("文件不属于当前账号")
    endpoint = "upload/sign" if upload else "sign"
    url = f"{store.project_url}/storage/v1/object/{endpoint}/{store.bucket}/{urllib.parse.quote(path, safe='/')}"
    req = urllib.request.Request(url, data=json.dumps({"expiresIn": 7200}).encode(),
                                 headers=store._headers({"Content-Type": "application/json"}), method="POST")
    from .supabase_http import supabase_urlopen
    with supabase_urlopen(req, timeout=20) as response:
        result = json.load(response)
    relative = result.get("signedURL") or result.get("signedUrl") or result.get("url")
    if not relative:
        raise RuntimeError("无法签发限时文件传输地址")
    if relative.startswith("http"):
        return relative
    return store.project_url + (relative if relative.startswith("/storage/v1/") else "/storage/v1" + relative)


def artifact_folder(store, project_id: str, raw: dict) -> Path:
    folder = store.files_dir / project_id / "_material" / raw["id"]
    if hasattr(store, "_storage") and not (folder / ".complete").exists():
        data = store._storage("GET", raw["payload"]["output_path"])
        checked_bundle(data, folder)
        (folder / ".complete").touch()
    return folder


def register_material_api(app, get_store, validate_config):
    router = APIRouter(prefix="/api/projects/{project_id}/material")

    def project_for(project_id):
        if not re.fullmatch(r"[a-f0-9]{32}", project_id):
            raise HTTPException(404, "项目不存在")
        store = get_store()
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
        if not enabled(project):
            raise HTTPException(404, "当前材料沿用原链路，或大创试点尚未启用")
        return store, project

    def save(store, project, revision, **fields):
        if revision != project.get("material_revision", 0):
            raise HTTPException(409, "项目已变化，请刷新后重试")
        try:
            return store.update_project(project["id"], expected_revision=revision, **fields)
        except MaterialConflict as exc:
            raise HTTPException(409, str(exc)) from None

    @router.get("")
    def context(project_id: str):
        store, project = project_for(project_id)
        return {"context": material_view(project, store.list_documents(project_id)),
                "requirements": project["state"].get(RULES, []),
                "plans": project["state"].get("_material_plans", []),
                "jobs": MaterialJobs(store).call("list", project_id=project_id),
                "worker_ready": os.environ.get("MATERIAL_WORKER_READY", "").lower() == "true"}

    @router.put("/requirements")
    def update_requirements(project_id: str, payload: RequirementsInput):
        store, project = project_for(project_id)
        state = {**project["state"], RULES: [r.model_dump() for r in payload.items]}
        updated = save(store, project, payload.revision, state=state)
        return material_view(updated)

    @router.post("/acknowledge")
    def acknowledge(project_id: str, payload: AcknowledgeInput):
        store, project = project_for(project_id)
        view = material_view(project)
        if payload.snapshot != view["snapshot"] or any(n not in view["stale"] for n in payload.nodes):
            raise HTTPException(409, "核对依据已变化，请重新检查")
        state = {**project["state"], "_material_ack": {"snapshot": payload.snapshot, "nodes": payload.nodes}}
        return material_view(save(store, project, payload.revision, state=state))

    @router.put("/plans")
    def update_plans(project_id: str, payload: PlansInput):
        store, project = project_for(project_id)
        ids = [item.id for item in payload.items]
        sections = {s["id"] for s in project["outline"]}
        if len(set(ids)) != len(ids) or any(item.section_id not in sections for item in payload.items):
            raise HTTPException(422, "图表编号重复或关联章节不存在")
        document_ids = {d["id"] for d in store.list_documents(project_id)}
        if any(set(item.source_ids) - document_ids for item in payload.items):
            raise HTTPException(422, "图表来源不属于当前项目")
        plans = [item.model_dump() for item in payload.items]
        # Editing a plan does not approve the previous version's output.
        old = {p["id"]: p for p in project["state"].get("_material_plans", [])}
        for item in plans:
            prior = old.get(item["id"])
            if prior and {k: v for k, v in prior.items() if k not in {"confirmed", "text_confirmed"}} != {
                k: v for k, v in item.items() if k not in {"confirmed", "text_confirmed"}
            }:
                item["text_confirmed"] = False
        updated = save(store, project, payload.revision, state={**project["state"], "_material_plans": plans})
        return {"plans": plans, "context": material_view(updated)}

    @router.post("/jobs", status_code=202)
    def submit(project_id: str, payload: JobInput):
        store, project = project_for(project_id)
        if os.environ.get("MATERIAL_WORKER_READY", "").lower() != "true":
            raise HTTPException(503, "大创 Worker 尚未启用，不能提交长任务")
        queue = MaterialJobs(store)
        # Retry an accepted HTTP submission before checking stale input or signing files.
        existing = queue.find(project_id, payload.idempotency_key)
        if existing:
            return existing
        if payload.revision != project.get("material_revision", 0):
            raise HTTPException(409, "项目已变化，请刷新后重试")
        spec = None
        if payload.kind in {"section", "plan"}:
            if not project["state"].get("outline_confirmed") or payload.target not in {s["id"] for s in project["outline"]}:
                raise HTTPException(422, "请先确认目录，并选择有效章节")
        elif payload.kind == "figure":
            plan = next((p for p in project["state"].get("_material_plans", []) if p["id"] == payload.target), None)
            if not plan or not plan.get("confirmed"):
                raise HTTPException(422, "请先保存并确认该图表计划")
            spec = FigureSpec.model_validate(plan)
            if spec.renderer == "upload":
                document = next((d for d in store.list_documents(project_id) if d["id"] == spec.document_id), None)
                if not document or not document.get("content_type", "").startswith("image/"):
                    raise HTTPException(422, "请选择当前项目的真实上传图片")
        model_call = payload.kind in {"section", "outline", "plan"} or (spec is not None and spec.renderer == "gpt")
        config = payload.llm_config or ({"provider": "preset"} if queue.cloud else {"provider": "ollama"})
        if model_call:
            if any(c["status"] == "needs_confirmation" for c in material_view(project)["requirements"]["conflicts"]):
                raise HTTPException(409, "适用要求存在同级冲突，请先确认采用哪条要求；尚未调用模型")
            try:
                config = validate_config(config)  # Normalize without any model call.
            except ValidationError:
                raise HTTPException(422, "模型配置格式不正确") from None
            if spec and spec.renderer == "gpt" and config.get("provider") not in {"preset", "openai_compatible"}:
                raise HTTPException(422, "GPT 生图需要平台模型或自定义生图 API")
            if not payload.confirm_paid:
                raise HTTPException(422, "请明确确认本轮模型调用；平台模型按原积分规则，BYOK 按服务商规则")
        platform = model_call and config.get("provider") == "preset"
        identifier = job_id()
        owner = store._identity()["user_id"] if queue.cloud else "local_user"
        job_payload = {
            "job_id": identifier, "owner_id": owner, "project": copy.deepcopy(project),
            "base_revision": project.get("material_revision", 0),
            "input_snapshot": material_view(project)["snapshot"],
            "documents": store.list_documents(project_id),
            "chunks": store.chunks_for_project(project_id),
            "messages": store.messages(project_id, limit=30),
            "spec": spec.model_dump() if spec else None,
            "paid": bool(model_call), "platform": bool(platform), "downloads": [],
        }
        if model_call:
            if config.get("provider") == "preset":
                job_payload["config"] = {"provider": "preset"}
            elif config.get("api_key") or config.get("image_api_key"):
                try:
                    job_payload["config_ciphertext"] = encrypt_config(owner, config)
                except RuntimeError as exc:
                    raise HTTPException(503, str(exc)) from None
            else:
                job_payload["config"] = config
        # Scene-text confirmation belongs to the generated asset, never its plan.
        if job_payload["spec"]:
            job_payload["spec"]["text_confirmed"] = False
        if queue.cloud:
            output = f"{owner}/{project_id}/_material/{identifier}.zip"
            job_payload["output_path"] = output
            if payload.kind in {"figure", "export"}:
                job_payload["upload_url"] = signed_url(store, output, upload=True)
            if payload.kind == "figure" and spec and spec.renderer == "gpt":
                # Vercel performs the paid image call with its existing provider
                # credentials, writes the image to private Storage, and gives
                # the Worker only a short-lived download URL.
                image_path = f"{owner}/{project_id}/_material/{identifier}-image.png"
                job_payload["image_path"] = image_path
                job_payload["image_upload_url"] = signed_url(store, image_path, upload=True)
                job_payload["image_download_url"] = signed_url(store, image_path)
            for doc in job_payload["documents"]:
                needs_file = (payload.kind == "export" and doc["kind"] in {"template", "photo"}) or (
                    spec is not None and spec.renderer == "upload" and spec.document_id == doc["id"])
                if needs_file and doc.get("storage_path"):
                    job_payload["downloads"].append({"kind": "document", "id": doc["id"],
                        "url": signed_url(store, doc["storage_path"])})
                doc.pop("stored_path", None)
            for figure in (project.get("diagrams", []) if payload.kind == "export" else []):
                previous_job = figure.get("material_job_id")
                if previous_job:
                    raw = queue.call("raw", project_id=project_id, id=previous_job)
                    if raw and raw["status"] == "completed":
                        job_payload["downloads"].append({"kind": "figure", "id": figure["id"],
                            "url": signed_url(store, raw["payload"]["output_path"])})
                    figure.pop("preview", None)
            if spec and spec.base_asset_job:
                raw = queue.call("raw", project_id=project_id, id=spec.base_asset_job)
                if not raw or raw["status"] != "completed" or raw["kind"] != "figure":
                    raise HTTPException(422, "原始图片资产不存在")
                job_payload["downloads"].append({"kind": "base", "id": spec.id,
                    "url": signed_url(store, raw["payload"]["output_path"])})
        else:
            job_payload["local_root"] = str(store.files_dir.resolve())
        if len(json.dumps(job_payload, ensure_ascii=False).encode()) > 7_000_000:
            raise HTTPException(413, "本次上下文过大，请拆分项目资料后再提交；尚未调用模型")
        return queue.submit(project_id, payload.kind, payload.target, job_payload, payload.idempotency_key)

    @router.get("/jobs/{identifier}")
    def status(project_id: str, identifier: str):
        store, _ = project_for(project_id)
        job = MaterialJobs(store).call("get", project_id=project_id, id=identifier)
        if not job:
            raise HTTPException(404, "任务不存在")
        return job

    @router.post("/jobs/{identifier}/cancel")
    def cancel(project_id: str, identifier: str):
        store, _ = project_for(project_id)
        result = MaterialJobs(store).call("cancel", project_id=project_id, id=identifier)
        if not result:
            raise HTTPException(404, "任务不存在")
        return result

    @router.post("/jobs/{identifier}/apply")
    def apply(project_id: str, identifier: str):
        store, project = project_for(project_id)
        queue = MaterialJobs(store)
        raw = queue.call("raw", project_id=project_id, id=identifier)
        if not raw or raw["status"] != "completed":
            raise HTTPException(409, "任务未完成")
        if raw["result"].get("applied"):
            return raw["result"]
        result = dict(raw["result"])
        fields = {}
        if raw["kind"] == "section":
            fields["sections"] = {**project["sections"], raw["target"]: result["content"]}
            inputs = dict(project["state"].get("_material_output_inputs", {}))
            inputs[raw["target"]] = {
                "snapshot": raw["payload"]["input_snapshot"],
                "sources": result.get("evidence", []),
                "blocks_version": digest(result["content"]),
            }
            fields["state"] = {**project["state"], "_material_output_inputs": inputs}
        elif raw["kind"] == "outline":
            fields["outline"] = result["outline"]
            fields["state"] = {**project["state"], "outline_confirmed": False}
        elif raw["kind"] == "plan":
            plan = FigureSpec.model_validate(result["plan"]).model_dump()
            fields["state"] = {**project["state"], "_material_plans": [
                p for p in project["state"].get("_material_plans", []) if p["id"] != plan["id"]
            ] + [plan]}
        elif raw["kind"] == "figure":
            folder = artifact_folder(store, project_id, raw)
            asset = {**result["asset"], "preview": str(folder / "figure.png"), "material_job_id": identifier}
            fields["diagrams"] = [d for d in project["diagrams"] if d["id"] != asset["id"]] + [asset]
        fields = prepare_update(project, fields) if fields else {}
        return queue.apply(raw, fields)

    @router.post("/figures/{figure_id}/confirm-text")
    def confirm_text(project_id: str, figure_id: str, payload: AcknowledgeInput):
        store, project = project_for(project_id)
        if payload.snapshot != material_view(project)["snapshot"]:
            raise HTTPException(409, "图片已变化，请重新核对")
        diagrams = copy.deepcopy(project["diagrams"])
        asset = next((d for d in diagrams if d["id"] == figure_id), None)
        if not asset or not asset.get("material_job_id"):
            raise HTTPException(404, "图片不存在")
        asset["text_confirmed"] = True
        return save(store, project, payload.revision, diagrams=diagrams)

    @router.get("/jobs/{identifier}/files/{name}")
    def download(project_id: str, identifier: str, name: str):
        store, _ = project_for(project_id)
        if not re.fullmatch(r"(proposal\.(docx|pdf)|figure\.png|base\.png|source\.(svg|html)|spec\.json|report\.json|page-\d{3}\.png)", name):
            raise HTTPException(404, "文件不存在")
        raw = MaterialJobs(store).call("raw", project_id=project_id, id=identifier)
        if not raw or raw["status"] != "completed":
            raise HTTPException(404, "任务产物不存在")
        path = artifact_folder(store, project_id, raw) / name
        if not path.is_file():
            raise HTTPException(404, "文件不存在")
        # HTML/SVG source is download-only to prevent active content in origin.
        return FileResponse(path, filename=name, headers={"Cache-Control": "private, no-store",
                             "X-Content-Type-Options": "nosniff"})

    app.include_router(router)
