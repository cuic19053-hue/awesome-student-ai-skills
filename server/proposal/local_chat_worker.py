"""Explicit local-only, at-most-once chat worker prototype.

This is not an HTTP service and is not a durable worker: message input and
model credentials stay in memory. A process restart cannot resume a pending
turn. Once claimed, an interrupted/expired turn requires review and must not
be automatically replayed. Cloud stores and production deployment are not
supported by this module.
"""
from __future__ import annotations

import hashlib
import json
import threading
import urllib.parse
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from .chat_runtime import ChatRuntime
from .storage import Store


class LeaseUnavailable(RuntimeError):
    """The current worker no longer has a valid turn lease."""


class _LeasedTools:
    def __init__(self, tools: Any, validate: Callable[[], None]):
        self._tools = tools
        self._validate = validate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._tools, name)

    def invoke(self, name: str, arguments: dict[str, Any]) -> Any:
        self._validate()
        return self._tools.invoke(name, arguments)


class _LeasedStore:
    def __init__(self, store: Store, validate: Callable[[], None]):
        self._store = store
        self._validate = validate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)

    def add_message(self, project_id: str, role: str, content: str) -> None:
        self._validate()
        self._store.add_message(project_id, role, content)


class _LeasedAgent:
    """Check lease before each additional model call and tool invocation."""
    def __init__(self, agent: Any, validate: Callable[[], None]):
        self._agent = agent
        self._validate = validate
        self.tools = _LeasedTools(agent.tools, validate)
        self.store = _LeasedStore(agent.store, validate)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)

    def _post(self, *args: Any, **kwargs: Any) -> Any:
        self._validate()
        return self._agent._post(*args, **kwargs)


def _fingerprint(project_id: str, message: str, agent: Any) -> str:
    # Hash the entire request/config in one digest; neither input nor API key
    # is saved in the turns table or emitted as a log message.
    request = {
        "project_id": project_id,
        "message": message,
        "provider": getattr(agent, "provider", ""),
        "model": getattr(agent, "model", ""),
        "base_url": getattr(agent, "base_url", ""),
        "api_key": getattr(agent, "api_key", ""),
        "platform_transport": bool(getattr(agent, "platform_transport", False)),
    }
    encoded = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class LocalChatWorker:
    """Run local chat turns asynchronously, never replaying a claimed turn.

    The caller must provide a fresh agent bound to the same local Store for
    each submission. The queue supplies atomic idempotency and lease checks.
    This worker does not renew leases, recover input after restart, or stop a
    model request already in flight when a lease expires.
    """

    def __init__(self, store: Store, turns: Any, agent_factory: Callable[[], Any], *,
                 max_workers: int = 2, lease_seconds: int = 120):
        if not isinstance(store, Store) or hasattr(store, "_rest"):
            raise ValueError("LocalChatWorker only accepts a local Store")
        if not callable(getattr(turns, "is_lease_valid", None)):
            raise ValueError("The turn store must support lease validation")
        if not callable(getattr(turns, "abandon_pending", None)):
            raise ValueError("The turn store must support abandoning unstarted turns")
        if getattr(turns, "db_path", None) == store.db_path:
            raise ValueError("Turn ledger must use a separate database")
        if not 1 <= max_workers <= 8:
            raise ValueError("max_workers out of bounds")
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds out of bounds")
        self.store = store
        self.turns = turns
        self.agent_factory = agent_factory
        self.lease_seconds = lease_seconds
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="local-chat")
        self._lock = threading.RLock()
        self._futures: set[Future[Any]] = set()
        self._closed = False

    def submit(self, project_id: str, idempotency_key: str, message: str) -> dict[str, Any]:
        """Submit once and return the current public status; never auto-retry."""
        if not isinstance(message, str) or not message.strip() or len(message) > 12000:
            raise ValueError("消息不能为空且不得超过 12000 字符")
        if not self.store.get_project(project_id):
            raise ValueError("找不到这个项目")
        # A factory must not use any active request context or shared cloud store.
        agent = self.agent_factory()
        if getattr(agent, "store", None) is not self.store:
            raise ValueError("Agent must use the worker's local Store")
        parsed = urllib.parse.urlsplit(str(getattr(agent, "base_url", "")))
        if (getattr(agent, "provider", "") != "ollama"
                or getattr(agent, "meter", None) is not None
                or getattr(agent, "platform_transport", False)
                or parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("LocalChatWorker only supports an unmetered local Ollama agent")
        owner = "local_user"
        with self._lock:
            if self._closed:
                raise RuntimeError("Worker is closed")
            self.turns.expire()
            turn, created = self.turns.submit(owner, project_id, idempotency_key,
                                               _fingerprint(project_id, message, agent))
            # A pending record contains no input. The caller has just supplied
            # the original input again and the ledger verified its digest, so
            # it is safe to claim that known-unstarted record. Running and all
            # terminal states must never be replayed.
            if not created and turn["status"] != "pending":
                return turn
            turn_id = turn["id"]
            lease = self.turns.claim(owner, project_id, turn_id, lease_seconds=self.lease_seconds)
            if lease is not None:
                try:
                    future = self._executor.submit(self._run, owner, project_id, turn_id, lease, message, agent)
                except Exception:
                    self.turns.fail(owner, project_id, turn_id, lease, uncertain=False)
                    raise
                self._futures.add(future)
                future.add_done_callback(self._forget)
            else:
                # No durable input is stored. Never leave a request looking
                # queued when another turn owns the project's only lease.
                self.turns.abandon_pending(owner, project_id, turn_id)
            return self.turns.get(owner, project_id, turn_id) or turn

    def _forget(self, future: Future[Any]) -> None:
        with self._lock:
            self._futures.discard(future)

    def _run(self, owner: str, project_id: str, turn_id: str, lease: str, message: str, agent: Any) -> None:
        def validate() -> None:
            if not self.turns.is_lease_valid(owner, project_id, turn_id, lease):
                raise LeaseUnavailable("turn lease expired")

        try:
            validate()
            guarded = _LeasedAgent(agent, validate)
            answer = None
            for event in ChatRuntime(guarded).run(project_id, message, stream=False):
                if event.get("type") == "done":
                    answer = event.get("message")
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("chat produced no final answer")
            self.turns.complete(owner, project_id, turn_id, lease, answer)
        except Exception:
            # Once execution began, even a transport failure can mean the
            # provider billed or a tool wrote data. Never persist raw errors or
            # mark the turn safely replayable.
            try:
                self.turns.fail(owner, project_id, turn_id, lease, uncertain=True)
            except Exception:
                pass  # Expiry reconciler owns the status after lost lease.

    def get(self, project_id: str, turn_id: str) -> dict[str, Any] | None:
        self.turns.expire()
        return self.turns.get("local_user", project_id, turn_id)

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=wait)
