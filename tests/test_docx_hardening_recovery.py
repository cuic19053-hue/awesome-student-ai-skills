"""Optional layout processing must never destroy a generated Word draft."""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

import server.app as app
import utils.docx_layout_fix as layout_fix
from proposal.storage import Store
from proposal.tools import ProposalTools


@pytest.mark.parametrize("raise_error", [True, False])
def test_layout_failure_leaves_original_word_downloadable(tmp_path, monkeypatch, raise_error):
    store = Store(tmp_path)
    pid = store.create_project(title="测试材料")["id"]
    store.update_project(pid, state={"skill_id": "internet-plus", "outline_confirmed": True},
                         outline=[{"id": "intro", "title": "项目简介"}],
                         sections={"intro": "这段学生保存的正文必须出现在可下载的 Word 中。"})
    monkeypatch.setattr(app, "store", store)
    monkeypatch.setattr(app, "tools", ProposalTools(store))
    monkeypatch.setattr(app, "CLOUD_MODE", False)
    def broken_fix(path):
        path.write_bytes(b"incomplete docx")
        if raise_error:
            raise OSError("simulated interruption")
    monkeypatch.setattr(layout_fix, "fix", broken_fix)
    with TestClient(app.app) as client:
        response = client.post(f"/api/projects/{pid}/export")
        assert response.status_code == 200, response.text
        assert response.json()["layout"]["score"] is None
        download = client.get(response.json()["download_url"])
        assert download.status_code == 200
    text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(download.content)).paragraphs)
    assert "学生保存的正文" in text
