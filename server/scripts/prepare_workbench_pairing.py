"""Prepare a private, one-to-one shop-code ↔ provider-code import.

This does not import, activate, or redeem anything. Both outputs are bearer
secrets, so transfer the station CSV only over the trusted server channel.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from proposal.credit_security import encrypt_card_code, workbench_voucher_digest


def _private_file(path: Path):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8", newline="")


def prepare(batch: Path, destination: Path, key: bytes) -> dict[str, object]:
    manifest = json.loads((batch / "manifest.json").read_text())
    if manifest["status"] != "draft_not_redeemable" or len(key) != 32:
        raise ValueError("批次或加密密钥无效")
    with (batch / manifest["seller_csv"]).open(newline="", encoding="utf-8-sig") as f:
        seller = list(csv.DictReader(f))
    with (batch / manifest["hashes_csv"]).open(newline="", encoding="utf-8-sig") as f:
        hashes = list(csv.DictReader(f))
    if len(seller) != len(hashes) or len(seller) != manifest["total_codes"]:
        raise ValueError("两份批次文件数量不一致")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(destination, 0o700)
    os.environ["WORKBENCH_REDEEM_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(key).decode()
    provider_csv = destination / "PRIVATE_provider_balance_codes.csv"
    ledger_json = destination / "PRIVATE_workbench_paired_rows.json"
    rows: list[dict[str, object]] = []
    with _private_file(provider_csv) as f:
        station = csv.writer(f)
        station.writerow(["code", "type", "value", "status", "notes"])
        seen: set[str] = set()
        for public, digest_row in zip(seller, hashes, strict=True):
            face = int(public["denomination_cny"])
            if (
                public["batch_id"] != manifest["batch_id"]
                or digest_row["batch_id"] != manifest["batch_id"]
                or int(digest_row["face_value_micro_cny"]) != face * 1_000_000
                or workbench_voucher_digest(public["code"]).hex() != digest_row["code_hash"]
            ):
                raise ValueError("批次顺序、面值或卡密摘要不匹配")
            private_code = secrets.token_hex(16).upper()
            while private_code in seen:
                private_code = secrets.token_hex(16).upper()
            seen.add(private_code)
            station.writerow([private_code, "balance", face, "unused", f"workbench:{manifest['batch_id']}"])
            rows.append({
                "batch_id": manifest["batch_id"],
                "face_value_micro_cny": face * 1_000_000,
                "code_hash": "\\x" + digest_row["code_hash"],
                "provider_code_ciphertext": "\\x" + encrypt_card_code(private_code).hex(),
                "status": "draft",
            })
    with _private_file(ledger_json) as f:
        json.dump(rows, f, separators=(",", ":"))
    return {"count": len(rows), "total_cny": sum(int(r["face_value_micro_cny"]) for r in rows) // 1_000_000,
            "batch_id": manifest["batch_id"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--key-file", type=Path, required=True)
    args = parser.parse_args()
    key = args.key_file.read_bytes()
    result = prepare(args.batch, args.destination, key)
    print(f"Prepared {result['count']} paired drafts (¥{result['total_cny']}); nothing imported or activated.")
