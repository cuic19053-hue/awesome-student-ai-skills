"""Student-facing starting outlines stay scoped to the selected track."""
import pytest
from fastapi.testclient import TestClient

import server.app as app
from proposal.agent import ModelUnavailable
from proposal.outline_fallback import recommended_outline
from proposal.storage import Store


@pytest.mark.parametrize(("skill_id", "expected", "unrelated"), [
    ("innovation-research", "研究方法与技术路线", "商业模式与运营计划"),
    ("internet-plus", "商业模式与运营计划", "调查结果与分析"),
    ("internet-plus-red-tour", "社会价值与成效", "调查结果与分析"),
    ("social-survey", "调研内容与方法", "商业模式与运营计划"),
    ("graduate-recommendation", "申请动机与专业匹配", "经费预算"),
])
def test_popular_track_outline_is_relevant_and_does_not_guess_results(skill_id, expected, unrelated):
    outline, notice = recommended_outline({"state": {"skill_id": skill_id}})
    titles = [item["title"] for item in outline]
    assert expected in titles and unrelated not in titles
    assert "学校" in notice and len({item["id"] for item in outline}) == len(outline)


def test_recommendation_is_a_read_only_preview_and_never_calls_a_model(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    monkeypatch.setattr(app, "_metered_invoke", lambda *_a, **_k: pytest.fail("No model call for a recommendation"))
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "challenge-cup", "initial_request": "挑战杯社会调查"},
                         outline=[{"id": "previous", "title": "原目录"}], sections={"previous": "学生原文"})
    before = store.get_project(project_id)
    with TestClient(app.app) as client:
        response = client.get(f"/api/projects/{project_id}/outline/recommend")
        assert response.status_code == 200
        assert "调查设计与研究方法" in [item["title"] for item in response.json()["outline"]]
        assert "学校" in response.json()["warning"]
        assert client.get(f"/api/projects/{'f' * 32}/outline/recommend").status_code == 404
    after = store.get_project(project_id)
    assert after["outline"] == before["outline"] and after["sections"] == before["sections"]
    assert after["material_revision"] == before["material_revision"]


def test_model_failure_uses_challenge_outline_instead_of_innovation_template(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    def unavailable(*_args, **_kwargs):
        raise ModelUnavailable("test offline")
    monkeypatch.setattr(app, "_metered_invoke", unavailable)
    project_id = store.create_project()["id"]
    store.update_project(project_id, state={"skill_id": "challenge-cup", "initial_request": "挑战杯科技发明制作"})
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{project_id}/outline/generate")
    assert response.status_code == 200
    assert "设计方案与制作过程" in [item["title"] for item in response.json()["outline"]]
    assert "模型暂不可用" in response.json()["warning"]


def test_saving_stale_outline_does_not_overwrite_other_page_changes(tmp_path, monkeypatch):
    store = Store(tmp_path)
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    pid = store.create_project()["id"]
    saved = store.update_project(pid, state={"skill_id": "social-survey"},
                                 outline=[{"id": "draft", "title": "调研背景"}], sections={"draft": "原正文"})
    stale_revision = saved["material_revision"]
    store.update_project(pid, sections={"draft": "其他页面刚保存的正文"})
    with TestClient(app.app) as client:
        response = client.put(f"/api/projects/{pid}/outline", json={
            "outline": [{"id": "new", "title": "调研方法"}], "expected_revision": stale_revision,
        })
    assert response.status_code == 409
    project = store.get_project(pid)
    assert project["outline"] == [{"id": "draft", "title": "调研背景"}]
    assert project["sections"]["draft"] == "其他页面刚保存的正文"
