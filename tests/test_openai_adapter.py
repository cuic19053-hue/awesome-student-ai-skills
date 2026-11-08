"""Protocol-level tests independent of any model, network, or account."""
import copy
import json

import server.app  # Makes the proposal package importable.
from proposal.openai_adapter import build_request, convert_messages


def test_missing_ids_still_match_two_same_name_tool_results():
    messages = [
        {"role": "assistant", "tool_calls": [
            {"function": {"name": "lookup", "arguments": {"q": "一"}}},
            {"function": {"name": "lookup", "arguments": {"q": "二"}}},
        ]},
        {"role": "tool", "tool_name": "lookup", "content": "first"},
        {"role": "tool", "tool_name": "lookup", "content": "second"},
    ]
    original = copy.deepcopy(messages)
    result = convert_messages(messages)
    ids = [item["id"] for item in result[0]["tool_calls"]]
    assert len(set(ids)) == 2
    assert [item["tool_call_id"] for item in result[1:]] == ids
    assert json.loads(result[0]["tool_calls"][0]["function"]["arguments"]) == {"q": "一"}
    assert messages == original


def test_explicit_ids_and_out_of_order_results_are_preserved():
    messages = [
        {"role": "assistant", "tool_calls": [
            {"id": "one", "function": {"name": "lookup", "arguments": "{}"}},
            {"id": "two", "function": {"name": "lookup", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "two", "tool_name": "lookup", "content": "second"},
        {"role": "tool", "tool_name": "lookup", "content": "first"},
    ]
    result = convert_messages(messages)
    assert [item["tool_call_id"] for item in result[1:]] == ["two", "one"]


def test_streaming_and_nonstreaming_share_platform_request_options():
    payload = {"messages": [{"role": "user", "content": "开始"}],
               "tools": [{"type": "function", "function": {"name": "lookup"}}],
               "options": {"temperature": 0.2, "num_predict": 4096}}
    kwargs = {"default_model": "deepseek-v4-flash", "platform_transport": True, "metered": False}
    ordinary = build_request(payload, stream=False, **kwargs)
    streamed = build_request(payload, stream=True, **kwargs)
    assert {**ordinary, "stream": True} == streamed
    assert ordinary["max_tokens"] == 2048
    assert ordinary["thinking"] == {"type": "disabled"}
    assert ordinary["tool_choice"] == "auto"
