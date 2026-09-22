# -*- coding: utf-8 -*-
"""utils 工具链测试。

注意：部分工具用**进程退出码**承载业务结果（例如 review_simulator 通过=0 / 未通过=1），
因此这里只断言「能跑出可解析的 JSON」，不对退出码做统一假设。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _json_from(text: str) -> dict:
    """从混合输出中提取第一个 JSON 对象（忽略前置提示行/尾随文本）。"""
    i = text.find("{")
    assert i >= 0, f"未找到 JSON 输出：{text[:200]!r}"
    obj, _ = json.JSONDecoder().raw_decode(text[i:])
    return obj


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, cwd=str(ROOT)
    )


def test_dispatcher_selfcheck():
    proc = _run("utils/dispatcher.py", "--selfcheck")
    assert proc.returncode == 0, proc.stderr[-800:]
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["disk_count"] == data["indexed_count"] == 35
    assert not data["missing_on_disk"] and not data["missing_in_index"]


def test_plagiarism_checker_outputs_json():
    proc = _run("utils/plagiarism_checker.py", "--text", "本项目研究大学生申报书生成。",
                "--skill", "innovation_research", "--json")
    data = _json_from(proc.stdout)
    assert "overall_similarity" in data
    assert "grade" in data


def test_review_simulator_outputs_json():
    proc = _run("utils/review_simulator.py", "--text", "本项目研究大学生申报书生成，具有创新性。",
                "--skill", "innovation_research", "--json")
    data = _json_from(proc.stdout)
    assert data["max_score"] == 100
    assert 0 <= data["total_score"] <= 100
    assert isinstance(data["dimensions"], list) and data["dimensions"]
