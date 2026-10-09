from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import new_id


request_identity: ContextVar[dict[str, str] | None] = ContextVar(
    "stardust_supabase_request_identity", default=None
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SupabaseStore:
    """Supabase REST + private Storage adapter, scoped to the request JWT."""

    bucket = "stardust-project-files"

    def __init__(
        self,
        project_url: str,
        publishable_key: str,
        data_dir: str | Path | None = None,
    ):
        self.project_url = project_url.rstrip("/")
        self.publishable_key = publishable_key
        configured = data_dir or os.environ.get("PROPOSAL_AGENT_TEMP_DIR", "/tmp/stardust-agent")
        self.data_dir = Path(configured).expanduser().resolve()
        self.files_dir = self.data_dir / "projects"
        self.files_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _json(value: Any, fallback: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return fallback
        return value if value is not None else fallback

    def _identity(self) -> dict[str, str]:
        identity = request_identity.get()
        if not identity or not identity.get("access_token") or not identity.get("user_id"):
            raise PermissionError("需要先登录，才能访问项目数据。")
        return identity

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        identity = self._identity()
        headers = {
            "apikey": self.publishable_key,
            "Authorization": f"Bearer {identity['access_token']}",
        }
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _query(params: list[tuple[str, str]] | dict[str, str] | None) -> str:
        if not params:
            return ""
        return urllib.parse.urlencode(params, doseq=True, safe="(),!*:")

    def _rest(
        self,
        table: str,
        method: str = "GET",
        params: list[tuple[str, str]] | dict[str, str] | None = None,
        payload: Any = None,
    ) -> Any:
        url = f"{self.project_url}/rest/v1/{table}"
        query = self._query(params)
        if query:
            url += f"?{query}"
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = self._headers({"Content-Type": "application/json"})
        if method in {"POST", "PATCH"}:
            headers["Prefer"] = "return=representation"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
            return json.loads(data.decode("utf-8")) if data else []
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"云端数据请求失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("无法连接 Supabase 云端数据库。") from exc

    def _storage(
        self,
        method: str,
        path: str,
        content: bytes | None = None,
        content_type: str = "application/octet-stream",
    ) -> bytes:
        url = f"{self.project_url}/storage/v1/object/{self.bucket}/{urllib.parse.quote(path, safe='/')}"
        headers = self._headers({"Content-Type": content_type})
        if method == "POST":
            headers["x-upsert"] = "false"
        request = urllib.request.Request(url, data=content, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"云端材料存储请求失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("无法连接 Supabase 材料存储。") from exc

    def _delete_storage(self, paths: list[str]) -> None:
        if not paths:
            return
        url = f"{self.project_url}/storage/v1/object/{self.bucket}"
        request = urllib.request.Request(
            url,
            data=json.dumps({"prefixes": paths}).encode("utf-8"),
            headers=self._headers({"Content-Type": "application/json"}),
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(request, timeout=45):
                pass
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"删除云端材料失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("无法连接 Supabase 材料存储。") from exc

    def _project_row(self, row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        result["state"] = self._json(result.pop("state_json", None), {})
        result["outline"] = self._json(result.pop("outline_json", None), [])
        result["sections"] = self._json(result.pop("sections_json", None), {})
        result["diagrams"] = self._json(result.pop("diagrams_json", None), [])
        return result

    def _document_row(self, row: dict[str, Any], download: bool = False) -> dict[str, Any]:
        result = dict(row)
        path = self.files_dir / str(result["project_id"]) / Path(result["storage_path"]).name
        path.parent.mkdir(parents=True, exist_ok=True)
        result["stored_path"] = str(path)
        if download and not path.is_file():
            data = self._storage("GET", result["storage_path"])
            path.write_bytes(data)
        return result

    def create_project(
        self,
        title: str = "我的大创项目",
        level: str = "",
        discipline: str = "",
        school: str = "",
    ) -> dict[str, Any]:
        identity = self._identity()
        project_id = new_id()
        row = self._rest(
            "projects",
            "POST",
            payload={
                "id": project_id,
                "owner_id": identity["user_id"],
                "title": str(title).strip()[:160] or "我的大创项目",
                "level": str(level).strip()[:40],
                "discipline": str(discipline).strip()[:100],
                "school": str(school).strip()[:120],
            },
        )
        (self.files_dir / project_id).mkdir(parents=True, exist_ok=True)
        return self._project_row(row[0])

    def list_projects(self) -> list[dict[str, Any]]:
        rows = self._rest("projects", params=[("select", "*"), ("order", "updated_at.desc")])
        return [self._project_row(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        rows = self._rest(
            "projects",
            params=[("select", "*"), ("id", f"eq.{project_id}"), ("limit", "1")],
        )
        return self._project_row(rows[0]) if rows else None

    def update_project(self, project_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {
            "title", "level", "discipline", "school", "state", "outline",
            "sections", "diagrams", "template_document_id",
        }
        payload: dict[str, Any] = {"updated_at": utc_now()}
        for key, value in fields.items():
            if key not in allowed:
                continue
            column = {
                "state": "state_json",
                "outline": "outline_json",
                "sections": "sections_json",
                "diagrams": "diagrams_json",
            }.get(key, key)
            payload[column] = value
        if len(payload) == 1:
            return self.get_project(project_id)
        rows = self._rest(
            "projects",
            "PATCH",
            params=[("id", f"eq.{project_id}"), ("select", "*")],
            payload=payload,
        )
        return self._project_row(rows[0]) if rows else None

    def add_document(
        self,
        project_id: str,
        original_name: str,
        stored_path: str,
        kind: str,
        content_type: str,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        identity = self._identity()
        document_id = document_id or new_id()
        path = Path(stored_path)
        storage_path = f"{identity['user_id']}/{project_id}/{document_id}{path.suffix.lower()}"
        self._storage("POST", storage_path, path.read_bytes(), content_type or "application/octet-stream")
        try:
            rows = self._rest(
                "documents",
                "POST",
                payload={
                    "id": document_id,
                    "project_id": project_id,
                    "original_name": Path(original_name).name,
                    "storage_path": storage_path,
                    "kind": kind,
                    "content_type": content_type,
                    "created_at": utc_now(),
                },
            )
        except Exception:
            self._delete_storage([storage_path])
            raise
        return self._document_row(rows[0])

    def register_document(
        self,
        project_id: str,
        document_id: str,
        original_name: str,
        storage_path: str,
        kind: str,
        content_type: str,
    ) -> dict[str, Any]:
        identity = self._identity()
        required_prefix = f"{identity['user_id']}/{project_id}/"
        if (
            not storage_path.startswith(required_prefix)
            or ".." in Path(storage_path).parts
            or Path(storage_path).name.split(".", 1)[0] != document_id
        ):
            raise PermissionError("上传路径与当前账号/项目不匹配。")
        project = self.get_project(project_id)
        if not project:
            raise PermissionError("项目不存在或不属于当前账号。")
        rows = self._rest(
            "documents",
            "POST",
            payload={
                "id": document_id,
                "project_id": project_id,
                "original_name": Path(original_name).name,
                "storage_path": storage_path,
                "kind": kind,
                "content_type": content_type,
                "created_at": utc_now(),
            },
        )
        return self._document_row(rows[0], download=True)

    def get_document(self, document_id: str, download: bool = True) -> dict[str, Any] | None:
        rows = self._rest(
            "documents",
            params=[("select", "*"), ("id", f"eq.{document_id}"), ("limit", "1")],
        )
        return self._document_row(rows[0], download=download) if rows else None

    def list_documents(self, project_id: str, download: bool = False) -> list[dict[str, Any]]:
        rows = self._rest(
            "documents",
            params=[
                ("select", "*"),
                ("project_id", f"eq.{project_id}"),
                ("order", "created_at.asc"),
            ],
        )
        return [self._document_row(row, download=download) for row in rows]

    def materialize_project_documents(self, project_id: str) -> None:
        for document in self.list_documents(project_id, download=False):
            self.get_document(document["id"], download=True)

    def persist_generated_file(
        self, project_id: str, filename: str, local_path: str | Path, content_type: str
    ) -> str:
        identity = self._identity()
        safe_name = Path(filename).name
        storage_path = f"{identity['user_id']}/{project_id}/_generated/{safe_name}"
        self._storage("POST", storage_path, Path(local_path).read_bytes(), content_type)
        return storage_path

    def read_generated_file(self, storage_path: str) -> bytes:
        return self._storage("GET", storage_path)

    def project_for_export(self, project_id: str) -> dict[str, Any] | None:
        project = self.get_project(project_id)
        if not project:
            return None
        self.materialize_project_documents(project_id)
        project = dict(project)
        project["diagrams"] = [dict(item) for item in project.get("diagrams", [])]
        for diagram in project["diagrams"]:
            preview = diagram.get("preview", "")
            if isinstance(preview, str) and preview.startswith("storage://"):
                storage_path = preview.removeprefix("storage://")
                local_path = self.files_dir / project_id / Path(storage_path).name
                local_path.parent.mkdir(parents=True, exist_ok=True)
                if not local_path.exists():
                    local_path.write_bytes(self.read_generated_file(storage_path))
                diagram["preview"] = str(local_path)
        return project

    def update_document_extraction(
        self,
        document_id: str,
        text: str,
        status: str,
        warning: str = "",
        low_confidence_count: int = 0,
        confirmed: bool = False,
    ) -> None:
        self._rest(
            "documents",
            "PATCH",
            params=[("id", f"eq.{document_id}")],
            payload={
                "extracted_text": text,
                "extraction_status": status,
                "extraction_warning": warning,
                "low_confidence_count": low_confidence_count,
                "confirmed": confirmed,
            },
        )

    def set_template_document(self, project_id: str, document_id: str | None) -> None:
        self.update_project(project_id, template_document_id=document_id)

    def replace_chunks(self, document_id: str, chunks: list[dict[str, Any]]) -> None:
        documents = self._rest(
            "documents",
            params=[
                ("select", "project_id,original_name"),
                ("id", f"eq.{document_id}"),
                ("limit", "1"),
            ],
        )
        if not documents:
            return
        document = documents[0]
        self._rest("chunks", "DELETE", params=[("document_id", f"eq.{document_id}")])
        if chunks:
            self._rest(
                "chunks",
                "POST",
                payload=[
                    {
                        "id": new_id(),
                        "project_id": document["project_id"],
                        "document_id": document_id,
                        "source_name": document["original_name"],
                        "source_ref": item["source_ref"],
                        "content": item["content"],
                        "embedding_json": item.get("embedding", []),
                        "created_at": utc_now(),
                    }
                    for item in chunks
                ],
            )

    def chunks_for_project(self, project_id: str) -> list[dict[str, Any]]:
        rows = self._rest(
            "chunks",
            params=[
                ("select", "*,documents!inner(confirmed,kind)"),
                ("project_id", f"eq.{project_id}"),
                ("documents.confirmed", "eq.true"),
                ("documents.kind", "neq.template"),
            ],
        )
        results = []
        for row in rows:
            item = dict(row)
            item["embedding"] = self._json(item.pop("embedding_json", None), [])
            item.pop("documents", None)
            results.append(item)
        return results

    def add_message(self, project_id: str, role: str, content: str) -> None:
        self._rest(
            "messages",
            "POST",
            payload={
                "id": new_id(),
                "project_id": project_id,
                "role": role,
                "content": content,
                "created_at": utc_now(),
            },
        )
        self._rest(
            "projects",
            "PATCH",
            params=[("id", f"eq.{project_id}")],
            payload={"updated_at": utc_now()},
        )

    def messages(self, project_id: str, limit: int = 30) -> list[dict[str, str]]:
        rows = self._rest(
            "messages",
            params=[
                ("select", "role,content"),
                ("project_id", f"eq.{project_id}"),
                ("order", "created_at.desc"),
                ("limit", str(limit)),
            ],
        )
        return [dict(row) for row in reversed(rows)]

    def delete_document(self, document_id: str) -> dict[str, Any] | None:
        document = self.get_document(document_id, download=False)
        if not document:
            return None
        self._delete_storage([document["storage_path"]])
        self._rest("documents", "DELETE", params=[("id", f"eq.{document_id}")])
        folder = self.files_dir / document["project_id"]
        (folder / Path(document["stored_path"]).name).unlink(missing_ok=True)
        return document

    def delete_project(self, project_id: str) -> bool:
        project = self.get_project(project_id)
        if not project:
            return False
        documents = self.list_documents(project_id, download=False)
        storage_paths = [doc["storage_path"] for doc in documents]
        storage_paths.extend(
            [
                value.removeprefix("storage://")
                for value in [
                    project.get("state", {}).get("exported_docx_storage_path", ""),
                    *[
                        diagram.get("preview", "")
                        for diagram in project.get("diagrams", [])
                        if isinstance(diagram, dict)
                    ],
                ]
                if isinstance(value, str) and value.startswith("storage://")
                or isinstance(value, str) and value.startswith(f"{self._identity()['user_id']}/{project_id}/_generated/")
            ]
        )
        self._delete_storage(storage_paths)
        self._rest("projects", "DELETE", params=[("id", f"eq.{project_id}")])
        folder = self.files_dir / project_id
        if folder.exists():
            for path in folder.iterdir():
                if path.is_file():
                    path.unlink()
            folder.rmdir()
        return True

    def record_token_usage(
        self,
        project_id: str,
        task_type: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: int = 0,
        key_fingerprint: str = "user-provided",
    ) -> None:
        try:
            self._rest(
                "token_usages",
                "POST",
                payload={
                    "id": new_id(),
                    "project_id": project_id,
                    "task_type": task_type,
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens or prompt_tokens + completion_tokens,
                    "latency_ms": latency_ms,
                    "key_fingerprint": key_fingerprint,
                    "created_at": utc_now(),
                },
            )
        except Exception:
            # Usage recording must not break project work.
            return

    def get_token_stats(self, project_id: str | None = None) -> dict[str, Any]:
        params = [("select", "task_type,prompt_tokens,completion_tokens,total_tokens,latency_ms")]
        if project_id:
            params.append(("project_id", f"eq.{project_id}"))
        rows = self._rest("token_usages", params=params)
        summary = {
            "call_count": len(rows),
            "total_prompt_tokens": sum(row["prompt_tokens"] for row in rows),
            "total_completion_tokens": sum(row["completion_tokens"] for row in rows),
            "grand_total_tokens": sum(row["total_tokens"] for row in rows),
            "avg_latency_ms": (
                sum(row["latency_ms"] for row in rows) / len(rows) if rows else 0
            ),
        }
        by_task: dict[str, dict[str, int]] = {}
        for row in rows:
            item = by_task.setdefault(row["task_type"], {"count": 0, "tokens": 0})
            item["count"] += 1
            item["tokens"] += row["total_tokens"]
        summary["by_task"] = [
            {"task_type": key, **value} for key, value in by_task.items()
        ]
        return summary
