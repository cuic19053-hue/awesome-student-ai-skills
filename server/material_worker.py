"""Single-process durable material worker. Run separately from the Vercel API.

Cloud: SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, MATERIAL_WORKER_SECRET.
Local: --local-data /path/to/.agent-data (explicit development mode only).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from proposal.material_jobs import MaterialJobs, checked_bundle
from proposal.material_figures import FigureSpec, render_svg, render_python, compose_text, check_scene_text, image_prompt
from proposal.material_export import export_material, check_pages
from proposal.materials import MaterialConflict
from proposal.storage import Store
from proposal.model_config_security import decrypt_config

log = logging.getLogger("material_worker")


class CloudQueue:
    def __init__(self):
        self.url = os.environ["SUPABASE_URL"].rstrip("/")
        self.key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
        self.secret = os.environ["MATERIAL_WORKER_SECRET"]

    def call(self, action, job=None, **args):
        from proposal.supabase_http import supabase_urlopen
        payload = {"p_secret": self.secret, "p_action": action,
                   "p_args": {**({"id": job["id"], "lease": job["lease"]} if job else {}), **args}}
        request = urllib.request.Request(self.url + "/rest/v1/rpc/material_worker_rpc",
            data=json.dumps(payload).encode(), method="POST",
            headers={"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with supabase_urlopen(request, timeout=20) as response:
            body = response.read()
            return json.loads(body) if body else None


class MeterStore:
    def __init__(self, queue, job):
        self.queue, self.job = queue, job

    def reserve_workbench_usage(self, user_id, request_id, model, amount, api_key_id=None):
        return self.queue.call("reserve", self.job, request_id=request_id, model=model, api_key_id=api_key_id)

    def settle_workbench_usage(self, request_id, amount, provider_id):
        return self.queue.call("settle", self.job, request_id=request_id, amount=amount, provider_id=provider_id)

    def refund_workbench_usage(self, request_id, reason="provider_error"):
        return self.queue.call("refund", self.job, request_id=request_id, reason=reason)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("任务文件不允许重定向")


def transfer(url, *, upload=None):
    configured = urllib.parse.urlparse(os.environ.get("SUPABASE_URL", ""))
    target = urllib.parse.urlparse(url)
    if (target.scheme != "https" or (target.scheme, target.netloc) != (configured.scheme, configured.netloc)
            or target.username or target.password
            or not target.path.startswith("/storage/v1/object/")):
        raise ValueError("任务传输地址不属于配置的私有存储")
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(url, data=upload, method="PUT" if upload is not None else "GET",
        headers={"Content-Type": "application/zip"} if upload is not None else {})
    with opener.open(request, timeout=90) as response:
        data = response.read(100_000_001)
    if len(data) > 100_000_000:
        raise ValueError("任务文件大小超限")
    return data


def hydrate(job, folder, local_source=None):
    """Install only this immutable project into an isolated temporary store."""
    payload = job["payload"]
    project = payload["project"]
    project_id = job["project_id"]
    import re
    if project["id"] != project_id or not re.fullmatch(r"[a-f0-9]{32}", project_id):
        raise ValueError("任务与项目不匹配")
    store = Store(folder / "input")
    with store.connect() as db:
        db.execute("""INSERT INTO projects(id,title,level,discipline,school,state_json,outline_json,
            sections_json,diagrams_json,template_document_id,created_at,updated_at,material_revision)
            VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'),?)""",
            (project_id,project["title"],project.get("level",""),project.get("discipline",""),project.get("school",""),
             json.dumps(project["state"]),json.dumps(project["outline"]),json.dumps(project["sections"]),
             json.dumps(project["diagrams"]),None,project.get("material_revision",0)))
    downloads = {(x["kind"], x["id"]): x["url"] for x in payload.get("downloads", [])}
    for doc in payload.get("documents", []):
        if not re.fullmatch(r"[a-f0-9]{32}", doc["id"]):
            raise ValueError("无效材料编号")
        suffix = Path(doc["original_name"]).suffix.lower()
        target = store.files_dir / project_id / (doc["id"] + suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        if ("document", doc["id"]) in downloads:
            target.write_bytes(transfer(downloads["document", doc["id"]]))
        elif local_source and doc.get("stored_path"):
            source = Path(doc["stored_path"]).resolve()
            source.relative_to(local_source.files_dir.resolve() / project_id)
            shutil.copyfile(source, target)
        else:
            # Text-only records can still contribute to grounded writing.
            target = target.with_suffix(".txt")
            target.write_text(doc.get("extracted_text", ""), encoding="utf-8")
        store.add_document(project_id, doc["original_name"], str(target), doc["kind"], doc.get("content_type",""),
                           document_id=doc["id"])
        store.update_document_extraction(doc["id"], doc.get("extracted_text",""), doc.get("extraction_status","ready"),
            doc.get("extraction_warning",""), doc.get("low_confidence_count",0), confirmed=bool(doc.get("confirmed")))
    with store.connect() as db:
        db.execute("UPDATE projects SET template_document_id=? WHERE id=?", (project.get("template_document_id"),project_id))
    for message in payload.get("messages", []):
        store.add_message(project_id, message["role"], message["content"])
    for doc in payload.get("documents", []):
        if not doc.get("confirmed"):
            continue
        chunks = [c for c in payload.get("chunks", []) if c.get("document_id") == doc["id"]]
        store.replace_chunks(doc["id"], chunks)
    diagrams = []
    for figure in project["diagrams"]:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", figure["id"]):
            raise ValueError("无效图表编号")
        item = dict(figure)
        item["preview"] = ""
        if ("figure", figure["id"]) in downloads:
            dest = folder / ("asset-" + figure["id"])
            checked_bundle(transfer(downloads["figure", figure["id"]]), dest)
            item["preview"] = str(dest / "figure.png")
        elif local_source and figure.get("preview"):
            source = Path(figure["preview"]).resolve()
            source.relative_to(local_source.files_dir.resolve() / project_id)
            dest = folder / ("figure-" + figure["id"] + ".png")
            shutil.copyfile(source, dest)
            item["preview"] = str(dest)
        diagrams.append(item)
    # Restore snapshot exactly; hydration operations must not alter its revision.
    with store.connect() as db:
        db.execute("UPDATE projects SET state_json=?,diagrams_json=?,material_revision=? WHERE id=?",
                   (json.dumps(project["state"]),json.dumps(diagrams),project.get("material_revision",0),project_id))
    base = None
    spec = payload.get("spec") or {}
    if spec.get("base_asset_job"):
        dest = folder / "base-input"
        if ("base", spec["id"]) in downloads:
            checked_bundle(transfer(downloads["base", spec["id"]]), dest)
        elif local_source:
            source = local_source.files_dir / project_id / "_material" / spec["base_asset_job"]
            dest.mkdir()
            for name in ("base.png", "figure.png"):
                if (source / name).is_file():
                    shutil.copyfile(source / name, dest / name)
        base = dest / ("base.png" if (dest / "base.png").is_file() else "figure.png")
    return store, base


def execute(job, workspace, checkpoint, local_source=None, queue=None):
    payload = job["payload"]
    output = workspace / "output"
    output.mkdir()
    checkpoint("preparing_inputs")
    store, base = hydrate(job, workspace, local_source)
    from proposal.tools import ProposalTools
    from proposal.retrieval import ProjectRetriever
    from proposal.agent import OllamaAgent
    class NoEmbed:
        def embed(self, _):
            return None
    tools = ProposalTools(store, ProjectRetriever(store, NoEmbed()))
    config = payload.get("config", {})
    if payload.get("config_ciphertext"):
        config = decrypt_config(payload["owner_id"], payload["config_ciphertext"])
    if job.get("owner_id") and job["owner_id"] != payload["owner_id"]:
        raise ValueError("任务身份不匹配")
    candidate = None
    meter = None
    if job["kind"] in {"section", "outline", "plan"} or (payload.get("spec") or {}).get("renderer") == "gpt":
        # Reuse existing model config and platform readiness checks, never introduce pricing.
        import app as api
        from proposal.supabase_store import request_identity
        if bool(payload.get("platform")) != (config.get("provider") == "preset"):
            raise ValueError("任务模型配置与计费方式不一致")
        if payload.get("platform"):
            if not api._platform_bundle_ready(require_ledger=False):
                raise ValueError("平台模型尚未开通或已暂停")
            from proposal.workbench_metering import WorkbenchMeter
            meter_store = MeterStore(queue, job) if queue else local_source
            meter = WorkbenchMeter(meter_store, payload["owner_id"], int(os.environ["WOPALLY_WORKBENCH_API_KEY_ID"]))
            candidate = OllamaAgent(
                store, tools, base_url=os.environ["WOPALLY_MODEL_BASE_URL"],
                model="deepseek-v4-flash", provider="openai_compatible",
                api_key=os.environ["WOPALLY_WORKBENCH_API_KEY"], meter=meter, platform_transport=True,
            )
        else:
            previous = api.store, api.tools, api.agent
            api.store, api.tools, api.agent = store, tools, OllamaAgent(store, tools)
            try:
                candidate = api._agent_for_config(api.LLMConfigInput(**config), project_id=job["project_id"])
            finally:
                api.store, api.tools, api.agent = previous
        from proposal.material_network import safe_urlopen
        candidate.request_opener = safe_urlopen
        candidate.single_attempt = True
        # Check the lease/cancellation before EVERY draft/critic request, including BYOK.
        original_post = candidate._post
        def guarded_post(*args, **kwargs):
            checkpoint("model_request")
            response = original_post(*args, **kwargs)
            # Preserve deliverable draft if a later critic/settlement step fails.
            request_body = args[1] if len(args) > 1 else {}
            if not isinstance(request_body.get("format"), dict):
                checkpoint("draft_saved", partial={"partial_content": str(response.get("message", {}).get("content", ""))[:40000]})
            return response
        candidate._post = guarded_post
    if job["kind"] == "outline":
        checkpoint("planning_outline")
        proposed = candidate.propose_outline(job["project_id"])
        # Normalize IDs before they can become API paths or figure anchors.
        import re
        seen, outline = set(), []
        for index, item in enumerate(proposed):
            sid = re.sub(r"[^a-zA-Z0-9_-]", "_", item["id"])[:70] or f"section_{index+1}"
            if sid in seen:
                sid = f"section_{index+1}"
            seen.add(sid)
            outline.append({"id": sid, "title": item["title"]})
        return {"outline": outline, "confirmed": False, "input_snapshot": payload["input_snapshot"]}
    if job["kind"] == "plan":
        checkpoint("planning_figure")
        proposed = candidate.propose_diagram(job["project_id"], "研究流程与技术路线")
        spec = FigureSpec(id=("suggested_"+job["target"])[:60], section_id=job["target"],
            title=proposed["title"][:100], renderer="svg", nodes=proposed["nodes"],
            source="依据已确认项目资料拟定的研究计划，待用户核对", confirmed=False)
        return {"plan": spec.model_dump(), "notice": proposed.get("notice", "请核对节点与顺序后再确认生成"),
                "input_snapshot": payload["input_snapshot"]}
    if job["kind"] == "section":
        checkpoint("writing_and_existing_review")
        result = candidate.generate_section(job["project_id"], job["target"], persist=False)
        from proposal.material_export import blocks
        result["blocks"] = blocks(result["content"])
        result["input_snapshot"] = payload["input_snapshot"]
        result["usage"] = store.get_token_stats(job["project_id"])
        return result
    if job["kind"] == "figure":
        spec = FigureSpec.model_validate(payload["spec"])
        checkpoint("drawing")
        (output / "spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        if spec.renderer == "svg":
            render_svg(spec, output)
        elif spec.renderer == "python":
            render_python(spec, output)
        elif spec.renderer == "overlay":
            if not base or not base.is_file():
                raise ValueError("原始底图不可用")
            shutil.copyfile(base, output / "base.png")
            compose_text(base, spec, output)
        elif spec.renderer == "upload":
            document = store.get_document(spec.document_id)
            if not document:
                raise ValueError("真实上传图片不存在")
            from PIL import Image
            with Image.open(document["stored_path"]) as picture:
                if picture.width * picture.height > 25_000_000:
                    raise ValueError("图片尺寸超限")
                picture.convert("RGB").save(output / "base.png")
            shutil.copyfile(output / "base.png", output / "figure.png")
        else:
            from proposal.workbench_images import generate_image, generate_custom_image
            prompt = image_prompt(spec, payload["project"])
            if meter:
                image = generate_image(prompt, meter)
            elif config.get("provider") == "openai_compatible":
                reuse = config.get("image_reuse_text", False)
                image = generate_custom_image(prompt, config["base_url"] if reuse else config.get("image_base_url") or config["base_url"],
                    config.get("image_model") or "gpt-image-2", config["api_key"] if reuse else config.get("image_api_key") or config["api_key"],
                    opener=safe_urlopen)
            else:
                raise ValueError("概念生图需要平台模型或自定义生图 API")
            (output / "base.png").write_bytes(image)
            if spec.overlays:
                compose_text(output / "base.png", spec, output)
            else:
                shutil.copyfile(output / "base.png", output / "figure.png")
        checkpoint("checking_figure_text")
        quality = check_scene_text(output / "figure.png", spec.scene_text)
        if spec.renderer == "svg" and len(spec.nodes) > 10:
            quality = {"status": "needs_review", "notice": "节点较多，请拆分图表，核对插入 Word 后的文字大小"}
        return {"asset": {**spec.model_dump(), "text_confirmed": False, "text_check": quality,
                          "input_snapshot": payload["input_snapshot"]}, "quality": quality}
    checkpoint("assembling_document")
    report = export_material(store, job["project_id"], output)
    report["input_snapshot"] = payload["input_snapshot"]
    checkpoint("rendering_pages")
    try:
        report = check_pages(output, report)
    except Exception:
        report.update(quality_status="not_checked", pages=[], checks=[
            {"rule": "page_render", "status": "not_checked", "detail": "渲染未完成，Word 草稿保留，请人工核对"}])
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": report}


def run_one(local_store=None, queue=None):
    repository = MaterialJobs(local_store) if local_store else None
    job = repository.claim_local() if repository else queue.call("claim")
    if not job:
        return False
    stop, lost = threading.Event(), threading.Event()

    def update(action, **args):
        if lost.is_set():
            raise MaterialConflict("任务租约已失效")
        return repository.worker_local(job, action, **args) if repository else queue.call(action, job, **args)

    def heartbeat():
        while not stop.wait(20):
            try:
                update("heartbeat")
            except Exception:
                lost.set()
                return

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="material-job-") as temp:
            workspace = Path(temp)
            result = execute(job, workspace, lambda step, **extra: update("checkpoint", step=step, **extra), local_store, queue)
            update("checkpoint", step="saving_artifacts")
            output = workspace / "output"
            bundle = workspace / "bundle.zip"
            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
                for file in output.iterdir():
                    if file.is_file() and file.suffix in {".png", ".docx", ".pdf", ".json", ".html", ".svg"}:
                        archive.write(file, file.name)
            if local_store:
                dest = local_store.files_dir / job["project_id"] / "_material" / job["id"]
                checked_bundle(bundle.read_bytes(), dest)
            elif job["payload"].get("upload_url"):
                transfer(job["payload"]["upload_url"], upload=bundle.read_bytes())
            update("finish", status="completed", result=result)
    except Exception as exc:
        # Do not expose provider keys, signed URLs, raw responses or project materials.
        log.warning("job=%s error_type=%s", job["id"], type(exc).__name__)
        public_errors = {
            "中文字体不可用，拒绝生成可能乱码的图片",
            "指定字体缺少图表所需字形，请更换有授权的完整中文字体",
            "原始底图不可用", "真实上传图片不存在", "图片尺寸超限",
        }
        try:
            update("finish", status="needs_review" if job["payload"].get("paid") else "failed",
                   error=str(exc) if str(exc) in public_errors else
                   "执行未完成，请核对该步骤；已发生的模型调用按原规则结算，不自动重复调用")
        except Exception:
            pass  # Lost lease/cancelled: never overwrite terminal state.
    finally:
        stop.set()
        thread.join(timeout=2)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-data", type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    os.environ["MATERIAL_PIPELINE_ENABLED"] = "true"
    local = Store(args.local_data) if args.local_data else None
    queue = None if local else CloudQueue()
    while True:
        try:
            worked = run_one(local, queue)
        except Exception as exc:
            log.warning("queue unavailable error_type=%s", type(exc).__name__)
            worked = False
        if args.once:
            break
        if not worked:
            time.sleep(3)


if __name__ == "__main__":
    main()
