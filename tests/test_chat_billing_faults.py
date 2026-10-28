"""Fault injection for the real paid model transport, never a live provider."""
import io
import json
import threading
import time
import urllib.error

import pytest
import server.app  # Registers proposal module path.
from proposal.agent import ModelUnavailable, OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.storage import Store
from proposal.tools import ProposalTools
from proposal.workbench_metering import WorkbenchMeter


def setup_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("BILLING_BACKGROUND_RECONCILIATION", "true")
    store = Store(tmp_path)
    store.grant_workbench_payment_credits("alice", "fault-test-payment", 1_000_000)
    meter = WorkbenchMeter(store, "alice", 692)
    meter.usage.find = lambda *_: (10000, "receipt-test")
    agent = OllamaAgent(
        store, ProposalTools(store, ProjectRetriever(store)),
        provider="openai_compatible", model="deepseek-v4-flash",
        base_url="https://api.wopally.cn/v1", api_key="test-only-key",
        meter=meter, platform_transport=True,
    )
    monkeypatch.setattr("proposal.agent.time.sleep", lambda *_: None)
    return store, meter, agent


def frame(content="", finish_reason=None):
    return ("data: " + json.dumps({"choices": [{
        "delta": {"content": content}, "finish_reason": finish_reason,
    }]}) + "\n\n").encode()


@pytest.mark.parametrize("stream", [False, True])
def test_completed_answer_survives_ledger_outage(tmp_path, monkeypatch, stream):
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    body = frame("已完成", "stop") + b"data: [DONE]\n\n" if stream else json.dumps({
        "choices": [{"message": {"content": "已完成"}}],
    }).encode()
    calls = []
    monkeypatch.setattr("proposal.agent.wopally_urlopen",
                        lambda *_args, **_kw: calls.append(1) or io.BytesIO(body))
    monkeypatch.setattr(store, "settle_workbench_usage",
                        lambda *_: (_ for _ in ()).throw(RuntimeError("ledger timeout")))
    if stream:
        assert list(agent._stream_post({"messages": []}))[-1]["message"]["content"] == "已完成"
    else:
        assert agent._post("/api/chat", {"messages": []})["message"]["content"] == "已完成"
    assert calls == [1]
    assert len(store.pending_workbench_usage("alice")) == 1
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 800000


@pytest.mark.parametrize("stream", [False, True])
def test_uncertain_timeout_never_replays_paid_inference(tmp_path, monkeypatch, stream):
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    calls = []

    def timeout(*_args, **_kwargs):
        calls.append(1)
        raise TimeoutError("inference might already have started")

    monkeypatch.setattr("proposal.agent.wopally_urlopen", timeout)
    with pytest.raises(ModelUnavailable):
        if stream:
            list(agent._stream_post({"messages": []}))
        else:
            agent._post("/api/chat", {"messages": []})
    assert calls == [1]
    assert len(store.pending_workbench_usage("alice")) == 1
    assert not any(t["kind"] == "usage_refund" for t in store.get_workbench_credit_transactions("alice"))


def test_partial_stream_disconnect_does_not_replay_or_refund(tmp_path, monkeypatch):
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    calls = []

    class BrokenStream:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def __iter__(self):
            yield frame("半条")
            raise urllib.error.URLError("disconnected")

    monkeypatch.setattr("proposal.agent.wopally_urlopen",
                        lambda *_args, **_kw: calls.append(1) or BrokenStream())
    events = []
    with pytest.raises(ModelUnavailable):
        for event in agent._stream_post({"messages": []}):
            events.append(event)
    assert [e["text"] for e in events if e["type"] == "delta"] == ["半条"]
    assert calls == [1]
    assert len(store.pending_workbench_usage("alice")) == 1


def test_premature_eof_is_not_a_successful_response(tmp_path, monkeypatch):
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    monkeypatch.setattr("proposal.agent.wopally_urlopen",
                        lambda *_args, **_kw: io.BytesIO(frame("未完成的半条回答")))
    with pytest.raises(ModelUnavailable, match="中断|未完成"):
        list(agent._stream_post({"messages": []}))
    assert len(store.pending_workbench_usage("alice")) == 1
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 800000


def test_blank_completed_stream_is_rejected_like_nonstream(tmp_path, monkeypatch):
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    monkeypatch.setattr("proposal.agent.wopally_urlopen",
                        lambda *_args, **_kw: io.BytesIO(b"data: [DONE]\n\n"))
    with pytest.raises(ModelUnavailable, match="未返回可用正文"):
        list(agent._stream_post({"messages": []}))
    assert store.pending_workbench_usage("alice") == []


def test_closing_generator_preserves_uncertain_hold_and_releases_connection(tmp_path, monkeypatch):
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    response = io.BytesIO(frame("第一段") + frame("下一段", "stop"))
    monkeypatch.setattr("proposal.agent.wopally_urlopen", lambda *_args, **_kw: response)
    stream = agent._stream_post({"messages": []})
    assert next(stream)["text"] == "第一段"
    stream.close()
    assert response.closed
    assert len(store.pending_workbench_usage("alice")) == 1
    # Another request is not locked out solely by this uncertain receipt.
    store.reserve_workbench_usage("alice", "next-request-after-close", "deepseek-v4-flash", 200000, 692)


def test_finish_reason_without_done_is_still_a_complete_compatible_stream(tmp_path, monkeypatch):
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    monkeypatch.setattr("proposal.agent.wopally_urlopen",
                        lambda *_args, **_kw: io.BytesIO(frame("完成", "stop")))
    assert list(agent._stream_post({"messages": []}))[-1]["message"]["content"] == "完成"
    assert store.pending_workbench_usage("alice") == []


def test_refund_ledger_keeps_request_reference_and_model(tmp_path, monkeypatch):
    store, meter, _agent = setup_agent(tmp_path, monkeypatch)
    request_id = meter.reserve("deepseek-v4-flash")
    meter.refund(request_id)
    refunds = [t for t in store.get_workbench_credit_transactions("alice") if t["kind"] == "usage_refund"]
    assert len(refunds) == 1
    assert refunds[0]["reference_id"] == request_id
    assert refunds[0]["model"] == "deepseek-v4-flash"


@pytest.mark.parametrize("stream", [False, True])
def test_gateway_503_does_not_replay_or_assume_free(tmp_path, monkeypatch, stream):
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    calls = []

    def failed(*_args, **_kwargs):
        calls.append(1)
        raise urllib.error.HTTPError("https://api.wopally.cn/v1/chat/completions",
                                     503, "upstream uncertain", {}, io.BytesIO(b"private detail"))

    monkeypatch.setattr("proposal.agent.wopally_urlopen", failed)
    with pytest.raises(ModelUnavailable) as exc:
        if stream:
            list(agent._stream_post({"messages": []}))
        else:
            agent._post("/api/chat", {"messages": []})
    assert "private detail" not in str(exc.value)
    assert calls == [1]
    assert len(store.pending_workbench_usage("alice")) == 1


def test_commit_then_timeout_keeps_answer_without_double_refund(tmp_path, monkeypatch):
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    original = store.settle_workbench_usage

    def commit_then_timeout(*args):
        original(*args)
        raise RuntimeError("response lost after commit")

    monkeypatch.setattr(store, "settle_workbench_usage", commit_then_timeout)
    monkeypatch.setattr("proposal.agent.wopally_urlopen", lambda *_args, **_kw: io.BytesIO(
        b'{"choices":[{"message":{"content":"complete answer"}}]}'))
    assert agent._post("/api/chat", {"messages": []})["message"]["content"] == "complete answer"
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 990000
    assert store.pending_workbench_usage("alice") == []
    assert not any(t["kind"] == "usage_refund" for t in store.get_workbench_credit_transactions("alice"))


def test_malformed_stream_does_not_silently_claim_completion(tmp_path, monkeypatch):
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    monkeypatch.setattr("proposal.agent.wopally_urlopen",
                        lambda *_args, **_kw: io.BytesIO(frame("partial") + b"data: not-json\n\n"))
    with pytest.raises(ModelUnavailable, match="格式异常"):
        list(agent._stream_post({"messages": []}))
    assert len(store.pending_workbench_usage("alice")) == 1


def test_service_login_lock_wait_is_bounded(monkeypatch):
    import proposal.wopally_auth as auth
    lock = threading.Lock()
    lock.acquire()
    monkeypatch.setattr(auth, "_lock", lock)
    monkeypatch.setattr(auth, "_cached_token", "")
    monkeypatch.setenv("WOPALLY_SERVICE_EMAIL", "test@example.test")
    monkeypatch.setenv("WOPALLY_SERVICE_PASSWORD", "test-only")
    try:
        started = time.monotonic()
        with pytest.raises(auth.ServiceLoginUnavailable, match="繁忙"):
            auth.service_token("https://api.wopally.cn", timeout=0.02)
        assert time.monotonic() - started < 0.5
        assert lock.locked()  # Never release another caller's lock.
    finally:
        lock.release()


@pytest.mark.parametrize("message", ["prior model charge pending review", "unrelated object state"])
def test_only_the_known_old_lock_error_is_described_as_pending(tmp_path, monkeypatch, message):
    from proposal.storage import PendingUsageError
    from proposal.supabase_store import SupabaseStore
    store = SupabaseStore("https://example.supabase.co", "test", data_dir=tmp_path,
                          service_role_key="server-test-only")

    def failure(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 500, "failed", {},
                                     io.BytesIO(json.dumps({"code": "55000", "message": message}).encode()))

    monkeypatch.setattr("proposal.supabase_store.supabase_urlopen", failure)
    expected = PendingUsageError if message == "prior model charge pending review" else RuntimeError
    with pytest.raises(expected):
        store._service_rpc("workbench_reserve_usage", {})


@pytest.mark.parametrize("usage", ["malformed", {"prompt_tokens": "123", "completion_tokens": None}, None])
def test_bad_informational_token_stats_do_not_drop_a_good_answer(tmp_path, monkeypatch, usage):
    _store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    body = json.dumps({"choices": [{"message": {"content": "complete answer"}}], "usage": usage}).encode()
    monkeypatch.setattr("proposal.agent.wopally_urlopen", lambda *_args, **_kw: io.BytesIO(body))
    result = agent._post("/api/chat", {"messages": []})
    assert result["message"]["content"] == "complete answer"
    assert type(result["usage"]["prompt_tokens"]) is int


def test_empty_keepalive_frames_are_not_treated_as_corrupt_model_output(tmp_path, monkeypatch):
    _store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    response = b": keepalive\n\ndata: \n\n" + frame("complete", "stop") + b"data: [DONE]\n\n"
    monkeypatch.setattr("proposal.agent.wopally_urlopen", lambda *_args, **_kw: io.BytesIO(response))
    assert list(agent._stream_post({"messages": []}))[-1]["message"]["content"] == "complete"


def test_broken_trailing_metadata_does_not_erase_declared_complete_text(tmp_path, monkeypatch):
    _store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    response = frame("complete", "stop") + b"data: malformed-usage\n\n"
    monkeypatch.setattr("proposal.agent.wopally_urlopen", lambda *_args, **_kw: io.BytesIO(response))
    assert list(agent._stream_post({"messages": []}))[-1]["message"]["content"] == "complete"


@pytest.mark.parametrize("stream", [False, True])
def test_expired_cloud_budget_never_creates_another_paid_reservation(tmp_path, monkeypatch, stream):
    monkeypatch.setenv("VERCEL", "1")
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    agent._execution_deadline = time.monotonic() - 1
    with pytest.raises(ModelUnavailable, match="时间已用完"):
        if stream:
            list(agent._stream_post({"messages": []}))
        else:
            agent._post("/api/chat", {"messages": []})
    assert store.pending_workbench_usage("alice") == []
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 1000000


def test_cloud_transport_timeout_is_shorter_than_serverless_hard_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    _store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    timeouts = []

    def upstream(_request, timeout):
        timeouts.append(timeout)
        return io.BytesIO(frame("complete", "stop"))

    monkeypatch.setattr("proposal.agent.wopally_urlopen", upstream)
    assert list(agent._stream_post({"messages": []}))[-1]["message"]["content"] == "complete"
    assert 0 < timeouts[0] <= 45


@pytest.mark.parametrize("stream", [False, True])
def test_budget_expiring_during_reserve_releases_never_sent_request(tmp_path, monkeypatch, stream):
    monkeypatch.setenv("VERCEL", "1")
    store, _meter, agent = setup_agent(tmp_path, monkeypatch)
    original = store.reserve_workbench_usage

    def slow_reserve(*args):
        result = original(*args)
        agent._execution_deadline = time.monotonic() - 1
        return result

    monkeypatch.setattr(store, "reserve_workbench_usage", slow_reserve)
    monkeypatch.setattr("proposal.agent.wopally_urlopen",
                        lambda *_args, **_kw: pytest.fail("expired request must not reach upstream"))
    with pytest.raises(ModelUnavailable, match="时间已用完"):
        if stream:
            list(agent._stream_post({"messages": []}))
        else:
            agent._post("/api/chat", {"messages": []})
    assert store.pending_workbench_usage("alice") == []
    assert store.get_workbench_credit_balance("alice")["balance_micro_cny"] == 1000000


def test_inline_cloud_settlement_uses_short_timeout(tmp_path, monkeypatch):
    from proposal.supabase_store import SupabaseStore
    monkeypatch.setenv("BILLING_BACKGROUND_RECONCILIATION", "true")
    store = SupabaseStore("https://example.supabase.co", "test", data_dir=tmp_path,
                          service_role_key="server-test-only")
    timeouts = []

    def open_request(_request, timeout):
        timeouts.append(timeout)
        return io.BytesIO(b'{"status":"settled"}')

    monkeypatch.setattr("proposal.supabase_store.supabase_urlopen", open_request)
    store.settle_workbench_usage("request-12345", 100, "receipt")
    assert timeouts == [2]


@pytest.mark.parametrize(("status", "held"), [(503, True), (401, False)])
def test_image_gateway_errors_distinguish_uncertain_outcome_from_rejection(tmp_path, monkeypatch, status, held):
    from proposal.workbench_images import generate_image_deferred
    store, meter, _agent = setup_agent(tmp_path, monkeypatch)
    store.grant_workbench_payment_credits("alice", "image-test-payment", 5000000)
    monkeypatch.setenv("WOPALLY_MODEL_BASE_URL", "https://api.wopally.cn/v1")
    monkeypatch.setenv("WOPALLY_WORKBENCH_API_KEY", "test-only")
    def failure(request, **_kwargs):
        raise urllib.error.HTTPError(request.full_url, status, "failed", {}, io.BytesIO(b""))
    monkeypatch.setattr("proposal.workbench_images.wopally_urlopen", failure)
    with pytest.raises(ModelUnavailable):
        generate_image_deferred("test only", meter)
    assert bool(store.pending_workbench_usage("alice")) is held


def test_long_sse_reply_does_not_query_wallet_per_delta(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import server.app as app
    store = Store(tmp_path)
    store.grant_workbench_payment_credits("alice", "stream-test-payment", 1_000_000)
    project = store.create_project(title="stream test")
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "_current_user_id", lambda _: "alice")
    reads = []
    original = store.get_workbench_credit_balance
    monkeypatch.setattr(store, "get_workbench_credit_balance",
                        lambda user: reads.append(user) or original(user))

    class StreamingAgent:
        def chat_stream(self, *_):
            for _ in range(25):
                yield {"type": "delta", "text": "文字"}
            yield {"type": "done", "message": "文字" * 25, "tool_calls": []}

    monkeypatch.setattr(app, "_agent_for_config", lambda *_args, **_kw: StreamingAgent())
    response = TestClient(app.app).post(f"/api/projects/{project['id']}/chat?stream=true",
        json={"message": "请继续", "stream": True, "llm_config": {"provider": "preset"}})
    assert response.status_code == 200 and "event: done" in response.text
    assert response.text.count("event: delta") == 25
    assert reads == ["alice"]
