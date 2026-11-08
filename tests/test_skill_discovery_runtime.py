"""Skill discovery and on-demand loading through the real chat loop."""
from __future__ import annotations

import copy
import json

import pytest

import server.app  # Registers the server module path.
from proposal.agent import OllamaAgent
from proposal.retrieval import ProjectRetriever
from proposal.skills import invoke_discovery_tool, model_safe_guidance, registry
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.mark.parametrize("stream", [False, True])
def test_chat_discovers_and_loads_selected_skill_without_mutation(tmp_path, monkeypatch, stream):
    store = Store(tmp_path)
    project = store.create_project(title="技能测试")
    store.update_project(project["id"], state={"skill_id": "national-scholarship"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    responses = iter([
        {"role": "assistant", "tool_calls": [{"id": "catalog", "function": {
            "name": "list_available_skills", "arguments": {}}}]},
        {"role": "assistant", "tool_calls": [{"id": "guidance", "function": {
            "name": "load_skill_guidance", "arguments": {"skill_id": "national-scholarship"}}}]},
        {"role": "assistant", "content": "我会按国家奖学金赛道协助你。"},
    ])
    requests = []

    def record(payload):
        requests.append(copy.deepcopy(payload))
        return next(responses)

    if stream:
        def fake_stream(payload):
            result = record(payload)
            if result.get("content"):
                yield {"type": "delta", "text": result["content"]}
            yield {"type": "final", "message": result, "usage": None}
        monkeypatch.setattr(agent, "_stream_post", fake_stream)
        result = list(agent.chat_stream(project["id"], "请帮我准备申请书"))[-1]
    else:
        monkeypatch.setattr(agent, "_post", lambda _endpoint, payload: {"message": record(payload)})
        result = agent.chat(project["id"], "请帮我准备申请书")

    assert result["tool_calls"] == ["list_available_skills", "load_skill_guidance"]
    assert "国家奖学金" in result["message"]
    advertised = {schema["function"]["name"] for schema in requests[0]["tools"]}
    assert {"list_available_skills", "load_skill_guidance"} <= advertised
    catalog = json.loads(requests[1]["messages"][-1]["content"])
    assert len(catalog["skills"]) == 35
    assert catalog["current_skill_id"] == "national-scholarship"
    outstanding = next(item for item in catalog["skills"] if item["id"] == "outstanding-student")
    assert "优秀团员" in outstanding["aliases"]
    guidance = json.loads(requests[2]["messages"][-1]["content"])
    assert guidance["skill_id"] == "national-scholarship"
    assert "信息采集" in guidance["guidance"]
    assert "张华" not in guidance["guidance"]
    assert store.get_project(project["id"])["state"] == {"skill_id": "national-scholarship"}


def test_skill_discovery_requires_valid_selected_track():
    no_skill = {"state": {"skill_id": ""}}
    catalog = invoke_discovery_tool("list_available_skills", {}, no_skill)
    assert len(catalog["skills"]) == 35 and catalog["current_skill_id"] is None
    assert "尚未选定" in invoke_discovery_tool(
        "load_skill_guidance", {"skill_id": "national-scholarship"}, no_skill
    )["error"]
    selected = {"state": {"skill_id": "national-scholarship"}}
    assert "赛道不同" in invoke_discovery_tool(
        "load_skill_guidance", {"skill_id": "innovation-research"}, selected
    )["error"]
    for skill_id in ("../../secret", "nonexistent", "/tmp/private"):
        assert "error" in invoke_discovery_tool("load_skill_guidance", {"skill_id": skill_id}, selected)
    assert "error" in invoke_discovery_tool(
        "load_skill_guidance", {"skill_id": "national-scholarship", "project_id": "other"}, selected
    )


def test_long_skill_guidance_is_readable_in_bounded_filtered_pages():
    selected = {"state": {"skill_id": "challenge-cup"}}
    skill = registry.get("challenge-cup")
    expected = model_safe_guidance(skill["skill_path"].read_text(encoding="utf-8"))
    assert len(expected) > 16000  # Exercises multiple pages of a real checked-in Skill.
    pages = []
    offset = 0
    while offset is not None:
        result = invoke_discovery_tool("load_skill_guidance", {
            "skill_id": "challenge-cup", "offset": offset,
        }, selected)
        assert result["offset"] == offset
        assert len(result["guidance"]) <= 8000
        pages.append(result["guidance"])
        offset = result["next_offset"]
    assert len(pages) >= 3
    assert "".join(pages) == expected


@pytest.mark.parametrize("offset", [-1, True, 1.5, "8000", None, 9999999])
def test_guidance_rejects_invalid_offsets(offset):
    result = invoke_discovery_tool("load_skill_guidance", {
        "skill_id": "national-scholarship", "offset": offset,
    }, {"state": {"skill_id": "national-scholarship"}})
    assert "error" in result


def test_paginated_guidance_cannot_read_another_track():
    result = invoke_discovery_tool("load_skill_guidance", {
        "skill_id": "challenge-cup", "offset": 8000,
    }, {"state": {"skill_id": "national-scholarship"}})
    assert "赛道不同" in result["error"]
    assert "guidance" not in result


def test_chat_tool_can_load_following_skill_page(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project = store.create_project(title="指南分页测试")
    store.update_project(project["id"], state={"skill_id": "challenge-cup"})
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    responses = iter([
        {"role": "assistant", "tool_calls": [{"id": "first", "function": {
            "name": "load_skill_guidance", "arguments": {"skill_id": "challenge-cup"}}}]},
        {"role": "assistant", "tool_calls": [{"id": "next", "function": {
            "name": "load_skill_guidance", "arguments": {"skill_id": "challenge-cup", "offset": 8000}}}]},
        {"role": "assistant", "content": "已读取后续写作指南。"},
    ])
    requests = []

    def record(_endpoint, payload):
        requests.append(copy.deepcopy(payload))
        return {"message": next(responses)}

    monkeypatch.setattr(agent, "_post", record)
    result = agent.chat(project["id"], "请查阅写作指南")
    first = json.loads(requests[1]["messages"][-1]["content"])
    second = json.loads(requests[2]["messages"][-1]["content"])
    assert first["next_offset"] == second["offset"] == 8000
    assert second["guidance"] and second["next_offset"] == 16000
    assert result["tool_calls"] == ["load_skill_guidance", "load_skill_guidance"]
