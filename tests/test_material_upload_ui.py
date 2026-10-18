"""Run dependency-free UI regression tests when Node.js is available."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_material_upload_ui():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for material upload UI regression tests")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", str(root / "tests/js/material_upload_ui.test.js")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
