"""Chat-to-document recovery: explicit confirmation, no model calls, no overwrite."""
import io
import sys
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from proposal.chat_drafts import candidates, plain_application_letter, title_key
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


@pytest.mark.parametrize(("raw", "expected"), [
    ("4.1 封面", "封面"), ("1.2.3 项目简介", "项目简介"), ("二、项目摘要", "项目摘要"),
    ("1. 项目摘要", "项目摘要"), ("2026.11.08 进度安排", "2026.11.08进度安排"),
])
def test_heading_numbers_are_removed_without_corrupting_dates(raw, expected):
    assert title_key(raw) == expected


def test_plain_complete_letter_is_reviewable_and_excludes_followup_advice(setup):
    client, store, pid, _ = setup
    store.add_message(pid, "user", "请帮我写一份国家励志奖学金申请书。")
    store.add_message(pid, "assistant", "好的，以下是申请书：\n\n## 国家励志奖学金申请书\n\n尊敬的评审老师：\n\n"
                      "我叫李明，现就读于信息学院。我申请国家励志奖学金，希望继续认真学习，"
                      "并根据自己的经历完善相关申请材料。\n\n此致\n敬礼！\n申请人：李明\n"
                      "日期：待补充\n\n请补充您的实际经历。")
    url = f"/api/projects/{pid}/chat-drafts"
    preview = client.get(url).json()
    item = next(item for item in preview["items"] if item["title"] == "国家励志奖学金申请书")
    assert "信息学院" in item["content"] and "申请人：李明" in item["content"]
    assert "请补充您的实际经历" not in item["content"]
    assert client.post(url + "/confirm", json={"snapshot": preview["snapshot"], "items": [{"id": item["id"]}]}).status_code == 200
    exported = client.post(f"/api/projects/{pid}/export").json()
    doc = Document(io.BytesIO(client.get(exported["download_url"]).content))
    assert "信息学院" in "\n".join(paragraph.text for paragraph in doc.paragraphs)


@pytest.mark.parametrize(("user_request", "response"), [
    ("申请书应该怎么写？", "申请书模板\n尊敬的老师：\n" + "学习表现。" * 20 + "\n此致\n敬礼！"),
    ("请写一份申请书", "下面是示例：\n转专业申请书\n尊敬的老师：\n" + "学习表现。" * 20 + "\n此致\n敬礼！"),
    ("请写一份申请书", "转专业申请书\n尊敬的老师：\n" + "学习表现。" * 20),
    ("请写一份申请书", '<WritingBlock variant="document">\n转专业申请书\n尊敬的老师：\n' + "学习表现。" * 20 + "\n此致\n敬礼！"),
    ("不要写申请书", "转专业申请书\n尊敬的老师：\n" + "学习表现。" * 20 + "\n此致\n敬礼！"),
])
def test_plain_recovery_excludes_advice_examples_and_incomplete_text(user_request, response):
    assert plain_application_letter(response, user_request) is None


@pytest.mark.parametrize("structured", [False, True])
def test_review_required_response_cannot_bypass_draft_check(structured):
    from proposal.chat_safety import PERSONAL_NUMBER_REVIEW_PREFIX
    body = "尊敬的老师：\n\n我的绩点4.5。" + "学习表现。" * 15 + "\n\n此致\n敬礼！"
    output = block("国家励志奖学金申请书", body) if structured else "国家励志奖学金申请书\n" + body
    message = PERSONAL_NUMBER_REVIEW_PREFIX + "绩点），请先核对或删改；以下内容暂不能直接整理保存。\n\n" + output
    project = {"outline": [], "sections": {}, "state": {}}
    assert candidates(project, [{"role": "user", "content": "请帮我写申请书。"},
                                {"role": "assistant", "content": message}]) == []
    assert candidates(project, [{"role": "assistant", "content": block("国家励志奖学金申请书", "旧版正文")},
                                {"role": "user", "content": "请重新写申请书。"},
                                {"role": "assistant", "content": message}]) == []


def test_project_draft_with_unverified_claims_is_offered_only_for_explicit_review():
    from proposal.chat_safety import PROJECT_CLAIM_REVIEW_PREFIX
    raw = PROJECT_CLAIM_REVIEW_PREFIX + "市场规模），请核对并修改。\n\n" + block(
        "项目简介", "市场规模预计为5000亿元。该项目计划根据学生实际需求进一步讨论方案及实施范围。")
    project = {"outline": [], "sections": {}, "state": {"skill_id": "internet-plus", "skill_category": "competition"}}
    items = candidates(project, [{"role": "user", "content": "请直接写一段项目简介。"},
                                 {"role": "assistant", "content": raw}])
    assert len(items) == 1 and items[0]["requires_review"]
    assert "市场规模" in items[0]["warnings"][0] and "5000亿元" in items[0]["content"]


def test_project_draft_without_detectable_numbers_still_requires_review():
    project = {"outline": [], "sections": {}, "state": {"skill_id": "internet-plus", "skill_category": "competition"}}
    output = block("项目简介", "团队已经开发产品，成员分别负责软件和市场推广。")
    items = candidates(project, [{"role": "user", "content": "请写项目简介。"},
                                 {"role": "assistant", "content": output}])
    assert items[0]["requires_review"]
    assert "检查项目方案" in items[0]["warnings"][0]


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
    request["items"][0]["replace_existing"] = True
    replaced = client.post(url + "/confirm", json=request)
    assert replaced.status_code == 200, replaced.text
    assert store.get_project(pid)["sections"][first["section_id"]] == first["content"]
    versions = store.list_section_versions(pid, first["section_id"])
    assert any(v["content"] == "刚刚保存的手写正文" for v in versions)


def test_draft_review_becomes_stale_when_user_changes_instructions(setup):
    client, store, pid, _ = setup
    url = f"/api/projects/{pid}/chat-drafts"
    preview = client.get(url).json()
    store.add_message(pid, "user", "请不要使用我的个人资料。")
    saved = client.post(url + "/confirm", json={"snapshot": preview["snapshot"], "items": [
        {"id": preview["items"][0]["id"]},
    ]})
    assert saved.status_code == 409
    assert store.get_project(pid)["sections"] == {}


@pytest.mark.parametrize("change", ["upload", "text", "confirmation", "delete"])
def test_draft_review_becomes_stale_when_material_changes(setup, change):
    client, store, pid, _ = setup
    doc = store.add_document(pid, "项目资料.txt", "unused", "reference", "text/plain")
    store.update_document_extraction(doc["id"], "原始材料", "done", confirmed=True, confirmed_by_user=True)
    url = f"/api/projects/{pid}/chat-drafts"
    preview = client.get(url).json()
    if change == "upload":
        store.add_document(pid, "补充材料.txt", "unused", "reference", "text/plain")
    elif change == "text":
        store.update_document_extraction(doc["id"], "修改后的材料", "done", confirmed=True, confirmed_by_user=True)
    elif change == "confirmation":
        store.update_document_extraction(doc["id"], "原始材料", "done", confirmed=False)
    else:
        store.delete_document(doc["id"])
    saved = client.post(url + "/confirm", json={"snapshot": preview["snapshot"], "items": [
        {"id": preview["items"][0]["id"]},
    ]})
    assert saved.status_code == 409
    assert store.get_project(pid)["sections"] == {}


def test_foreign_candidate_or_project_is_rejected(setup):
    client, store, pid, _ = setup
    url = f"/api/projects/{pid}/chat-drafts"
    preview = client.get(url).json()
    assert client.post(url + "/confirm", json={
        "snapshot": preview["snapshot"], "items": [{"id": "f" * 64}],
    }).status_code == 409
    assert client.get("/api/projects/" + "f" * 32 + "/chat-drafts").status_code == 404
    assert store.get_project(pid)["sections"] == {}


def test_conflicting_concurrent_change_never_overwrites_current_section(setup, monkeypatch):
    client, store, pid, _ = setup
    from proposal.materials import MaterialConflict
    url = f"/api/projects/{pid}/chat-drafts"
    first = client.get(url).json()["items"][0]
    store.update_project(pid, outline=[{"id": first["section_id"], "title": first["title"]}],
                         sections={first["section_id"]: "已有正文"})
    preview = client.get(url).json()
    monkeypatch.setattr(store, "update_project", lambda *_args, **_kwargs: (_ for _ in ()).throw(MaterialConflict("changed")))
    result = client.post(url + "/confirm", json={"snapshot": preview["snapshot"], "items": [
        {"id": preview["items"][0]["id"], "replace_existing": True},
    ]})
    assert result.status_code == 409
    assert store.get_project(pid)["sections"][first["section_id"]] == "已有正文"


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
