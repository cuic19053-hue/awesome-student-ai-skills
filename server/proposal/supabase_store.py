from __future__ import annotations

import json
import hashlib
import os
import urllib.error
import urllib.parse
import urllib.request
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import CreditRateLimitError, InsufficientCreditsError, PendingUsageError, new_id
from .billing_policy import normalize_trial_wallet
from .supabase_http import supabase_urlopen


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
        service_role_key: str | None = None,
    ):
        self.project_url = project_url.rstrip("/")
        self.publishable_key = publishable_key
        self.service_role_key = (
            service_role_key
            if service_role_key is not None
            else os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        ).strip()
        self.backend_secret = os.environ.get("WORKBENCH_BACKEND_SECRET", "").strip()
        configured = data_dir or os.environ.get("PROPOSAL_AGENT_TEMP_DIR", "/tmp/stardust-agent")
        self.data_dir = Path(configured).expanduser().resolve()
        self.files_dir = self.data_dir / "projects"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        from .storage import Store
        self._job_store = Store(self.data_dir / "jobs_store.db")

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

    def get_model_config(self):
        owner = self._identity()["user_id"]
        rows = self._rest("user_model_configs", params={
            "owner_id": f"eq.{owner}", "select": "ciphertext,updated_at",
        })
        if not rows:
            return None
        from .model_config_security import decrypt_config
        return decrypt_config(owner, rows[0]["ciphertext"])

    def save_model_config(self, config):
        owner = self._identity()["user_id"]
        from .model_config_security import encrypt_config
        payload = {
            "owner_id": owner, "ciphertext": encrypt_config(owner, config),
            "updated_at": utc_now(),
        }
        # 单条 upsert 原子替换，不先删后插，避免失败时丢失旧凭据。
        url = f"{self.project_url}/rest/v1/user_model_configs?on_conflict=owner_id"
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode(), method="POST",
            headers=self._headers({
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            }),
        )
        try:
            with supabase_urlopen(request, timeout=20):
                pass
        except (urllib.error.URLError, OSError):
            raise RuntimeError("云端模型配置保存失败，请稍后重试。") from None

    def delete_model_config(self):
        self._rest("user_model_configs", "DELETE", {"owner_id": f"eq.{self._identity()['user_id']}"})

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
            with supabase_urlopen(request, timeout=20) as response:
                data = response.read()
            return json.loads(data.decode("utf-8")) if data else []
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"云端数据请求失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("无法连接 Supabase 云端数据库。") from exc

    def _service_rpc(self, function: str, payload: dict[str, Any]) -> Any:
        if self.service_role_key:
            headers = {
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Content-Type": "application/json",
                "Content-Profile": "public",
                "Accept-Profile": "public",
            }
        elif self.backend_secret and function in {
            "workbench_lookup_paired_voucher", "workbench_begin_card_redemption",
            "workbench_complete_paired_voucher", "workbench_set_card_redemption_status",
            "workbench_complete_card_redemption",
            "workbench_reserve_usage", "workbench_settle_usage", "workbench_refund_usage",
            "workbench_get_intent",
            "workbench_consume_free_chat", "workbench_refund_free_chat",
        }:
            headers = self._headers({
                "Content-Type": "application/json",
                "Content-Profile": "public",
                "Accept-Profile": "public",
            })
            payload = {**payload, "p_server_secret": self.backend_secret}
            function = function.replace("workbench_", "workbench_backend_", 1)
        else:
            raise RuntimeError("云端积分账本未配置服务端密钥。")
        url = f"{self.project_url}/rest/v1/rpc/{urllib.parse.quote(function, safe='')}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            timeout = (
                2 if function.endswith("settle_usage")
                and os.environ.get("BILLING_BACKGROUND_RECONCILIATION", "").lower() == "true"
                else 20
            )
            with supabase_urlopen(request, timeout=timeout) as response:
                data = response.read()
            return json.loads(data.decode("utf-8")) if data else None
        except urllib.error.HTTPError as exc:
            try:
                error_data = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                error_data = {}
            if isinstance(error_data, dict) and error_data.get("code") == "54000":
                raise CreditRateLimitError("卡密兑换过于频繁，请一小时后再试。") from exc
            if isinstance(error_data, dict) and error_data.get("code") == "23514":
                raise InsufficientCreditsError("积分不足。请兑换卡密或切换自带 API Key。") from exc
            if (isinstance(error_data, dict) and error_data.get("code") == "55000"
                    and "reserve_usage" in function
                    and error_data.get("message") == "prior model charge pending review"):
                raise PendingUsageError("有一笔模型用量正在核对，请稍后重试。") from exc
            if isinstance(error_data, dict) and error_data.get("code") == "42501":
                raise PermissionError("登录身份或服务端授权无效。") from exc
            raise RuntimeError(f"云端积分账本请求失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("无法连接 Supabase 积分账本。") from exc

    @staticmethod
    def _rpc_result(result: Any) -> dict[str, Any]:
        if isinstance(result, list) and result:
            result = result[0]
        if not isinstance(result, dict):
            raise RuntimeError("云端积分账本返回格式无法识别。")
        return result

    def grant_workbench_payment_credits(
        self, user_id: str, event_id: str, amount_micro_cny: int
    ) -> dict[str, Any]:
        return self._rpc_result(
            self._service_rpc(
                "workbench_grant_payment_credits",
                {
                    "p_user_id": user_id,
                    "p_event_id": event_id,
                    "p_amount_micro_cny": int(amount_micro_cny),
                },
            )
        )

    def _storage(
        self,
        method: str,
        path: str,
        content: bytes | None = None,
        content_type: str = "application/octet-stream",
        upsert: bool = False,
    ) -> bytes:
        url = f"{self.project_url}/storage/v1/object/{self.bucket}/{urllib.parse.quote(path, safe='/')}"
        headers = self._headers({"Content-Type": content_type})
        if method == "POST":
            headers["x-upsert"] = "true" if upsert else "false"
        request = urllib.request.Request(url, data=content, headers=headers, method=method)
        try:
            with supabase_urlopen(request, timeout=45) as response:
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
            with supabase_urlopen(request, timeout=45):
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
        from .materials import attach_material
        return attach_material(result)

    def _document_row(self, row: dict[str, Any], download: bool = False) -> dict[str, Any]:
        result = dict(row)
        if result.get("kind") != "template" and result.get("confirmation_origin") != "user":
            result["confirmed"] = False
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
        from .materials import MaterialConflict, enabled, prepare_update
        expected = fields.pop("expected_revision", None)
        if os.environ.get("MATERIAL_PIPELINE_ENABLED", "").lower() == "true" or expected is not None:
            previous = self.get_project(project_id)
            if not previous:
                return None
            if enabled(previous) or expected is not None:
                revision = previous.get("material_revision", 0)
                if expected is not None and expected != revision:
                    raise MaterialConflict("项目已变化，请刷新后重试")
                result = self._rest("rpc/material_patch", "POST", payload={
                    "p_project_id": project_id, "p_revision": revision,
                    "p_fields": prepare_update(previous, fields),
                })
                if result and result.get("conflict"):
                    raise MaterialConflict("项目已变化，请刷新后重试")
                return self._project_row(result) if result else None
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
        download: bool = True,
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
        existing = self.get_document(document_id, download=False)
        if existing:
            if (existing["project_id"] != project_id or existing["storage_path"] != storage_path
                    or existing["kind"] != kind):
                raise PermissionError("材料编号已被其他上传使用。")
            return self._document_row(existing, download=download)
        # Check that upload finished before creating a material record; no file body
        # needs to pass through the registration request.
        self._storage("HEAD", storage_path)
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
        return self._document_row(rows[0], download=download)

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
        # Keep storage object keys ASCII-only. Supabase Storage rejects some
        # non-ASCII object keys (e.g. the Chinese "申报书草稿.docx") as InvalidKey.
        # The user-facing download name is set separately in download_docx.
        safe_name = "generated-" + Path(filename).suffix.lower().lstrip(".")
        storage_path = f"{identity['user_id']}/{project_id}/_generated/{safe_name}"
        self._storage(
            "POST",
            storage_path,
            Path(local_path).read_bytes(),
            content_type,
            upsert=True,
        )
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
        confirmed_by_user: bool = False,
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
                "confirmation_origin": "user" if confirmed and confirmed_by_user else "",
            },
        )
        from .materials import touch_document
        if os.environ.get("MATERIAL_PIPELINE_ENABLED", "").lower() == "true":
            document = self.get_document(document_id, download=False)
            if document:
                touch_document(self, document)

    def set_template_document(self, project_id: str, document_id: str | None) -> None:
        self.update_project(project_id, template_document_id=document_id)

    def replace_chunks(self, document_id: str, chunks: list[dict[str, Any]], *, expected_text: str | None = None) -> None:
        if not chunks:
            # Revocation must also work while the document is unconfirmed.
            self._rest("chunks", "DELETE", params=[("document_id", f"eq.{document_id}")])
            return
        if expected_text is None:
            raise ValueError("云端索引需要提供已确认材料的原始文字。")
        rows = []
        for item in chunks:
            row = {"id": new_id(), "source_ref": item["source_ref"], "content": item["content"]}
            embedding = item.get("embedding", [])
            revision = item.get("embedding_revision", "")
            if item.get("embedding_model") == "bge-m3" and revision and len(embedding) == 1024:
                row.update(embedding=embedding, embedding_model="bge-m3", embedding_revision=revision)
            rows.append(row)
        try:
            self._rest(
                "rpc/rag_replace_project_chunks", "POST",
                payload={"p_document_id": document_id,
                         "p_expected_sha256": hashlib.sha256(expected_text.encode("utf-8")).hexdigest(),
                         "p_chunks": rows},
            )
        except RuntimeError as exc:
            if isinstance(exc.__cause__, urllib.error.HTTPError) and exc.__cause__.code == 409:
                from .materials import MaterialConflict
                raise MaterialConflict("材料在索引期间发生变化，请重新核对后确认。") from None
            raise

    def search_project_chunks(
        self, project_id: str, terms: list[str], embedding: list[float] | None, model: str, model_revision: str = ""
    ) -> list[dict[str, Any]]:
        """Run under the request JWT, never the privileged service role."""
        self._identity()
        return self._rest(
            "rpc/rag_project_search",
            "POST",
            payload={
                "p_project_id": project_id,
                "p_terms": terms[:80],
                "p_embedding": embedding if embedding and len(embedding) == 1024 else None,
                "p_model": model,
                "p_model_revision": model_revision,
                "p_limit": 30,
            },
        )

    def search_public_knowledge(
        self, skill_id: str, school: str, year: int | None,
        terms: list[str], embedding: list[float] | None, embedding_revision: str = "", variant: str = "",
        filters: dict[str, str] | None = None, official_only: bool = False, include_examples: bool = False,
    ) -> list[dict[str, Any]]:
        """Read only published public sources under the current user's JWT."""
        self._identity()
        return self._rest(
            "rpc/rag_search_public_knowledge",
            "POST",
            payload={
                "p_skill_id": skill_id,
                "p_school": school,
                "p_year": year,
                "p_terms": terms[:80],
                "p_embedding": embedding if embedding and len(embedding) == 1024 else None,
                "p_embedding_revision": embedding_revision,
                "p_variant": variant,
                "p_filters": filters or {},
                "p_official_only": official_only,
                "p_include_examples": include_examples,
                "p_limit": 30,
            },
        )

    def chunks_for_project(self, project_id: str) -> list[dict[str, Any]]:
        rows = self._rest(
            "chunks",
            params=[
                ("select", "*,documents!inner(confirmed,kind)"),
                ("project_id", f"eq.{project_id}"),
                ("documents.project_id", f"eq.{project_id}"),
                ("documents.confirmed", "eq.true"),
                ("documents.confirmation_origin", "eq.user"),
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
        from .materials import touch_document
        touch_document(self, document, deleted=True)
        return document

    def delete_project(self, project_id: str) -> bool:
        project = self.get_project(project_id)
        if not project:
            return False
        documents = self.list_documents(project_id, download=False)
        storage_paths = [doc["storage_path"] for doc in documents]
        if "_material_tracking" in project.get("state", {}):
            offset = 0
            while True:
                rows = self._rest("material_jobs", params={
                    "project_id": f"eq.{project_id}", "select": "payload",
                    "limit": "500", "offset": str(offset),
                })
                prefix = f"{self._identity()['user_id']}/{project_id}/_material/"
                storage_paths.extend(row["payload"]["output_path"] for row in rows
                    if str(row["payload"].get("output_path", "")).startswith(prefix))
                if len(rows) < 500:
                    break
                offset += 500
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

    def get_workbench_credit_balance(self, user_id: str | None = None) -> dict[str, Any]:
        identity = self._identity()
        owner_id = user_id or identity["user_id"]
        if owner_id != identity["user_id"]:
            raise PermissionError("不能查看其他用户的积分余额。")
        rows = self._rest(
            "workbench_credit_wallets",
            params=[
                ("select", "user_id,balance_micro_cny,total_credited_micro_cny,total_spent_micro_cny,free_chat_count,created_at,updated_at"),
                ("user_id", f"eq.{owner_id}"),
                ("limit", "1"),
            ],
        )
        if rows:
            return normalize_trial_wallet(
                rows[0], registered_at=identity.get("registered_at"), require_registration=True,
            )
        return {
            "user_id": owner_id,
            "balance_micro_cny": 0,
            "total_credited_micro_cny": 0,
            "total_spent_micro_cny": 0,
            # Only the signup trigger grants trials; a missing wallet is not a new user.
            "free_chat_count": 0,
            "trial_eligible": False,
            "updated_at": None,
        }

    def consume_free_chat(self, user_id: str) -> int:
        identity = self._identity()
        if str(user_id) != identity["user_id"]:
            raise PermissionError("用户身份不匹配。")
        if self.get_workbench_credit_balance(user_id)["free_chat_count"] <= 0:
            return -1
        res = self._service_rpc("workbench_consume_free_chat", {"p_user_id": user_id})
        return int(res) if res is not None else -1

    def refund_free_chat(self, user_id: str) -> int:
        identity = self._identity()
        if str(user_id) != identity["user_id"]:
            raise PermissionError("用户身份不匹配。")
        if not self.get_workbench_credit_balance(user_id).get("trial_eligible"):
            return 0
        res = self._service_rpc("workbench_refund_free_chat", {"p_user_id": user_id})
        return int(res) if res is not None else 0

    def get_workbench_credit_transactions(self, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
        identity = self._identity()
        if str(user_id) != identity["user_id"]:
            raise PermissionError("不能查看其他用户的积分流水。")
        return self._rest(
            "workbench_credit_transactions",
            params=[
                ("select", "id,delta_micro_cny,balance_after_micro_cny,kind,reference_id,model,request_id,created_at"),
                ("user_id", f"eq.{user_id}"),
                ("order", "created_at.desc"),
                ("limit", str(max(1, min(100, int(limit))))),
            ],
        )

    def redeem_workbench_voucher(self, user_id: str, code: str) -> dict[str, Any]:
        identity = self._identity()
        if str(user_id) != identity["user_id"]:
            raise PermissionError("用户身份不匹配。")
        request = urllib.request.Request(
            f"{self.project_url}/rest/v1/rpc/workbench_redeem_voucher",
            data=json.dumps({"p_code": code}, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(
                {"Content-Type": "application/json", "Accept-Profile": "public"}
            ),
            method="POST",
        )
        try:
            with supabase_urlopen(request, timeout=20) as response:
                return self._rpc_result(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = {}
            code_name = body.get("code") if isinstance(body, dict) else None
            if code_name in {"P0002", "22023", "23505", "55000"}:
                raise ValueError("卡密无效、尚未启用或已被兑换。") from exc
            if code_name == "42501" or exc.code in {401, 403}:
                raise PermissionError("登录已失效，请重新登录。") from exc
            raise RuntimeError(f"云端卡密兑换失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("暂时无法连接工作台卡密账本，请稍后查询余额。") from exc

    def lookup_paired_voucher(self, code_hash: bytes) -> dict[str, Any]:
        result = self._rpc_result(self._service_rpc(
            "workbench_lookup_paired_voucher", {"p_code_hash": "\\x" + code_hash.hex()}
        ))
        result["provider_code_ciphertext"] = bytes.fromhex(result["provider_code_ciphertext"])
        return result

    def complete_paired_voucher(
        self, intent_id: str, face_value_micro_cny: int, provider_user_id: int
    ) -> dict[str, Any]:
        return self._rpc_result(self._service_rpc(
            "workbench_complete_paired_voucher",
            {"p_intent_id": intent_id, "p_face_value_micro_cny": face_value_micro_cny,
             "p_provider_user_id": provider_user_id},
        ))

    def begin_workbench_card_redemption(
        self, user_id: str, code_hash: bytes, code_ciphertext: bytes
    ) -> dict[str, Any]:
        identity = self._identity()
        if str(user_id) != identity["user_id"]:
            raise PermissionError("用户身份不匹配。")
        result = self._rpc_result(
            self._service_rpc(
                "workbench_begin_card_redemption",
                {
                    "p_user_id": user_id,
                    "p_code_hash": "\\x" + code_hash.hex(),
                    "p_code_ciphertext": "\\x" + code_ciphertext.hex(),
                },
            )
        )
        # The SQL RPC returns `intent_id`; keep the storage contract identical
        # to SQLite, whose callers use the canonical `id` field.
        if "id" not in result and result.get("intent_id"):
            result["id"] = result["intent_id"]
        return result

    def get_workbench_redemption_intent(self, intent_id: str, user_id: str) -> dict[str, Any] | None:
        if not self.service_role_key and self.backend_secret:
            row = self._rpc_result(self._service_rpc(
                "workbench_get_intent",
                {"p_intent_id": intent_id, "p_user_id": user_id},
            ))
            if not row:
                return None
            encoded = row.get("code_ciphertext")
            if isinstance(encoded, str):
                row["code_ciphertext"] = bytes.fromhex(encoded.removeprefix("\\x"))
            return row
        if not self.service_role_key:
            raise RuntimeError("云端积分账本未配置服务端密钥。")
        url = (
            f"{self.project_url}/rest/v1/workbench_card_redemptions"
            f"?select=id,user_id,code_ciphertext,status,face_value_micro_cny,safe_message,created_at"
            f"&id=eq.{urllib.parse.quote(intent_id)}&user_id=eq.{urllib.parse.quote(user_id)}&limit=1"
        )
        request = urllib.request.Request(
            url,
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Accept-Profile": "public",
            },
            method="GET",
        )
        try:
            with supabase_urlopen(request, timeout=15) as response:
                rows = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"兑换请求查询失败（HTTP {exc.code}）。") from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("无法查询云端兑换记录。") from exc
        if not rows:
            return None
        row = rows[0]
        encoded = row.get("code_ciphertext")
        if isinstance(encoded, str) and encoded.startswith("\\x"):
            row["code_ciphertext"] = bytes.fromhex(encoded[2:])
        return row

    def complete_workbench_card_redemption(
        self, intent_id: str, face_value_micro_cny: int, provider_user_id: int | None = None
    ) -> dict[str, Any]:
        return self._rpc_result(
            self._service_rpc(
                "workbench_complete_card_redemption",
                {
                    "p_intent_id": intent_id,
                    "p_face_value_micro_cny": int(face_value_micro_cny),
                    "p_provider_user_id": provider_user_id,
                },
            )
        )

    def set_workbench_card_redemption_status(
        self, intent_id: str, status: str, safe_message: str
    ) -> None:
        self._service_rpc(
            "workbench_set_card_redemption_status",
            {"p_intent_id": intent_id, "p_status": status, "p_safe_message": safe_message[:240]},
        )

    def reserve_workbench_usage(
        self, user_id: str, request_id: str, model: str, reserve_micro_cny: int,
        api_key_id: int | None = None,
    ) -> dict[str, Any]:
        identity = self._identity()
        if str(user_id) != identity["user_id"]:
            raise PermissionError("用户身份不匹配。")
        return self._rpc_result(
            self._service_rpc(
                "workbench_reserve_usage",
                {
                    "p_user_id": user_id,
                    "p_request_id": request_id,
                    "p_model": model,
                    "p_reserved_micro_cny": int(reserve_micro_cny),
                    "p_api_key_id": api_key_id,
                },
            )
        )

    def settle_workbench_usage(
        self, request_id: str, actual_micro_cny: int, provider_request_id: str = ""
    ) -> dict[str, Any]:
        return self._rpc_result(
            self._service_rpc(
                "workbench_settle_usage",
                {
                    "p_request_id": request_id,
                    "p_actual_micro_cny": int(actual_micro_cny),
                    "p_provider_request_id": provider_request_id or None,
                },
            )
        )

    def pending_workbench_usage(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        identity = self._identity()
        if str(user_id) != identity["user_id"]:
            raise PermissionError("用户身份不匹配。")
        return self._rest("workbench_usage_events", params=[
            ("select", "request_id,model,api_key_id"),
            ("user_id", f"eq.{user_id}"),
            ("status", "eq.reserved"),
            ("order", "created_at.asc"),
            ("limit", str(max(1, min(limit, 20)))),
        ])

    def refund_workbench_usage(self, request_id: str, reason: str = "provider_error") -> dict[str, Any]:
        return self._rpc_result(
            self._service_rpc(
                "workbench_refund_usage",
                {"p_request_id": request_id, "p_reason": reason[:120]},
            )
        )

    # ------------------------------------------------------------------
    # 异步生成任务 (Generation Jobs) 与版本保护代理
    # ------------------------------------------------------------------

    def create_generation_job(self, project_id: str, section_id: str, idempotency_key: str = "", base_version: str = "") -> dict[str, Any]:
        return self._job_store.create_generation_job(project_id, section_id, idempotency_key, base_version)

    def get_generation_job(self, job_id: str) -> dict[str, Any] | None:
        return self._job_store.get_generation_job(job_id)

    def find_job_by_idempotency_key(self, project_id: str, idempotency_key: str) -> dict[str, Any] | None:
        return self._job_store.find_job_by_idempotency_key(project_id, idempotency_key)

    def find_active_job(self, project_id: str, section_id: str) -> dict[str, Any] | None:
        return self._job_store.find_active_job(project_id, section_id)

    def update_generation_job(self, job_id: str, status: str, step: str | None = None, result: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any] | None:
        return self._job_store.update_generation_job(job_id, status, step, result, error)

    def cancel_generation_job(self, job_id: str) -> bool:
        return self._job_store.cancel_generation_job(job_id)

    def save_section_version(self, project_id: str, section_id: str, content: str, source: str = "user_edit", review_card: dict[str, Any] | None = None) -> dict[str, Any]:
        from .materials import enabled
        if os.environ.get("MATERIAL_PIPELINE_ENABLED", "").lower() == "true" and enabled(self.get_project(project_id) or {}):
            rows = self._rest("material_revisions", "POST", payload={
                "project_id": project_id, "section_id": section_id,
                "content": content, "source": source, "review_card": review_card,
            })
            return rows[0]
        return self._job_store.save_section_version(project_id, section_id, content, source, review_card)

    def list_section_versions(self, project_id: str, section_id: str, limit: int = 10) -> list[dict[str, Any]]:
        from .materials import enabled
        if os.environ.get("MATERIAL_PIPELINE_ENABLED", "").lower() == "true" and enabled(self.get_project(project_id) or {}):
            return self._rest("material_revisions", params={
                "project_id": f"eq.{project_id}", "section_id": f"eq.{section_id}",
                "order": "id.desc", "limit": str(max(1, min(limit, 100))),
            })
        return self._job_store.list_section_versions(project_id, section_id, limit)

    def get_section_version(self, version_id: str) -> dict[str, Any] | None:
        if os.environ.get("MATERIAL_PIPELINE_ENABLED", "").lower() == "true":
            if str(version_id).isdigit():
                rows = self._rest("material_revisions", params={"id": f"eq.{version_id}", "limit": "1"})
                return rows[0] if rows else None
        return self._job_store.get_section_version(version_id)
