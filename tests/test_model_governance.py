# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch
import pytest
from server.proposal.agent import OllamaAgent, ModelUnavailable
from server.proposal.workflow import ContextBudgeter


def test_context_budgeter_allocation_bounds():
    budgeter = ContextBudgeter(max_context_chars=4000, extended_grounding=True)
    huge_bb = "x" * 5000
    huge_guidance = "y" * 6000
    huge_evidence = [{"text": "z" * 1000} for _ in range(10)]

    allocated = budgeter.allocate(huge_bb, huge_evidence, huge_guidance)
    assert len(allocated["blackboard"]) <= 1500
    assert len(allocated["evidence"]) <= 2600
    assert len(allocated["guidance"]) <= 3500
    evidence_json, notice = allocated["evidence"].split("\n", 1)
    assert json.loads(evidence_json)  # Complete JSON records, not a sliced JSON string.
    assert "其余来源未放入本轮上下文" in notice
    assert sum(map(len, allocated.values())) <= 4000


def test_agent_retry_on_transient_error(monkeypatch):
    attempts = []

    def mock_urlopen(request, timeout):
        attempts.append(1)
        if len(attempts) < 2:
            # 模拟第 1 次 503 临时故障
            raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, io.BytesIO(b"busy"))
        # 第 2 次重试成功
        return io.BytesIO(json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "重试成功输出"}}]
        }).encode())

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    agent = OllamaAgent(
        None, None,
        base_url="https://api.example.test/v1",
        model="test-model",
        provider="openai_compatible",
        api_key="sk-secret-1234",
    )
    res = agent._post("/api/chat", {"messages": [{"role": "user", "content": "hi"}]})
    assert res["message"]["content"] == "重试成功输出"
    assert len(attempts) == 2


def test_agent_exhausted_retries_does_not_leak_key(monkeypatch):
    def mock_failing_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_failing_urlopen)

    agent = OllamaAgent(
        None, None,
        base_url="https://api.example.test/v1",
        model="test-model",
        provider="openai_compatible",
        api_key="sk-secret-1234",
    )
    with pytest.raises(ModelUnavailable) as exc:
        agent._post("/api/chat", {"messages": []})

    err_msg = str(exc.value)
    assert "sk-secret-1234" not in err_msg
    assert "HTTP 401" in err_msg
