"""Translate the runtime's messages to the OpenAI Chat Completions contract.

This module only constructs request data. Transport, credentials, billing,
retry decisions and settlement remain the caller's responsibility.
"""
from __future__ import annotations

import json
import uuid
from typing import Any


def tool_call_id(value: Any = None) -> str:
    """Preserve provider IDs, generating one for providers that omit them."""
    return value or f"call_{uuid.uuid4().hex}"


def convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted_messages: list[dict[str, Any]] = []
    pending: list[dict[str, str]] = []
    for item in messages:
        role = item.get("role", "user")
        if role == "tool":
            call_id = item.get("tool_call_id")
            name = item.get("tool_name", "")
            if call_id:
                pending = [entry for entry in pending if entry["id"] != call_id]
            else:
                match = next((i for i, entry in enumerate(pending) if entry["name"] == name), None)
                if match is not None:
                    call_id = pending.pop(match)["id"]
                else:
                    call_id = name
            converted_messages.append({"role": "tool", "tool_call_id": call_id,
                                       "content": item.get("content", "")})
            continue
        converted: dict[str, Any] = {"role": role, "content": item.get("content") or ""}
        if role == "assistant" and item.get("tool_calls"):
            pending = []
            converted["tool_calls"] = []
            for call in item["tool_calls"]:
                fn = call.get("function", {})
                arguments = fn.get("arguments", "{}")
                ident = tool_call_id(call.get("id"))
                name = fn.get("name", "")
                converted["tool_calls"].append({"id": ident, "type": "function", "function": {
                    "name": name,
                    "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
                }})
                pending.append({"id": ident, "name": name})
        converted_messages.append(converted)
    return converted_messages


def build_request(payload: dict[str, Any], *, default_model: str, stream: bool,
                  platform_transport: bool, metered: bool) -> dict[str, Any]:
    """Build one provider request identically for streaming and normal runs."""
    model = str(payload.get("model") or default_model)
    body: dict[str, Any] = {"model": model, "messages": convert_messages(payload.get("messages", [])),
                            "stream": stream}
    if platform_transport and model == "deepseek-v4-flash":
        body["thinking"] = {"type": "disabled"}
    if payload.get("tools"):
        body["tools"] = payload["tools"]
        body["tool_choice"] = "auto"
    options = payload.get("options") or {}
    if "temperature" in options:
        body["temperature"] = options["temperature"]
    if "num_predict" in options:
        body["max_tokens"] = options["num_predict"]
    if platform_transport or (stream and metered):
        # Only the server's dedicated draft path can opt into the larger
        # budget. User text or an arbitrarily large num_predict never raises
        # the ordinary conversation limit.
        cap = 4096 if payload.get("response_profile") == "scholarship_draft" else 2048
        body["max_tokens"] = max(1, min(int(body.get("max_tokens") or cap), cap))
    # Existing streaming callers do not request structured responses.
    if not stream:
        if isinstance(payload.get("format"), dict):
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "structured_response", "strict": True, "schema": payload["format"],
            }}
        elif payload.get("format"):
            body["response_format"] = {"type": "json_object"}
    return body
