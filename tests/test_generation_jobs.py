# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import pytest
from server.proposal.storage import Store
from server.proposal.jobs import GenerationJobRunner, content_hash


def test_job_runner_lifecycle_and_completion(tmp_path):
    store = Store(tmp_path / "test.db")
    runner = GenerationJobRunner(store, max_workers=2)
    project = store.create_project(title="测试大创项目")

    calls = []
    def fake_invoke():
        calls.append(1)
        return {"content": "这是生成的章节正文", "review_card": {"score": 85.0}}

    job = runner.submit_job(
        project_id=project["id"],
        section_id="background",
        invoke_fn=fake_invoke,
        current_section_content="",
    )
    assert job["status"] in {"pending", "running"}

    # 等待完成
    for _ in range(50):
        time.sleep(0.05)
        st = runner.get_job_status(job["id"])
        if st and st["status"] == "completed":
            break

    final_job = runner.get_job_status(job["id"])
    assert final_job["status"] == "completed"
    assert final_job["step"] == "finished"
    assert final_job["result"]["content"] == "这是生成的章节正文"
    assert len(calls) == 1

    # 验证章节内容已被保存到项目中
    proj_after = store.get_project(project["id"])
    assert proj_after["sections"]["background"] == "这是生成的章节正文"

    # 验证版本历史记录已保存
    versions = store.list_section_versions(project["id"], "background")
    assert len(versions) == 1
    assert versions[0]["source"] == "ai_generated"


def test_job_runner_idempotency_key(tmp_path):
    store = Store(tmp_path / "test.db")
    runner = GenerationJobRunner(store, max_workers=2)
    project = store.create_project(title="测试大创项目")

    calls = []
    def fake_invoke():
        calls.append(1)
        time.sleep(0.1)
        return {"content": "幂等结果"}

    job1 = runner.submit_job(
        project_id=project["id"],
        section_id="method",
        invoke_fn=fake_invoke,
        idempotency_key="idemp_key_123",
    )
    # 重复使用相同 key 提交
    job2 = runner.submit_job(
        project_id=project["id"],
        section_id="method",
        invoke_fn=fake_invoke,
        idempotency_key="idemp_key_123",
    )

    assert job1["id"] == job2["id"]

    for _ in range(50):
        time.sleep(0.05)
        if runner.get_job_status(job1["id"])["status"] == "completed":
            break

    # 确保只执行了一次实际生成
    assert len(calls) == 1


def test_job_runner_active_job_mutex(tmp_path):
    store = Store(tmp_path / "test.db")
    runner = GenerationJobRunner(store, max_workers=2)
    project = store.create_project(title="测试大创项目")

    def slow_invoke():
        time.sleep(0.2)
        return {"content": "慢生成"}

    job1 = runner.submit_job(project["id"], "summary", slow_invoke)
    # 在 job1 运行期间再次提交同一章节
    job2 = runner.submit_job(project["id"], "summary", slow_invoke)

    assert job1["id"] == job2["id"]


def test_job_runner_version_conflict_protection(tmp_path):
    store = Store(tmp_path / "test.db")
    runner = GenerationJobRunner(store, max_workers=2)
    project = store.create_project(title="测试大创项目")

    initial_text = "用户初始写的两句话"
    store.update_project(project["id"], sections={"background": initial_text})

    def fake_gen():
        # 模拟模型生成较慢，用户在此期间手动编辑了输入框
        time.sleep(0.1)
        store.update_project(project["id"], sections={"background": "用户在生成期间修改保存的内容！"})
        return {"content": "AI 生成的大段内容"}

    job = runner.submit_job(
        project_id=project["id"],
        section_id="background",
        invoke_fn=fake_gen,
        current_section_content=initial_text,
    )

    for _ in range(50):
        time.sleep(0.05)
        if runner.get_job_status(job["id"])["status"] == "completed":
            break

    final_job = runner.get_job_status(job["id"])
    assert final_job["status"] == "completed"
    # 验证冲突保护生效
    assert final_job["result"]["conflict_status"] == "user_edit_preserved"

    # 验证项目正文没有被 AI 强制覆盖，保留了用户编辑
    proj_after = store.get_project(project["id"])
    assert proj_after["sections"]["background"] == "用户在生成期间修改保存的内容！"

    # 验证 AI 产物存入了备选版本
    versions = store.list_section_versions(project["id"], "background")
    assert any(v["source"] == "ai_generated_alternative" for v in versions)


def test_job_runner_cancellation(tmp_path):
    store = Store(tmp_path / "test.db")
    runner = GenerationJobRunner(store, max_workers=2)
    project = store.create_project(title="测试大创项目")

    def slow_task():
        time.sleep(0.5)
        return {"content": "本不该完成的内容"}

    job = runner.submit_job(project["id"], "cancel_sec", slow_task)
    success = runner.cancel_job(job["id"])
    assert success is True

    st = runner.get_job_status(job["id"])
    assert st["status"] == "cancelled"
