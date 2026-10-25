from __future__ import annotations

import base64
import fcntl
import gzip
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import struct
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"STARDUSTLOG1\n"
KEY_MAGIC = b"STARDUSTKEY1\n"
MAX_BYTES = 32 * 1024 * 1024
SERVICE = "website.stardust.ops"


class OpsError(RuntimeError):
    """Codes only; never propagate HTTP responses, credentials or archive plaintext."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def private_path(path, *, create=True):
    p = Path(path).expanduser().absolute()
    if any(x.is_symlink() for x in [p, *p.parents]):
        raise OpsError("ARCHIVE_SYMLINK_REFUSED")
    p = p.resolve()
    if any((x / ".git").exists() for x in [p, *p.parents]):
        raise OpsError("ARCHIVE_INSIDE_GIT_REFUSED")
    if create:
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(p, 0o700)
    return p


def atomic_write(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".partial")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(data); out.flush(); os.fsync(out.fileno())
        os.replace(tmp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        tmp.unlink(missing_ok=True)


class Keychain:
    def __init__(self):
        import keyring
        from keyring.backends.macOS import Keyring
        self.backend = keyring.get_keyring()
        if not isinstance(self.backend, Keyring):
            raise OpsError("MAC_KEYCHAIN_REQUIRED")

    def get(self, account):
        try:
            value = self.backend.get_password(SERVICE, account)
            if not value:
                raise OpsError("KEYCHAIN_ITEM_MISSING")
            return value
        except Exception:
            raise OpsError("KEYCHAIN_LOCKED_OR_UNAVAILABLE") from None

    def set(self, account, value):
        try:
            self.backend.set_password(SERVICE, account, value)
        except Exception:
            raise OpsError("KEYCHAIN_WRITE_FAILED") from None

    def encryption_key(self, key_id):
        try:
            key = base64.b64decode(self.get("archive_key:" + key_id), validate=True)
            if len(key) != 32:
                raise ValueError
            return key
        except OpsError:
            raise
        except Exception:
            raise OpsError("ARCHIVE_KEY_INVALID") from None


def seal(raw, batch, key_id, key, now=None):
    if len(raw) > MAX_BYTES or len(key) != 32:
        raise OpsError("ARCHIVE_TOO_LARGE_OR_INVALID_KEY")
    header = {"format": 1, "schema_version": 1, "batch_id": batch["id"],
              "event_count": batch["event_count"], "plaintext_sha256": batch["plaintext_sha256"],
              "key_id": key_id, "nonce": base64.b64encode(secrets.token_bytes(12)).decode(),
              "archived_at": (now or utcnow()).isoformat()}
    aad = canonical(header)
    encrypted = AESGCM(key).encrypt(base64.b64decode(header["nonce"]), gzip.compress(raw, mtime=0), aad)
    return MAGIC + struct.pack(">I", len(aad)) + aad + encrypted


def unseal(data, keys):
    try:
        if not data.startswith(MAGIC) or len(data) > MAX_BYTES + 8192:
            raise ValueError
        start = len(MAGIC)
        size = struct.unpack(">I", data[start:start+4])[0]
        if not 1 <= size <= 8192:
            raise ValueError
        aad = data[start+4:start+4+size]
        header = json.loads(aad)
        if header["format"] != 1 or header["schema_version"] != 1:
            raise OpsError("UNSUPPORTED_ARCHIVE_VERSION")
        uuid.UUID(header["batch_id"])
        if not re.fullmatch(r"[a-f0-9]{32}", header["key_id"]) or not 1 <= header["event_count"] <= 5000:
            raise ValueError
        timestamp(header["archived_at"])
        key = keys.encryption_key(header["key_id"])
        raw_gzip = AESGCM(key).decrypt(base64.b64decode(header["nonce"], validate=True), data[start+4+size:], aad)
        with gzip.GzipFile(fileobj=io.BytesIO(raw_gzip)) as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or sha(raw) != header["plaintext_sha256"]:
            raise ValueError
        lines = raw.decode("utf-8").splitlines()
        if len(lines) != header["event_count"]:
            raise ValueError
        events = [json.loads(line) for line in lines]
        if len({e["event_id"] for e in events}) != len(events):
            raise ValueError
        return header, events
    except OpsError:
        raise
    except Exception:
        raise OpsError("ARCHIVE_AUTHENTICATION_OR_CONTENT_FAILED") from None


@contextmanager
def archive_lock(directory):
    fd = os.open(directory / ".archive.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OpsError("ARCHIVE_ALREADY_RUNNING") from None
        yield
    finally:
        os.close(fd)


class Archiver:
    def __init__(self, api, keys, config, *, now=utcnow, disk_usage=shutil.disk_usage):
        self.api, self.keys, self.config = api, keys, config
        self.now, self.disk_usage = now, disk_usage
        self.directory = private_path(config["archive_dir"], create=False)
        if not self.directory.is_dir():
            raise OpsError("ARCHIVE_DIRECTORY_MISSING")

    def receipt(self, path, expected=None):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES + 8192:
            raise OpsError("ARCHIVE_FILE_UNSAFE")
        data = path.read_bytes()
        header, _ = unseal(data, self.keys)
        if expected and (header["batch_id"] != expected["id"] or any(header[k] != expected[k] for k in ("event_count", "plaintext_sha256"))):
            raise OpsError("ARCHIVE_BATCH_MISMATCH")
        result = {k: header[k] for k in ("event_count", "plaintext_sha256", "key_id")}
        result["ciphertext_sha256"] = sha(data)
        return header, result

    def acknowledge(self, path, batch=None):
        header, receipt = self.receipt(path, batch)
        marker = path.with_suffix(".receipt.json")
        if not marker.exists():
            result = self.api.call("POST", f"/archive/batches/{header['batch_id']}/ack", receipt)
            if result != {"verified": True}:
                raise OpsError("ARCHIVE_ACK_NOT_CONFIRMED")
            atomic_write(marker, canonical({"verified": True, "completed_at": self.now().isoformat(), **receipt}))
        else:
            saved = json.loads(marker.read_text())
            if any(saved.get(k) != receipt[k] for k in receipt):
                raise OpsError("ARCHIVE_RECEIPT_MISMATCH")
        return header

    def verify_cloud_inventory(self):
        """Detect deleted files too, not only corrupted files that still exist."""
        params = {}
        previous = None
        for _ in range(10000):
            page = self.api.call("GET", "/archive/inventory", params=params)["batches"]
            if not isinstance(page, list) or len(page) > 200:
                raise OpsError("ARCHIVE_INVENTORY_INVALID")
            for batch in page:
                path = self.directory / (str(uuid.UUID(batch["id"])) + ".slog")
                _, receipt = self.receipt(path, batch)
                if any(receipt[k] != batch[k] for k in ("ciphertext_sha256", "key_id")):
                    raise OpsError("ARCHIVE_INVENTORY_MISMATCH")
            if len(page) < 200:
                return
            cursor = (page[-1]["verified_at"], page[-1]["id"])
            if cursor == previous:
                raise OpsError("ARCHIVE_INVENTORY_CURSOR_STALLED")
            params = {"after_time": cursor[0], "after_id": cursor[1]}
            previous = cursor
        raise OpsError("ARCHIVE_INVENTORY_TOO_LARGE")

    def run(self):
        with archive_lock(self.directory):
            if self.disk_usage(self.directory).free < 1024**3:
                raise OpsError("ARCHIVE_DISK_SPACE_LOW")
            key_id = self.config["key_id"]
            key = self.keys.encryption_key(key_id)  # Fail closed before any acknowledgement/purge.
            count = 0
            # An acknowledgement may have succeeded before the local checkpoint failed.
            for path in sorted(self.directory.glob("*.slog")):
                # Verify even previously acknowledged files BEFORE requesting any purge.
                self.acknowledge(path)
            for _ in range(1000):
                batch = self.api.call("POST", "/archive/batches")["batch"]
                if batch is None:
                    break
                if batch.get("schema_version") != 1 or not 1 <= batch["event_count"] <= 5000:
                    raise OpsError("UNSUPPORTED_BATCH_OR_SIZE")
                path = self.directory / (str(uuid.UUID(batch["id"])) + ".slog")
                if not path.exists():
                    lines, total = [], 0
                    for offset in range(0, batch["event_count"], 200):
                        page = self.api.call("GET", f"/archive/batches/{batch['id']}", params={"offset": offset})
                        if page["batch"]["plaintext_sha256"] != batch["plaintext_sha256"] or not 1 <= len(page["lines"]) <= 200:
                            raise OpsError("ARCHIVE_PAGE_MISMATCH")
                        for line in page["lines"]:
                            data = (line + "\n").encode()
                            total += len(data)
                            if total > MAX_BYTES:
                                raise OpsError("ARCHIVE_TOO_LARGE")
                            lines.append(data)
                    raw = b"".join(lines)
                    if len(lines) != batch["event_count"] or sha(raw) != batch["plaintext_sha256"]:
                        raise OpsError("ARCHIVE_DIGEST_MISMATCH")
                    atomic_write(path, seal(raw, batch, key_id, key, self.now()))
                self.acknowledge(path, batch)
                count += 1
            else:
                raise OpsError("ARCHIVE_BACKLOG_NOT_FINISHED")
            for path in sorted(self.directory.glob("*.slog")):
                self.receipt(path)
            health = self.api.call("GET", "/archive/status")
            self.verify_cloud_inventory()
            for _ in range(1000):
                result = self.api.call("POST", "/archive/purge")
                if result.get("deleted") == 0:
                    break
            else:
                raise OpsError("ARCHIVE_PURGE_NOT_FINISHED")
            removed = 0
            for path in self.directory.glob("*.slog"):
                header, _ = self.receipt(path)
                completed = json.loads(path.with_suffix(".receipt.json").read_text()).get("completed_at")
                if completed and max(timestamp(header["archived_at"]), timestamp(completed)) < self.now()-timedelta(days=180):
                    path.unlink()
                    path.with_suffix(".receipt.json").unlink(missing_ok=True)
                    removed += 1
            return {"archived_batches": count, "expired_local_batches": removed, "status": "ok",
                    "capacity_warning": bool(health.get("capacity_warning")),
                    "database_bytes": health.get("database_bytes")}

    def events(self):
        for path in sorted(self.directory.glob("*.slog")):
            self.receipt(path)
            _, events = unseal(path.read_bytes(), self.keys)
            yield from events


def daily_slot(now):
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    return (local.date() if local.hour >= 9 else local.date()-timedelta(days=1)).isoformat()


def backup_keys(keys, key_ids, password):
    if len(password) < 12:
        raise OpsError("RECOVERY_PASSPHRASE_TOO_SHORT")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    key = Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(password.encode())
    raw = canonical({kid: base64.b64encode(keys.encryption_key(kid)).decode() for kid in key_ids})
    return KEY_MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, raw, KEY_MAGIC)


def restore_keys(data, password):
    try:
        if not data.startswith(KEY_MAGIC) or len(data)>65536:
            raise ValueError
        i=len(KEY_MAGIC);salt=data[i:i+16];nonce=data[i+16:i+28]
        key=Scrypt(salt=salt,length=32,n=2**17,r=8,p=1).derive(password.encode())
        return json.loads(AESGCM(key).decrypt(nonce,data[i+28:],KEY_MAGIC))
    except Exception:
        raise OpsError("RECOVERY_AUTHENTICATION_FAILED") from None
