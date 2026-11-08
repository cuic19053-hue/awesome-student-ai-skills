"""A slow section generation must not overwrite a student's saved work."""
import pytest
from fastapi.testclient import TestClient
import server.app as app
from proposal.storage import Store


@pytest.mark.parametrize("pipeline", [False, True])
def test_sync_generation_preserves_edit_saved_while_model_is_running(tmp_path, monkeypatch, pipeline):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", str(pipeline).lower())
    store = Store(tmp_path)
    pid = store.create_project()["id"]
    store.update_project(pid, state={"skill_id": "internet-plus", "outline_confirmed": True},
                         outline=[{"id": "intro", "title": "项目简介"}],
                         sections={"intro": "学生的旧正文"})
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    class SlowModel:
        def generate_section(self, *_args, **kwargs):
            assert kwargs.get("persist") is False
            store.update_project(pid, sections={"intro": "生成期间学生保存的新正文"})
            return {"section_id": "intro", "content": "生成的草稿", "status": "passed"}
    monkeypatch.setattr(app, "_metered_invoke", lambda _c, _r, _a, _p, call: call(SlowModel()))
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{pid}/sections/intro/generate")
    assert response.status_code == 200
    assert response.json()["conflict_status"] == "user_edit_preserved"
    assert store.get_project(pid)["sections"]["intro"] == "生成期间学生保存的新正文"
    assert any(v["content"] == "生成的草稿" and v["source"] == "ai_generated_alternative"
               for v in store.list_section_versions(pid, "intro"))


@pytest.mark.parametrize("conflict", [False, True])
def test_finished_result_survives_version_storage_failure(tmp_path, monkeypatch, conflict):
    monkeypatch.setenv("MATERIAL_PIPELINE_ENABLED", "false")
    store = Store(tmp_path)
    pid = store.create_project()["id"]
    store.update_project(pid, state={"skill_id": "internet-plus", "outline_confirmed": True},
                         outline=[{"id": "intro", "title": "项目简介"}], sections={"intro": "旧正文"})
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    class SlowModel:
        def generate_section(self, *_args, **_kwargs):
            if conflict:
                store.update_project(pid, sections={"intro": "更新后的正文"})
            return {"section_id": "intro", "content": "生成的草稿", "status": "passed"}
    monkeypatch.setattr(app, "_metered_invoke", lambda _c, _r, _a, _p, call: call(SlowModel()))
    monkeypatch.setattr(store, "save_section_version", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("offline")))
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{pid}/sections/intro/generate")
    assert response.status_code == 200 and response.json()["content"] == "生成的草稿"
    if conflict:
        assert response.json()["result_save_uncertain"]
        assert store.get_project(pid)["sections"]["intro"] == "更新后的正文"
    else:
        assert response.json()["material_applied"]
        assert store.get_project(pid)["sections"]["intro"] == "生成的草稿"
