"""Request-local time budgets for synchronous, read-only chat tools."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import socket
import threading
import time
from typing import Any, Iterator


class ExecutionBudgetExceeded(TimeoutError):
    pass


_deadline: ContextVar[float | None] = ContextVar("chat_tool_deadline", default=None)


@contextmanager
def execution_budget(deadline: float | None) -> Iterator[None]:
    token = _deadline.set(deadline)
    try:
        remaining_timeout(1)
        yield
    finally:
        _deadline.reset(token)


def remaining_timeout(requested: float) -> float:
    deadline = _deadline.get()
    if deadline is None:
        return requested
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ExecutionBudgetExceeded("本轮处理时间已用完，工具未继续执行。请先查看已有结果。")
    return min(requested, remaining)


def read_response(response: Any, limit: int | None = None) -> bytes:
    """Interrupt urllib's response socket even if it keeps trickling bytes."""
    timeout = remaining_timeout(12)
    deadline = _deadline.get()
    sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
    timer = None
    if deadline is not None and sock is not None:
        sock.settimeout(timeout)

        def interrupt() -> None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        timer = threading.Timer(max(0, deadline - time.monotonic()), interrupt)
        timer.daemon = True
        timer.start()
    try:
        body = response.read(limit) if limit is not None else response.read()
        remaining_timeout(1)
        return body
    finally:
        if timer is not None:
            timer.cancel()
