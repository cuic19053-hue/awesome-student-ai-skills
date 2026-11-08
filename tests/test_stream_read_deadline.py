"""A stalled later SSE read must not restart the whole serverless budget."""
import http.server
import json
import threading
import time

import pytest

from server.proposal.agent import ModelUnavailable, OllamaAgent
from server.proposal.storage import Store
from server.proposal.tools import ProposalTools


@pytest.mark.parametrize("finished", [False, True])
def test_later_stream_stall_obeys_remaining_time(tmp_path, monkeypatch, finished):
    monkeypatch.setenv("VERCEL", "1")
    calls = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(1)
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            time.sleep(0.2)
            payload = {"choices": [{"delta": {"content": "前半段"}, "finish_reason": "stop" if finished else None}]}
            self.wfile.write(("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode())
            self.wfile.flush()
            time.sleep(0.6)
        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        store = Store(tmp_path)
        agent = OllamaAgent(store, ProposalTools(store),
                            base_url=f"http://127.0.0.1:{server.server_port}",
                            model="test", provider="openai_compatible", api_key="test")
        agent._execution_deadline = time.monotonic() + 0.38
        start = time.monotonic()
        if finished:
            events = list(agent._stream_post({"messages": []}))
            assert events[-1]["message"]["content"] == "前半段"
        else:
            with pytest.raises(ModelUnavailable):
                list(agent._stream_post({"messages": []}))
        elapsed = time.monotonic() - start
        assert 0.25 <= elapsed < 0.65
        assert calls == [1]  # A timed-out inference is never replayed.
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_stream_trickling_without_newline_still_ends_at_deadline(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    calls = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(1)
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for _ in range(25):
                try:
                    self.wfile.write(b"x")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                time.sleep(0.04)
        def log_message(self, *_args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        store = Store(tmp_path)
        agent = OllamaAgent(store, ProposalTools(store), base_url=f"http://127.0.0.1:{server.server_port}",
                            model="test", provider="openai_compatible", api_key="test")
        agent._execution_deadline = time.monotonic() + 0.35
        start = time.monotonic()
        with pytest.raises(ModelUnavailable):
            list(agent._stream_post({"messages": []}))
        assert time.monotonic() - start < 0.65
        assert calls == [1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
