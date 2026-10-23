"""Durable pilot queue. Cloud uses scoped RPCs; local mode uses SQLite.

Paid jobs with an expired lease become needs_review, never auto-replayed.
No user JWT, plaintext model credential, or service-role key is stored in jobs.
"""
from __future__ import annotations

import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from .materials import MaterialConflict

PUBLIC = ("id", "project_id", "kind", "target", "status", "step", "result", "error", "created_at", "updated_at")
TERMINAL = {"completed", "failed", "cancelled", "needs_review"}


def public_job(job):
    return {k: job.get(k) for k in PUBLIC} if job else None


class MaterialJobs:
    def __init__(self, store):
        self.store = store
        self.cloud = hasattr(store, "_rest")
        if not self.cloud:
            with store.connect() as db:
                db.execute("""CREATE TABLE IF NOT EXISTS material_jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL, target TEXT NOT NULL, idempotency TEXT NOT NULL, body TEXT NOT NULL,
                    UNIQUE(project_id, idempotency))""")

    def call(self, action: str, **args):
        if self.cloud:
            return self.store._rest("rpc/material_jobs_api", "POST", payload={"p_action": action, "p_args": args})
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            if action == "submit":
                project_row = db.execute("SELECT material_revision FROM projects WHERE id=?", (args["project_id"],)).fetchone()
                if not project_row:
                    raise PermissionError("项目不存在")
                rows = db.execute("SELECT body FROM material_jobs WHERE project_id=?", (args["project_id"],)).fetchall()
                for row in rows:
                    old = json.loads(row[0])
                    if old["idempotency"] == args["idempotency"]:
                        return public_job(old)
                    if (old["kind"], old["target"]) == (args["kind"], args["target"]) and old["status"] in {"pending", "running"}:
                        return public_job(old)
                if project_row["material_revision"] != args["payload"]["base_revision"]:
                    raise MaterialConflict("提交时项目已变化，尚未调用模型，请刷新后重试")
                body = dict(args, status="pending", step="queued", result={}, error="", created_at=now, updated_at=now)
                db.execute("INSERT INTO material_jobs VALUES (?,?,?,?,?,?)",
                           (args["id"], args["project_id"], args["kind"], args["target"], args["idempotency"], json.dumps(body)))
                return public_job(body)
            if action == "list":
                return [public_job(json.loads(r[0])) for r in db.execute(
                    "SELECT body FROM material_jobs WHERE project_id=? ORDER BY rowid DESC LIMIT 30", (args["project_id"],))]
            row = db.execute("SELECT body FROM material_jobs WHERE id=? AND project_id=?",
                             (args["id"], args["project_id"])).fetchone()
            if not row:
                return None
            body = json.loads(row[0])
            if action == "get":
                return public_job(body)
            if action == "cancel" and body["status"] not in TERMINAL:
                body["status"] = "cancelled"
                body["error"] = "已取消后续执行，已发生的调用费用仍按原规则核对"
                body["payload"].pop("config_ciphertext", None)
            elif action == "raw":
                return body
            elif action == "applied":
                body["result"] = args["result"]
            body["updated_at"] = now
            db.execute("UPDATE material_jobs SET body=? WHERE id=?", (json.dumps(body), body["id"]))
            return public_job(body)

    def submit(self, project_id, kind, target, payload, idempotency):
        if kind not in {"section", "figure", "export", "outline", "plan"} or not idempotency:
            raise ValueError("任务类型或幂等编号无效")
        result = self.call("submit", id=payload["job_id"], project_id=project_id, kind=kind,
                           target=target, payload=payload, idempotency=idempotency)
        if result and result.get("conflict"):
            raise MaterialConflict("提交时项目已变化，尚未调用模型，请刷新后重试")
        return result

    def find(self, project_id, idempotency):
        if self.cloud:
            rows = self.store._rest("material_jobs", params={
                "project_id": f"eq.{project_id}", "idempotency": f"eq.{idempotency}",
                "select": ",".join(PUBLIC), "limit": "1",
            })
            return rows[0] if rows else None
        with self.store.connect() as db:
            row = db.execute("SELECT body FROM material_jobs WHERE project_id=? AND idempotency=?",
                             (project_id, idempotency)).fetchone()
        return public_job(json.loads(row[0])) if row else None

    def claim_local(self):
        if self.cloud:
            raise RuntimeError("Cloud worker must use material_worker_rpc")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            for row in db.execute("SELECT body FROM material_jobs ORDER BY rowid").fetchall():
                body = json.loads(row[0])
                if body["status"] == "running" and body.get("lease_until", 0) < now:
                    body["status"] = "needs_review" if body["payload"].get("paid") else "pending"
                    body["error"] = "执行租约中断，需要核对调用结果" if body["status"] == "needs_review" else ""
                    if body["status"] == "needs_review":
                        body["payload"].pop("config_ciphertext", None)
                    db.execute("UPDATE material_jobs SET body=? WHERE id=?", (json.dumps(body), body["id"]))
                if body["status"] == "pending":
                    body.update(status="running", lease=secrets.token_hex(24), lease_until=now + 120, updated_at=now)
                    db.execute("UPDATE material_jobs SET body=? WHERE id=?", (json.dumps(body), body["id"]))
                    return body
        return None

    def apply(self, job, fields):
        args = {"id": job["id"], "project_id": job["project_id"],
                "revision": job["payload"]["base_revision"], "fields": fields}
        if self.cloud:
            result = self.store._rest("rpc/material_apply", "POST", payload={"p_args": args})
            return result
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM projects WHERE id=?", (job["project_id"],)).fetchone()
            stored = db.execute("SELECT body FROM material_jobs WHERE id=? AND project_id=?",
                                (job["id"], job["project_id"])).fetchone()
            if not row or not stored:
                raise PermissionError("项目或任务不存在")
            current_job = json.loads(stored[0])
            if current_job["status"] != "completed":
                raise MaterialConflict("任务未完成")
            result = dict(current_job["result"])
            if result.get("applied"):
                return result
            conflict = row["material_revision"] != args["revision"]
            if job["kind"] == "section":
                source = "ai_generated_alternative" if conflict else "ai_generated"
                db.execute("""INSERT OR IGNORE INTO section_versions
                    (id,project_id,section_id,source,content,review_card_json,created_at)
                    VALUES (?,?,?,?,?,?,datetime('now'))""",
                    (job["id"], job["project_id"], job["target"], source, result["content"],
                     json.dumps(result.get("review_card"))))
            if conflict:
                result["conflict_status"] = "user_edit_preserved"
                result["notice"] = "输入已变化，结果保留为备选，未覆盖当前项目"
                fields = {}
            if fields:
                from .materials import prepare_update
                fields = prepare_update(self.store._project_row(row), fields)
                keys = {"state", "sections", "diagrams", "outline"}
                columns = [f"{k}_json=?" for k in fields if k in keys]
                values = [json.dumps(v, ensure_ascii=False) for k, v in fields.items() if k in keys]
                db.execute(f"UPDATE projects SET {','.join(columns)},material_revision=material_revision+1 WHERE id=?",
                           [*values, job["project_id"]])
            result["applied"] = True
            current_job["result"] = result
            db.execute("UPDATE material_jobs SET body=? WHERE id=?", (json.dumps(current_job), job["id"]))
            return result

    def worker_local(self, job, action, **args):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM material_jobs WHERE id=?", (job["id"],)).fetchone()
            current = json.loads(row[0]) if row else {}
            if current.get("status") != "running" or current.get("lease") != job["lease"] or current.get("lease_until", 0) < time.time():
                raise MaterialConflict("任务已取消或租约失效")
            current.update(lease_until=time.time()+120, updated_at=time.time())
            if action == "finish":
                current.update(status=args["status"], result={**current.get("result", {}), **args.get("result", {})},
                               error=args.get("error", "")[:400])
                current["payload"].pop("config_ciphertext", None)
            elif action == "checkpoint":
                current["step"] = args["step"]
                current["result"].update(args.get("partial", {}))
            db.execute("UPDATE material_jobs SET body=? WHERE id=?", (json.dumps(current), job["id"]))
            return public_job(current)


def checked_bundle(data: bytes, folder: Path) -> None:
    """Only our bounded, flat artifact format; no Zip Slip or zip bombs."""
    import io
    import zipfile
    if len(data) > 100_000_000:
        raise ValueError("产物包过大")
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 170 or sum(x.file_size for x in entries) > 350_000_000:
            raise ValueError("产物解压大小超限")
        for item in entries:
            name = item.filename
            if Path(name).name != name or not name or name.startswith(".") or Path(name).suffix.lower() not in {".png", ".pdf", ".docx", ".json", ".svg", ".html"}:
                raise ValueError("无效产物文件名")
            (folder / name).write_bytes(archive.read(item))


def job_id() -> str:
    return uuid.uuid4().hex
