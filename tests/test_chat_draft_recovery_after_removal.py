"""A historical import marker must not trap a user in the empty-export gate."""
import io

from docx import Document
from fastapi.testclient import TestClient
import pytest

import server.app as app
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.fixture(params=[False, True], ids=["legacy", "material"])
def setup(request, tmp_path, monkeypatch):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", str(request.param).lower())
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    store = Store(tmp_path)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", ProposalTools(store))
    project = store.create_project(title="聊天草稿恢复")
    pid = project["id"]
    store.update_project(pid, state={"skill_id": "innovation-research"})
    store.add_message(pid, "user", "请帮我写项目简介。")
    store.add_message(pid, "assistant", '<WritingBlock variant="document">\n## 项目简介\n\n'
                      '这份项目简介需要在学生确认后才保存，恢复后必须完整出现在 Word 文件中。\n</WritingBlock>')
    with TestClient(app.app) as client:
        url = f"/api/projects/{pid}"
        preview = client.get(url + "/chat-drafts").json()
        item = preview["items"][0]
        client.post(url + "/chat-drafts/confirm", json={
            "snapshot": preview["snapshot"], "items": [{"id": item["id"]}],
        }).raise_for_status()
        yield client, store, pid, url, item


@pytest.mark.parametrize("change", ["clear_body", "remove_from_outline"])
def test_cleared_or_removed_import_can_be_explicitly_restored_and_exported(setup, change):
    client, store, pid, url, original = setup
    sid = original["section_id"]
    if change == "clear_body":
        client.put(url + f"/sections/{sid}", json={"content": ""}).raise_for_status()
    else:
        # The outline API retains orphaned section text to avoid data loss.
        client.put(url + "/outline", json={"outline": [{"id": "new", "title": "新章节"}]}).raise_for_status()
    assert client.post(url + "/export").status_code == 422
    before = store.get_project(pid)
    preview = client.get(url + "/chat-drafts").json()
    item = preview["items"][0]
    assert item["already_saved"] is False
    # Preview itself cannot restore or confirm anything.
    assert store.get_project(pid)["outline"] == before["outline"]
    assert store.get_project(pid)["sections"] == before["sections"]
    client.post(url + "/chat-drafts/confirm", json={
        "snapshot": preview["snapshot"], "items": [{"id": item["id"]}],
    }).raise_for_status()
    project = store.get_project(pid)
    assert any(section["id"] == sid for section in project["outline"])
    assert project["sections"][sid] == original["content"]
    exported = client.post(url + "/export")
    exported.raise_for_status()
    download = client.get(exported.json()["download_url"])
    download.raise_for_status()
    text = "\n".join(p.text for p in Document(io.BytesIO(download.content)).paragraphs)
    assert original["content"] in text


def test_nonempty_hand_edits_remain_saved_without_reimporting_old_chat(setup):
    client, store, pid, url, original = setup
    edited = "学生在正文编辑器里修改后保存的真实新版本。"
    client.put(url + f"/sections/{original['section_id']}", json={"content": edited}).raise_for_status()
    preview = client.get(url + "/chat-drafts").json()
    assert preview["items"][0]["already_saved"] is True
    assert store.get_project(pid)["sections"][original["section_id"]] == edited
    exported = client.post(url + "/export")
    exported.raise_for_status()
    word = Document(io.BytesIO(client.get(exported.json()["download_url"]).content))
    text = "\n".join(p.text for p in word.paragraphs)
    assert edited in text and original["content"] not in text
