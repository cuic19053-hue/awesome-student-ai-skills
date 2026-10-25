"""Chat-to-document recovery: explicit confirmation, no model calls, no overwrite."""
import io
import sys
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from proposal.chat_drafts import candidates
from proposal.storage import Store
from proposal.tools import ProposalTools


def block(title, content, block_id="reused"):
    return f'<WritingBlock id="{block_id}" variant="document">## {title}\n\n{content}</WritingBlock>'


@pytest.fixture(params=[False, True], ids=["legacy", "material"])
def setup(request, monkeypatch, tmp_path):
    import app
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", str(request.param).lower())
    monkeypatch.setenv("MATERIAL_WORKER_READY", "true")
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    store = Store(tmp_path)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", ProposalTools(store))
    p = store.create_project(title="合成测试项目")
    p = store.update_project(p["id"], state={"skill_id": "innovation-research"})
    store.add_message(p["id"], "assistant", block("一、项目目的", "已生成但未保存的合成正文。"))
    store.add_message(p["id"], "assistant", block("七、经费预算", "建议预算：待核对，不代表已批准。"))
    with TestClient(app.app) as client:
        yield client, store, p["id"], request.param


def test_latest_complete_block_per_heading_not_reused_id():
    partial = '<WritingBlock id="x" variant="document">## 一、目的\n残缺快照'
    raw = partial + "前言" + block("一、目的", "完整末版") + block("二、预算", "待补充")
    messages = [{"role": "user", "content": block("不应导入", "用户消息")},
                {"role": "assistant", "content": raw},
                {"role": "assistant", "content": block("一、目的", "修订末版")},
                {"role": "assistant", "content": partial}]
    result = candidates({"outline": [], "sections": {}, "state": {}}, messages)
    assert [r["title"] for r in result] == ["目的", "预算"]
    assert result[0]["content"] == "修订末版"
    assert len({r["section_id"] for r in result}) == 2


def test_confirmation_preserves_chat_and_does_not_confirm_facts(setup, monkeypatch):
    client, store, pid, _ = setup
    from proposal.agent import OllamaAgent
    monkeypatch.setattr(OllamaAgent, "_post", lambda *_: pytest.fail("Must not call a model"))
    url = f"/api/projects/{pid}/chat-drafts"
    previous_messages = store.messages(pid, limit=200)
    preview = client.get(url).json()
    assert len(preview["items"]) == 2
    assert store.get_project(pid)["sections"] == {}
    edited = "用户核对后的目的，仍是草稿。"
    saved = client.post(url + "/confirm", json={
        "snapshot": preview["snapshot"],
        "items": [{"id": preview["items"][0]["id"], "content": edited},
                  {"id": preview["items"][1]["id"]}],
    })
    assert saved.status_code == 200, saved.text
    p = store.get_project(pid)
    assert len(p["outline"]) == len(p["sections"]) == 2
    assert edited in p["sections"].values()
    assert not p["state"].get("confirmed_facts")
    assert not p["state"].get("budget")
    assert store.messages(pid, limit=200) == previous_messages
    assert all(item["already_saved"] for item in client.get(url).json()["items"])
    exported = client.post(f"/api/projects/{pid}/export")
    assert exported.status_code == 200, exported.text
    data = client.get(exported.json()["download_url"]).content
    text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    assert edited in text
    assert "建议预算：待核对" in text


def test_stale_review_or_existing_manual_body_is_never_overwritten(setup):
    client, store, pid, _ = setup
    url = f"/api/projects/{pid}/chat-drafts"
    preview = client.get(url).json()
    first = preview["items"][0]
    store.update_project(pid, outline=[{"id": first["section_id"], "title": first["title"]}],
                         sections={first["section_id"]: "刚刚保存的手写正文"})
    request = {"snapshot": preview["snapshot"], "items": [{"id": first["id"]}]}
    assert client.post(url + "/confirm", json=request).status_code == 409
    current = client.get(url).json()
    assert current["items"][0]["conflict"]
    request["snapshot"] = current["snapshot"]
    assert client.post(url + "/confirm", json=request).status_code == 409
    assert store.get_project(pid)["sections"][first["section_id"]] == "刚刚保存的手写正文"


def test_foreign_candidate_or_project_is_rejected(setup):
    client, store, pid, _ = setup
    url = f"/api/projects/{pid}/chat-drafts"
    preview = client.get(url).json()
    assert client.post(url + "/confirm", json={
        "snapshot": preview["snapshot"], "items": [{"id": "f" * 64}],
    }).status_code == 409
    assert client.get("/api/projects/" + "f" * 32 + "/chat-drafts").status_code == 404
    assert store.get_project(pid)["sections"] == {}


def test_empty_export_requires_explicit_confirmation_before_enqueuing(setup):
    client, store, pid, material = setup
    assert client.post(f"/api/projects/{pid}/export").status_code == 422
    if material:
        result = client.post(f"/api/projects/{pid}/material/jobs", json={
            "revision": store.get_project(pid)["material_revision"],
            "kind": "export", "idempotency_key": "empty-should-not-queue",
        })
        assert result.status_code == 422
        from proposal.material_jobs import MaterialJobs
        assert not MaterialJobs(store).call("list", project_id=pid)
    # An intentionally requested incomplete draft remains supported.
    assert client.post(f"/api/projects/{pid}/export",
                       json={"allow_empty_draft": True}).status_code == 200


def test_cloud_download_requires_bearer_not_a_public_link(setup, monkeypatch):
    client, _, pid, _ = setup
    import httpx
    import app
    class Auth:
        async def get(self, *_args, **_kwargs):
            return httpx.Response(200, json={"id": "isolated-user", "created_at": "2026-01-01T00:00:00Z"})
    monkeypatch.setattr(app, "CLOUD_MODE", True)
    monkeypatch.setattr(app.app.state, "auth_http", Auth())
    token = {"Authorization": "Bearer isolated-not-real-token"}
    exported = client.post(f"/api/projects/{pid}/export", headers=token,
                           json={"allow_empty_draft": True})
    assert exported.status_code == 200
    url = exported.json()["download_url"]
    assert client.get(url).status_code == 401
    assert client.get(url, headers=token).status_code == 200
    assert client.get(f"/api/projects/{pid}/chat-drafts").status_code == 401
