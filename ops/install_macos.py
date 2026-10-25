#!/usr/bin/env python3
"""Install an immutable, standalone runtime. Activation requires a verified first archive."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stardust_ops.archive import OpsError, atomic_write, private_path

HOME = Path.home() / "Library/Application Support/StardustOps"
PLIST = Path.home() / "Library/LaunchAgents/website.stardust.logarchive.plist"


def launch_agent(home):
    return {
        "Label": "website.stardust.logarchive",
        "ProgramArguments": [str(home / "stardust-ops"), "scheduled-run"],
        "WorkingDirectory": str(home), "RunAtLoad": True, "StartInterval": 3600,
        "StartCalendarInterval": {"Hour": 9, "Minute": 0},
        "ProcessType": "Background", "LowPriorityIO": True, "Nice": 10,
        "Umask": 0o077,
        "EnvironmentVariables": {"TZ": "Asia/Shanghai", "PYTHONUNBUFFERED": "1"},
        # The program rotates its own controlled, metadata-only status log.
        "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null",
    }


def checked(args):
    subprocess.run([str(x) for x in args], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        raise OpsError("MACOS_REQUIRED")
    uv = shutil.which("uv")
    if not uv:
        raise OpsError("UV_REQUIRED")
    source = Path(__file__).resolve().parent
    home = private_path(HOME)
    digest = hashlib.sha256()
    for path in [source / "pyproject.toml", source / "requirements.lock",
                 *sorted((source / "stardust_ops").glob("*.py"))]:
        digest.update(path.name.encode()); digest.update(path.read_bytes())
    release = digest.hexdigest()[:16]
    version = private_path(home / "versions" / release)
    runtime = version / "venv"
    if not (version / "installed").exists():
        wheel_dir = private_path(version / "wheels")
        checked([uv, "build", "--wheel", "--out-dir", wheel_dir, source])
        checked([uv, "venv", "--python", "3.12.14", runtime])
        checked([uv, "pip", "install", "--python", runtime / "bin/python",
                 "--require-hashes", "-r", source / "requirements.lock"])
        wheel = next(wheel_dir.glob("stardust_ops-*.whl"))
        checked([uv, "pip", "install", "--python", runtime / "bin/python", "--no-deps", wheel])
        checked([runtime / "bin/stardust-ops", "--version"])
        atomic_write(version / "installed", release.encode())
    # Stable wrapper, no source checkout or project virtualenv on the execution path.
    launcher = home / "stardust-ops"
    atomic_write(launcher, ("#!/bin/sh\numask 077\nexec " +
        __import__("shlex").quote(str(runtime / "bin/stardust-ops")) + ' "$@"\n').encode())
    os.chmod(launcher, 0o700)
    print(f"Installed: {launcher}")
    if not args.activate:
        print("尚未启用定时任务。先运行 init，再运行本脚本 --activate。")
        return
    if datetime.now().astimezone().utcoffset() != timedelta(hours=8):
        raise OpsError("LAUNCHD_CALENDAR_REQUIRES_BEIJING_SYSTEM_TIMEZONE")
    if not (home / "config.json").exists():
        raise OpsError("OPS_NOT_INITIALIZED")
    # No scheduler is loaded if Keychain, network, disk, verification or receipts fail.
    checked([launcher, "archive", "run"])
    checked([launcher, "archive", "verify"])
    private_path(PLIST.parent)
    atomic_write(PLIST, plistlib.dumps(launch_agent(home)))
    checked(["plutil", "-lint", PLIST])
    domain = "gui/" + str(os.getuid())
    subprocess.run(["launchctl", "bootout", domain, str(PLIST)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    checked(["launchctl", "bootstrap", domain, PLIST])
    checked(["launchctl", "kickstart", domain + "/website.stardust.logarchive"])
    print("LaunchAgent enabled: 每天北京时间 09:00，登录/唤醒补拉，失败每小时重试。")


if __name__ == "__main__":
    try:
        main()
    except (OpsError, subprocess.CalledProcessError) as exc:
        print(str(exc) if isinstance(exc, OpsError) else "OPS_INSTALL_OR_ACTIVATION_FAILED", file=sys.stderr)
        raise SystemExit(1)
