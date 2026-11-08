"""Explicitly enabled, local-only API for the experimental chat worker.

This is intentionally separate from the public chat endpoint: it cannot use
cloud storage, platform billing, remote providers, or claim restart recovery.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .chat_turns import ChatTurns, IdempotencyConflict
from .local_chat_worker import LocalChatWorker
from .storage import Store


class LocalChatTurnInput(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    idempotency_key: str = Field(min_length=1, max_length=160)


class LocalChatAPI:
    """One local worker per app instance; caller owns shutdown."""

    def __init__(self, get_store: Callable[[], Any], get_agent: Callable[[], Any],
                 is_cloud: Callable[[], bool]):
        self.get_store = get_store
        self.get_agent = get_agent
        self.is_cloud = is_cloud
        self.lock = threading.Lock()
        self.worker: LocalChatWorker | None = None

    def get_worker(self) -> LocalChatWorker:
        if self.is_cloud() or os.environ.get("LOCAL_CHAT_WORKER_ENABLED", "").lower() != "true":
            raise HTTPException(status_code=404, detail="本地实验功能未启用。")
        store = self.get_store()
        if not isinstance(store, Store) or hasattr(store, "_rest"):
            raise HTTPException(status_code=404, detail="本地实验功能未启用。")
        with self.lock:
            if self.worker is None or self.worker.store is not store:
                if self.worker is not None:
                    self.worker.shutdown(wait=False)
                turns = ChatTurns(store.data_dir / "local-chat-turns.sqlite3")
                self.worker = LocalChatWorker(store, turns, self.get_agent)
            return self.worker

    def close(self) -> None:
        with self.lock:
            worker, self.worker = self.worker, None
        if worker:
            worker.shutdown(wait=False)


def register_local_chat_api(app: FastAPI, service: LocalChatAPI) -> None:
    @app.post("/api/experimental/local-chat/{project_id}/turns")
    def submit_local_turn(project_id: str, payload: LocalChatTurnInput) -> dict[str, Any]:
        worker = service.get_worker()
        project = worker.store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在。")
        if project.get("state", {}).get("skill_id") == "":
            raise HTTPException(status_code=409, detail="请先为对话选择申报类型。")
        try:
            return worker.submit(project_id, payload.idempotency_key, payload.message)
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/experimental/local-chat/{project_id}/turns/{turn_id}")
    def get_local_turn(project_id: str, turn_id: str) -> dict[str, Any]:
        worker = service.get_worker()
        if not worker.store.get_project(project_id):
            raise HTTPException(status_code=404, detail="项目不存在。")
        turn = worker.get(project_id, turn_id)
        if not turn:
            raise HTTPException(status_code=404, detail="任务不存在。")
        return turn
