"""End-to-end contracts for the shared conversation runtime, with fake models."""
from __future__ import annotations

import copy
import io
import json
import re

import pytest

import server.app  # Registers the server module path.
from proposal.agent import ModelUnavailable, OllamaAgent, _system_prompt
from proposal.retrieval import ProjectRetriever
from proposal.skills import model_safe_guidance, registry
from proposal.storage import Store
from proposal.supabase_store import SupabaseStore
from proposal.tools import ProposalTools


def test_guidance_excludes_sample_paragraphs_and_preserves_other_sections():
    source = '''# 写作指南
正常要求：根据事实撰写。
✅ 正确示例：
> 我叫张华，专业排名第一。

### 完整示例
我是李明，在校园获得奖项。

### 实际写作要求
- 突出真实经历。
| 专业 | 全称，如“计算机科学与技术” |
'''
    guidance = model_safe_guidance(source)
    assert "张华" not in guidance and "李明" not in guidance
    assert "计算机科学与技术" not in guidance
    assert "突出真实经历" in guidance


def test_real_skill_samples_are_not_loaded_into_model_guidance():
    guidance = registry.model_guidance("national-scholarship")
    assert "张华" not in guidance and "1/120" not in guidance
    assert "信息采集" in guidance
    assert "硬门槛" not in guidance
    assert "必须为全日制二年级" not in guidance
    assert "同一学业阶段一般不重复获得" not in guidance
    assert "build.py" not in guidance
    # Case-driven titles must not hide the whole rest of any catalogue Skill.
    for skill in registry.list():
        assert len(registry.model_guidance(skill["id"])) > 1000, skill["id"]


def test_unknown_project_skill_never_silently_uses_another_track(tmp_path):
    store = Store(tmp_path)
    project = store.create_project()
    store.update_project(project["id"], state={"skill_id": "unavailable-skill"})
    project = store.get_project(project["id"])
    prompt = _system_prompt(project)
    assert "赛道指南无法加载" in prompt
    assert "当前项目赛道：" not in prompt
    result = ProposalTools(store, ProjectRetriever(store)).get_writing_guidance(project["id"])
    assert "赛道指南不可用" in result["error"]


@pytest.mark.parametrize("stream", [False, True])
def test_model_cannot_bypass_tool_policy_or_choose_another_project(tmp_path, monkeypatch, stream):
    store = Store(tmp_path)
    tools = ProposalTools(store, ProjectRetriever(store))
    agent = OllamaAgent(store, tools)
    project = store.create_project(title="当前项目")
    other = store.create_project(title="其他项目")
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    invoked = []
    original_invoke = tools.invoke

    def tracked_invoke(name, arguments):
        invoked.append((name, arguments))
        return original_invoke(name, arguments)

    monkeypatch.setattr(tools, "invoke", tracked_invoke)
    original_schemas = tools.schemas
    monkeypatch.setattr(tools, "schemas", lambda: original_schemas() + [{
        "type": "function", "function": {"name": "future_privileged_action", "parameters": {
            "type": "object", "properties": {"project_id": {"type": "string"}},
        }},
    }])
    calls = [
        {"id": "read", "function": {"name": "get_project_state", "arguments": {"project_id": other["id"]}}},
        {"id": "write", "function": {"name": "save_section", "arguments": {
            "project_id": project["id"], "section_id": "intro", "content": "未经确认"}}},
        *[{"id": name, "function": {"name": name, "arguments": {"project_id": project["id"]}}}
          for name in ("simulate_review", "export_docx", "save_diagram", "future_privileged_action")],
    ]
    messages = [
        {"role": "assistant", "content": "我先查看资料。", "tool_calls": calls},
        {"role": "assistant", "content": "资料已读取，请核对草稿。"},
    ]
    requests = []

    if stream:
        def reply(payload):
            requests.append(copy.deepcopy(payload))
            message = messages.pop(0)
            yield {"type": "delta", "text": message["content"]}
            yield {"type": "final", "message": message, "usage": None}
        monkeypatch.setattr(agent, "_stream_post", reply)
        events = list(agent.chat_stream(project["id"], "请帮我梳理材料"))
        assert [item["type"] for item in events].count("reset") == 1
        result = events[-1]
    else:
        def reply(_endpoint, payload):
            requests.append(copy.deepcopy(payload))
            return {"message": messages.pop(0)}
        monkeypatch.setattr(agent, "_post", reply)
        result = agent.chat(project["id"], "请帮我梳理材料")

    assert result["message"] == "资料已读取，请核对草稿。"
    assert invoked == [("get_project_state", {"project_id": project["id"]})]
    assert store.get_project(project["id"])["sections"] == {}
    offered = {schema["function"]["name"] for schema in requests[0]["tools"]}
    assert offered.isdisjoint({"save_section", "simulate_review", "export_docx", "save_diagram", "future_privileged_action"})
    tool_results = [json.loads(item["content"]) for item in requests[1]["messages"] if item["role"] == "tool"]
    assert tool_results[0]["project"]["id"] == project["id"]
    assert all("error" in item for item in tool_results[1:])
    assert [item["role"] for item in store.messages(project["id"])] == ["user", "assistant"]


def test_chat_context_uses_snapshot_before_saving_current_message(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project = store.create_project()
    store.add_message(project["id"], "user", "此前问题")
    store.add_message(project["id"], "assistant", "此前回答")
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    requests = []
    monkeypatch.setattr(agent, "_post", lambda _endpoint, payload: requests.append(copy.deepcopy(payload))
                        or {"message": {"content": "新的回答"}})
    agent.chat(project["id"], "本轮问题")
    assert [(item["role"], item["content"]) for item in requests[0]["messages"][1:]] == [
        ("user", "此前问题"), ("assistant", "此前回答"), ("user", "本轮问题"),
    ]


def test_chat_does_not_remove_questions_from_generated_drafts(tmp_path, monkeypatch):
    store = Store(tmp_path)
    project = store.create_project()
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    monkeypatch.setattr(agent, "_policy_evidence_reply", lambda *_: None)
    draft = '<WritingBlock variant="document">\n## 问卷\n1. 你希望解决什么？\n2. 你有哪些建议？\n</WritingBlock>'
    monkeypatch.setattr(agent, "_post", lambda *_: {"message": {"content": draft}})
    assert agent.chat(project["id"], "给我一份问卷")['message'] == draft
    assert store.messages(project["id"])[-1]["content"] == draft


@pytest.mark.parametrize("complete", [False, True])
def test_ollama_stream_requires_completion_before_success(tmp_path, monkeypatch, complete):
    store = Store(tmp_path)
    agent = OllamaAgent(store, ProposalTools(store, ProjectRetriever(store)))
    response = json.dumps({"message": {"content": "部分回答"}, "done": complete}, ensure_ascii=False)
    monkeypatch.setattr("proposal.agent.urllib.request.urlopen", lambda *_args, **_kwargs:
                        io.BytesIO((response + "\n").encode()))
    if complete:
        assert list(agent._stream_post({"messages": []}))[-1]["message"]["content"] == "部分回答"
    else:
        with pytest.raises(ModelUnavailable, match="未完成"):
            list(agent._stream_post({"messages": []}))


def test_local_old_equal_timestamps_keep_insertion_order(tmp_path):
    store = Store(tmp_path)
    project = store.create_project()
    for role, content in [("user", "第一条"), ("assistant", "第二条"), ("user", "第三条")]:
        store.add_message(project["id"], role, content)
    with store.connect() as db:
        db.execute("UPDATE messages SET created_at=? WHERE project_id=?", ("2026-01-01T00:00:00+00:00", project["id"]))
    assert [item["content"] for item in store.messages(project["id"])] == ["第一条", "第二条", "第三条"]
    assert [item["content"] for item in store.messages(project["id"], limit=2)] == ["第二条", "第三条"]


def test_cloud_message_write_keeps_subsecond_precision(tmp_path, monkeypatch):
    store = SupabaseStore("https://example.supabase.co", "public-test-key", data_dir=tmp_path)
    calls = []
    monkeypatch.setattr(store, "_rest", lambda table, method="GET", **kwargs: calls.append((table, method, kwargs)))
    store.add_message("project", "user", "测试")
    created_at = calls[0][2]["payload"]["created_at"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00", created_at)
