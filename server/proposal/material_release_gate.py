"""Fail closed on the API until the hardened cloud material protocol is ready.

This API-only gate intentionally does not run in the independent Worker: the
Worker must never receive the submission secret. It also does not stop an old
Worker that is already running; operational shutdown is a separate step.
"""
from __future__ import annotations

import os


def gate_cloud_material_api(cloud_mode: bool) -> bool:
    """Disable cloud material entry points unless operator and secret agree.

    An explicit ready flag records the operator's completed migration and
    Worker compatibility checks. Merely having an old secret or old pipeline
    flags cannot activate the new protocol.
    """
    if not cloud_mode:
        return True
    secret = os.environ.get("MATERIAL_SUBMIT_SECRET", "")
    ready = (os.environ.get("MATERIAL_HARDENED_READY", "").lower() == "true"
             and len(secret) >= 32 and secret == secret.strip())
    if not ready:
        # All API-side code, including project views and Worker proxies, uses
        # these same flags. Existing independent processes are not affected.
        os.environ["MATERIAL_PIPELINE_ENABLED"] = "false"
        os.environ["MATERIAL_WORKER_READY"] = "false"
    return ready
