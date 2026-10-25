# -*- coding: utf-8 -*-
"""
Generation Job Runner & Task State Machine
==========================================

长文档章节异步生成任务系统：
  1. 状态机流转：pending -> running(drafting/reviewing/revising) -> completed/failed/cancelled
  2. 幂等与并发防重：支持 idempotency_key，同一章节活跃任务互斥拦截
  3. 版本保护 (Optimistic Concurrency)：生成完成若检测到用户手动修改，保留用户编辑并存为备选版本
  4. 支持任务查询与优雅取消
"""

from __future__ import annotations

import hashlib
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from threading import Lock
from typing import Any, Callable, Dict, Optional

from . import observability as obs

logger = logging.getLogger("proposal_agent.jobs")


def content_hash(text: str) -> str:
    """计算章节文本的稳定指纹。"""
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()[:16]


class GenerationJobRunner:
    """章节异步任务调度与状态机执行器。"""

    def __init__(self, store: Any, max_workers: int = 4) -> None:
        self.store = store
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="gen-job-")
        self._active_futures: Dict[str, Future[Any]] = {}
        self._submit_lock = Lock()

    def submit_job(
        self,
        project_id: str,
        section_id: str,
        invoke_fn: Callable[[], Dict[str, Any]],
        idempotency_key: str = "",
        current_section_content: str = "",
    ) -> dict[str, Any]:
        """幂等提交生成任务；若已存在相同 key 或活跃任务，则直接返回。"""
        with self._submit_lock:
            return self._submit_job(project_id, section_id, invoke_fn, idempotency_key, current_section_content)

    def _submit_job(self, project_id, section_id, invoke_fn, idempotency_key, current_section_content):
        # Legacy, single-process runner. Durable pilot uses MaterialJobs instead.
        if idempotency_key:
            existing = self.store.find_job_by_idempotency_key(project_id, idempotency_key)
            if existing:
                return existing

        # 2. 活跃任务互斥检查（同一章节不能并发重复生成，防重复扣费）
        active = self.store.find_active_job(project_id, section_id)
        if active:
            return active

        # 3. 创建持久化任务
        base_ver = content_hash(current_section_content)
        job = self.store.create_generation_job(
            project_id=project_id,
            section_id=section_id,
            idempotency_key=idempotency_key,
            base_version=base_ver,
        )
        job_id = job["id"]
        state = obs.context.get() or {}
        obs.bind(trace_id=obs.correlated("job", state.get("owner_id") or "local", job_id), job_id=job_id)
        obs.emit("task.submitted", stage="queued", status="accepted", job_id=job_id)

        # 4. 派发至后台线程池
        future = self.executor.submit(
            copy_context().run,
            self._execute_job,
            job_id=job_id,
            project_id=project_id,
            section_id=section_id,
            base_version=base_ver,
            invoke_fn=invoke_fn,
        )
        self._active_futures[job_id] = future
        return job

    def cancel_job(self, job_id: str) -> bool:
        """取消指定的生成任务。"""
        cancelled = self.store.cancel_generation_job(job_id)
        future = self._active_futures.get(job_id)
        if future and not future.done():
            future.cancel()
        return cancelled

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """查询任务最新状态与结果。"""
        return self.store.get_generation_job(job_id)

    # ------------------------------------------------------------------
    # 内部执行与状态流转
    # ------------------------------------------------------------------

    def _execute_job(self, job_id, project_id, section_id, base_version, invoke_fn):
        with obs.background_scope(job_id, project_id):
            obs.emit("task.execution", stage="invoke", status="started", job_id=job_id)
            self._execute_job_inner(job_id, project_id, section_id, base_version, invoke_fn)
            try:
                result = self.store.get_generation_job(job_id) or {}
                failed = result.get("status") == "failed"
                obs.emit("task.execution", stage="result_saved", job_id=job_id,
                         status="failed" if failed else "cancelled" if result.get("status") == "cancelled" else "completed",
                         level="error" if failed else "info", code="TASK_EXECUTION_FAILED" if failed else None)
            except Exception:
                obs.emit("task.observation", stage="result_saved", status="pending",
                         level="warning", job_id=job_id, code="TASK_OBSERVATION_UNAVAILABLE")

    def _execute_job_inner(
        self,
        job_id: str,
        project_id: str,
        section_id: str,
        base_version: str,
        invoke_fn: Callable[[], Dict[str, Any]],
    ) -> None:
        try:
            # 状态转移：running -> drafting
            job = self.store.get_generation_job(job_id)
            if not job or job.get("status") == "cancelled":
                return

            updated = self.store.update_generation_job(job_id, status="running", step="drafting")
            if not updated or updated.get("status") == "cancelled":
                return

            # 核心调用（执行 Agentic 生成工作流）
            result = invoke_fn()

            # 再次检查是否已被中途取消
            job_after = self.store.get_generation_job(job_id)
            if not job_after or job_after.get("status") == "cancelled":
                return

            generated_content = result.get("content", "")
            review_card = result.get("review_card")

            # 版本保护 (Optimistic Concurrency Control)
            # 获取当前章节最新正文，比对指纹
            project = self.store.get_project(project_id)
            current_now = (project.get("sections") or {}).get(section_id, "") if project else ""
            current_ver_now = content_hash(current_now)

            if current_ver_now != base_version:
                # 用户在后台生成期间手动编辑了输入框！绝不强行静默覆盖！
                saved_ver = self.store.save_section_version(
                    project_id=project_id,
                    section_id=section_id,
                    content=generated_content,
                    source="ai_generated_alternative",
                    review_card=review_card,
                )
                result["conflict_status"] = "user_edit_preserved"
                result["alternative_version_id"] = saved_ver["id"]
                result["notice"] = (
                    "检测到您在生成期间手动编辑了该章节，AI 生成的最新版本已安全存入版本历史，未覆盖您的当前编辑。"
                )
            else:
                # 正常覆盖更新并记录版本
                if project:
                    sections = dict(project.get("sections") or {})
                    sections[section_id] = generated_content
                    self.store.update_project(project_id, sections=sections)
                self.store.save_section_version(
                    project_id=project_id,
                    section_id=section_id,
                    content=generated_content,
                    source="ai_generated",
                    review_card=review_card,
                )

            # 状态转移：completed -> finished
            self.store.update_generation_job(
                job_id=job_id,
                status="completed",
                step="finished",
                result=result,
            )

        except Exception as exc:
            logger.exception("Generation job %s failed: %s", job_id, exc)
            self.store.update_generation_job(
                job_id=job_id,
                status="failed",
                step="error",
                error=str(exc),
            )
        finally:
            self._active_futures.pop(job_id, None)
