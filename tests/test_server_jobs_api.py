# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient
from server.app import app, store


def test_api_jobs_lifecycle_and_versions():
    test_client = TestClient(app)

    # 1. 创建项目并初始化目录
    resp = test_client.post("/api/projects", json={"title": "任务API测试项目"})
    assert resp.status_code == 200
    proj_id = resp.json()["id"]

    outline_resp = test_client.put(
        f"/api/projects/{proj_id}/outline",
        json={"outline": [{"id": "project_info", "title": "项目基本信息"}]},
    )
    assert outline_resp.status_code == 200

    # 2. 提交异步任务
    job_resp = test_client.post(
        f"/api/projects/{proj_id}/sections/project_info/jobs",
        json={"idempotency_key": "api_test_idemp_1"},
    )
    assert job_resp.status_code == 200
    job = job_resp.json()
    job_id = job["id"]
    assert job["status"] in {"pending", "running"}

    # 3. 查询任务状态
    status_resp = test_client.get(f"/api/projects/{proj_id}/sections/project_info/jobs/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["id"] == job_id

    # 等待完成
    for _ in range(50):
        time.sleep(0.05)
        st = test_client.get(f"/api/projects/{proj_id}/sections/project_info/jobs/{job_id}").json()
        if st["status"] in {"completed", "failed"}:
            break

    final_st = test_client.get(f"/api/projects/{proj_id}/sections/project_info/jobs/{job_id}").json()
    assert final_st["status"] == "completed"

    # 4. 查看版本历史
    ver_resp = test_client.get(f"/api/projects/{proj_id}/sections/project_info/versions")
    assert ver_resp.status_code == 200
    versions = ver_resp.json()["versions"]
    assert len(versions) >= 1
    ver_id = versions[0]["id"]

    # 5. 手动修改正文
    test_client.put(
        f"/api/projects/{proj_id}/sections/project_info",
        json={"content": "手动输入的新正文"},
    )
    assert store.get_project(proj_id)["sections"]["project_info"] == "手动输入的新正文"

    # 6. 还原历史版本
    restore_resp = test_client.post(
        f"/api/projects/{proj_id}/sections/project_info/versions/{ver_id}/restore"
    )
    assert restore_resp.status_code == 200
    assert restore_resp.json()["restored"] is True
    # 正文被成功还原
    assert store.get_project(proj_id)["sections"]["project_info"] == versions[0]["content"]


def test_api_jobs_cancellation():
    test_client = TestClient(app)

    resp = test_client.post("/api/projects", json={"title": "取消API测试项目"})
    proj_id = resp.json()["id"]

    job_resp = test_client.post(f"/api/projects/{proj_id}/sections/cancel_test/jobs", json={})
    job_id = job_resp.json()["id"]

    cancel_resp = test_client.post(f"/api/projects/{proj_id}/sections/cancel_test/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["cancelled"] in {True, False}
