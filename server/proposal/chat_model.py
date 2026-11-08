"""Adapt streaming and non-streaming transports to a shared model event stream."""
from __future__ import annotations

from typing import Any, Iterator

from .agent import ModelUnavailable


def model_events(agent: Any, project_id: str, payload: dict[str, Any], *, stream: bool) -> Iterator[dict[str, Any]]:
    """Preserve transport-owned billing and expose a single terminal response.

    A dropped consumer closes the upstream generator immediately; its own
    transport handles uncertain billing and releases its connection.
    """
    if not stream:
        response = agent._post("/api/chat", {**payload, "stream": False})
        agent._record_usage(project_id, "chat", response)
        yield {"type": "response", "message": response.get("message") or {}}
        return

    terminal = None
    upstream = agent._stream_post(payload)
    try:
        for event in upstream:
            if event["type"] == "delta":
                yield {"type": "delta", "text": event["text"]}
            elif event["type"] == "final":
                terminal = event
    finally:
        close = getattr(upstream, "close", None)
        if close:
            close()
    if not terminal:
        raise ModelUnavailable("模型未能产生有效输出。")
    if terminal.get("usage"):
        agent._record_usage(project_id, "chat", {"message": terminal["message"], "usage": terminal["usage"]})
    yield {"type": "response", "message": terminal["message"]}
