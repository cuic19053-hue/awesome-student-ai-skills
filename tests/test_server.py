# -*- coding: utf-8 -*-
"""服务层接口测试（不依赖真实 LLM：无 Key 时应 fail-fast 返回 503）。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = ROOT / "server"
for _p in (str(SERVER_DIR), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient


@pytest.fixture()
def client(monkeypatch):
    # 清掉 Key，保证「未配置」路径可复现；并重置惰性单例
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    import app as server_app

    server_app._state["generator"] = None
    with TestClient(server_app.app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["skills_loaded"] == 35


def test_types(client):
    r = client.get("/types")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 35
    assert len(body["skills"]) == 35


def test_route_returns_candidates(client):
    r = client.post("/route", json={"query": "我要申请国家奖学金", "top_n": 3})
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["candidates"]]
    assert names, "应至少返回一个候选赛道"
    assert "national_scholarship" in names


def test_fields_returns_checklist(client):
    r = client.get("/fields", params={"skill_id": "summary_report"})
    assert r.status_code == 200
    assert isinstance(r.json()["info_fields"], list)


def test_fields_unknown_skill_404(client):
    r = client.get("/fields", params={"skill_id": "not_a_real_skill"})
    assert r.status_code == 404


def test_generate_without_key_fails_fast(client):
    r = client.post("/generate", json={"skill_id": "summary_report", "user_info": {}})
    assert r.status_code == 503
    assert "LLM_API_KEY" in r.json()["detail"]


def test_generate_unknown_skill_404(client):
    r = client.post("/generate", json={"skill_id": "not_a_real_skill", "user_info": {}})
    assert r.status_code == 404
