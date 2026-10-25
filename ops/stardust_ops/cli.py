from __future__ import annotations

import argparse
import base64
import getpass
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import secrets
import sys
from datetime import timedelta
import uuid

import httpx

from .archive import (
    Archiver, Keychain, OpsError, atomic_write, backup_keys, daily_slot,
    private_path, restore_keys, timestamp, utcnow,
)

HOME = Path.home() / "Library/Application Support/StardustOps"
DEFAULT_ARCHIVE = Path.home() / "Private/stardust-log-archive"


class API:
    def __init__(self, endpoint, token, client=None):
        if endpoint != "https://agent.stardust.website":
            raise OpsError("UNTRUSTED_OPS_ENDPOINT")
        if not 32 <= len(token) <= 256:
            raise OpsError("OPS_CREDENTIAL_INVALID")
        self.endpoint, self.token = endpoint, token
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)

    def call(self, method, suffix, body=None, params=None):
        if not re.fullmatch(r"/[a-z0-9_/-]+", suffix):
            raise OpsError("INVALID_OPS_ROUTE")
        try:
            response = self.client.request(method, self.endpoint + "/api/ops/logs" + suffix,
                headers={"Authorization": "Bearer " + self.token},
                json=body if method == "POST" else None, params=params)
            if response.status_code != 200:
                raise OpsError({401: "OPS_ACCESS_DENIED", 403: "OPS_ACCESS_DENIED",
                                409: "ARCHIVE_RECEIPT_REJECTED"}.get(response.status_code, "OPS_REQUEST_FAILED"))
            return response.json()
        except OpsError:
            raise
        except Exception:
            raise OpsError("OPS_NETWORK_OR_PROTOCOL_UNAVAILABLE") from None

    def events(self, filters=None, trace_id=None):
        params = {k: v for k, v in (filters or {}).items() if v is not None}
        suffix = "/traces/" + trace_id if trace_id else "/events"
        previous = None
        for _ in range(10000):
            data = self.call("GET", suffix, params=params)
            rows = data["events"]
            if not isinstance(rows, list) or len(rows) > 200:
                raise OpsError("OPS_PAGE_INVALID")
            yield from rows
            if len(rows) < 200:
                return
            cursor = (rows[-1]["ingested_at"], rows[-1]["event_id"])
            if cursor == previous:
                raise OpsError("OPS_CURSOR_STALLED")
            previous = cursor
            params.update(after_time=cursor[0], after_id=cursor[1])
        raise OpsError("OPS_QUERY_TOO_LARGE")


def time_arg(value):
    if value is None:
        return None
    if re.fullmatch(r"\d+[dh]", value):
        return (utcnow()-timedelta(**{"days" if value[-1] == "d" else "hours": int(value[:-1])})).isoformat()
    try:
        return timestamp(value).isoformat()
    except Exception:
        raise OpsError("INVALID_TIME_FILTER") from None


def merge_events(local, remote, filters=None, trace_id=None):
    rows = {row["event_id"]: row for row in [*local, *remote]}
    selected = list(rows.values())
    if trace_id:
        refs = {e.get("usage_request_id") for e in selected
                if e.get("trace_id") == trace_id or e.get("http_request_id") == trace_id} - {None}
        selected = [e for e in selected if e.get("trace_id") == trace_id
                    or e.get("http_request_id") == trace_id or e.get("usage_request_id") in refs]
    for key, value in (filters or {}).items():
        if value is None:
            continue
        if key == "since":
            selected = [e for e in selected if timestamp(e["ingested_at"]) >= timestamp(value)]
        elif key == "until":
            selected = [e for e in selected if timestamp(e["ingested_at"]) < timestamp(value)]
        else:
            selected = [e for e in selected if e.get(key) == value]
    return sorted(selected, key=lambda e: (timestamp(e["ingested_at"]), e["event_id"]))


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def run(argv=None, *, keys=None, api_factory=API, home=HOME):
    parser = argparse.ArgumentParser(prog="stardust-ops")
    parser.add_argument("--version", action="version", version="stardust-ops 1.0.0 / archive schema 1")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE))
    init.add_argument("--credential-stdin", action="store_true")
    logs = sub.add_parser("logs").add_subparsers(dest="action", required=True)
    for action in ("list", "trace", "stats"):
        p = logs.add_parser(action)
        if action == "trace":
            p.add_argument("trace_id")
        else:
            for field in ("since", "until", "operation", "job-id", "owner-id", "error-code", "level", "environment"):
                p.add_argument("--" + field)
        p.add_argument("--source", choices=("both", "cloud", "local"), default="both")
    archive = sub.add_parser("archive").add_subparsers(dest="action", required=True)
    for action in ("run", "status", "verify"):
        archive.add_parser(action)
    key = sub.add_parser("key").add_subparsers(dest="action", required=True)
    for action in ("backup", "restore"):
        p = key.add_parser(action)
        p.add_argument("file")
    sub.add_parser("scheduled-run")
    args = parser.parse_args(argv)
    home = private_path(home)
    config_path = home / "config.json"
    state_path = home / "state.json"
    state = {}
    if args.command == "scheduled-run":
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if state.get("last_success_slot", "") >= daily_slot(utcnow()):
            return 0  # Do not even access Keychain/network after today's successful run.
    try:
        keys = keys or Keychain()
    except Exception as exc:
        code = str(exc) if isinstance(exc, OpsError) else "KEYCHAIN_UNAVAILABLE"
        if args.command == "scheduled-run":
            atomic_write(state_path, canonical_state({**state, "last_error_at": utcnow().isoformat(),
                                                     "status": "failed", "error_code": code}))
        raise OpsError(code) from None
    if args.command == "init":
        directory = private_path(args.archive_dir)
        if config_path.exists():
            raise OpsError("OPS_ALREADY_INITIALIZED")
        token = sys.stdin.readline().strip() if args.credential_stdin else getpass.getpass("专用日志运维凭据（不回显）: ")
        api_factory("https://agent.stardust.website", token).call("GET", "/archive/status")
        key_id = uuid.uuid4().hex
        keys.set("read_capability", token)
        keys.set("archive_key:" + key_id, base64.b64encode(secrets.token_bytes(32)).decode())
        config = {"endpoint": "https://agent.stardust.website", "archive_dir": str(directory),
                  "key_id": key_id, "schema_version": 1, "local_retention_days": 180,
                  "cloud_retention_days": 30, "single_copy_accepted": True}
        atomic_write(config_path, json.dumps(config).encode())
        output({"initialized": True, "archive_dir": str(directory),
                "warning": "单副本模式：设备或密钥丢失后可能无法恢复。请交互式备份恢复密钥。"})
        return 0
    if not config_path.exists():
        raise OpsError("OPS_NOT_INITIALIZED")
    config = json.loads(config_path.read_text())
    if config.get("schema_version") != 1 or not config.get("single_copy_accepted"):
        raise OpsError("UNSUPPORTED_OPS_CONFIGURATION")
    archiver = Archiver(None, keys, config)
    if args.command == "key":
        target = Path(args.file).expanduser().absolute()
        private_path(target.parent)
        if target.resolve().is_relative_to(archiver.directory):
            raise OpsError("RECOVERY_KEY_MUST_BE_SEPARATE")
        if not sys.stdin.isatty():
            raise OpsError("KEY_RECOVERY_REQUIRES_LOCAL_INTERACTION")
        password = getpass.getpass("恢复文件口令（至少 12 字符，不回显）: ")
        if args.action == "backup":
            if target.exists():
                raise OpsError("RECOVERY_FILE_ALREADY_EXISTS")
            if password != getpass.getpass("再次输入恢复口令: "):
                raise OpsError("RECOVERY_PASSPHRASE_MISMATCH")
            key_ids = {config["key_id"]}
            for path in archiver.directory.glob("*.slog"):
                header, _ = archiver.receipt(path)
                key_ids.add(header["key_id"])
            atomic_write(target, backup_keys(keys, sorted(key_ids), password))
        else:
            for kid, value in restore_keys(target.read_bytes(), password).items():
                if not re.fullmatch("[a-f0-9]{32}", kid) or len(base64.b64decode(value, validate=True)) != 32:
                    raise OpsError("RECOVERY_KEY_INVALID")
                keys.set("archive_key:" + kid, value)
        output({"key_recovery": args.action, "status": "ok"})
        return 0
    api = None
    def connect():
        return api_factory(config["endpoint"], keys.get("read_capability"))
    if args.command != "scheduled-run":
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if args.command == "scheduled-run":
        slot = daily_slot(utcnow())
        if state.get("last_success_slot", "") >= slot:
            return 0
        try:
            archiver.api = connect()
            result = archiver.run()
            atomic_write(state_path, canonical_state({"last_success_slot": slot,
                "last_success_at": utcnow().isoformat(), "status": "ok", **result}))
            output(result)
            return 0
        except Exception as exc:
            code = str(exc) if isinstance(exc, OpsError) else "ARCHIVE_INTERNAL_FAILURE"
            atomic_write(state_path, canonical_state({**state, "last_error_at": utcnow().isoformat(),
                                                     "status": "failed", "error_code": code}))
            raise OpsError(code) from None
    if args.command == "archive":
        if args.action != "verify":
            api = connect()
            archiver.api = api
        if args.action == "run":
            output(archiver.run())
        elif args.action == "status":
            output({"local": state, "cloud": api.call("GET", "/archive/status"),
                    "local_files": len(list(archiver.directory.glob("*.slog"))),
                    "coverage": "本地仅保留实际已验证归档；未记录的过去事件不可补回"})
        else:
            n = sum(1 for path in archiver.directory.glob("*.slog") if archiver.receipt(path))
            output({"verified_archives": n})
        return 0
    filters = {k: getattr(args, k, None) for k in (
        "since", "until", "operation", "job_id", "owner_id", "error_code", "level", "environment")}
    for name in ("since", "until"):
        filters[name] = time_arg(filters[name])
    local = list(archiver.events()) if args.source != "cloud" else []
    remote, gap = [], None
    if args.source != "local":
        try:
            api = connect()
            trace_id = getattr(args, "trace_id", None)
            remote = list(api.events(filters, trace_id))
            if trace_id:
                # Bridge billing references whose originating trace is already only on Mac.
                related = merge_events(local, remote, trace_id=trace_id)
                for ref in sorted({e.get("usage_request_id") for e in related} - {None}):
                    remote.extend(api.events({"usage_request_id": ref}))
        except OpsError as exc:
            gap = str(exc)
    rows = merge_events(local, remote, filters, getattr(args, "trace_id", None))
    if args.action == "stats":
        groups = {}
        for row in rows:
            label = row["operation"] + ":" + row["status"]
            groups[label] = groups.get(label, 0) + 1
        output({"events": len(rows), "groups": groups, "coverage_gap": gap})
    else:
        output({"events": rows, "coverage_gap": gap})
    return 1 if gap else 0


def canonical_state(state):
    return json.dumps(state, ensure_ascii=False, sort_keys=True).encode()


def main():
    private_path(HOME)
    handler = RotatingFileHandler(HOME / "scheduler-status.log", maxBytes=1_000_000, backupCount=2)
    os.chmod(HOME / "scheduler-status.log", 0o600)
    logger = logging.getLogger("stardust.ops"); logger.addHandler(handler); logger.setLevel(logging.INFO)
    try:
        code = run()
    except OpsError as exc:
        # OpsError contains controlled codes only.
        logger.error(str(exc)); output({"status": "failed", "error_code": str(exc)})
        code = 1
    except Exception:
        logger.error("OPS_INTERNAL_FAILURE"); output({"status": "failed", "error_code": "OPS_INTERNAL_FAILURE"})
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
