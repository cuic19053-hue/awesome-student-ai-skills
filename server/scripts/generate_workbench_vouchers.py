"""Generate offline, non-redeemable workbench voucher drafts for a card shop.

The seller CSV contains bearer codes. Never commit or upload it to a public
repository. Codes have no value until their hashes are imported and activated
in the production workbench ledger.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import secrets
import uuid
from pathlib import Path
from typing import Mapping


DENOMINATIONS = (1, 5, 10, 20, 50)
CREDITS_PER_CNY = 10


def voucher_digest(code: str) -> str:
    normalized = "".join(code.split()).upper()
    return hashlib.sha256(
        b"workbench-voucher-v1:" + normalized.encode("ascii")
    ).hexdigest()


def _new_code() -> str:
    random_hex = secrets.token_hex(16).upper()  # 128 bits, not sequential.
    return "AGT1-" + "-".join(random_hex[i : i + 8] for i in range(0, 32, 8))


def _private_file(path: Path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8", newline="")


def generate_batch(output_dir: Path, quantities: Mapping[int, int]) -> dict[str, object]:
    if not quantities or any(amount <= 0 or count <= 0 for amount, count in quantities.items()):
        raise ValueError("面值和数量必须是正整数")
    output_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(output_dir, 0o700)

    batch_id = uuid.uuid4().hex
    seller_file = output_dir / "DRAFT_NOT_ACTIVE_seller_codes.csv"
    import_file = output_dir / "DRAFT_NOT_ACTIVE_hashes.csv"
    seen: set[str] = set()
    with _private_file(seller_file) as seller_out, _private_file(import_file) as import_out:
        seller = csv.writer(seller_out)
        importer = csv.writer(import_out)
        seller.writerow(("batch_id", "denomination_cny", "credits", "code"))
        importer.writerow(("batch_id", "face_value_micro_cny", "code_hash", "status"))
        for amount, count in sorted(quantities.items()):
            for _ in range(count):
                code = _new_code()
                while code in seen:
                    code = _new_code()
                seen.add(code)
                seller.writerow((batch_id, amount, amount * CREDITS_PER_CNY, code))
                importer.writerow((batch_id, amount * 1_000_000, voucher_digest(code), "draft"))

    manifest: dict[str, object] = {
        "batch_id": batch_id,
        "status": "draft_not_redeemable",
        "counts_by_cny": {str(amount): count for amount, count in sorted(quantities.items())},
        "total_codes": len(seen),
        "total_face_value_cny": sum(amount * count for amount, count in quantities.items()),
        "total_credits_if_activated": sum(
            amount * CREDITS_PER_CNY * count for amount, count in quantities.items()
        ),
        "seller_csv": seller_file.name,
        "hashes_csv": import_file.name,
        "warning": "未导入并激活前不可兑换；不可提前交付店铺销售。",
    }
    with _private_file(output_dir / "manifest.json") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--per-denomination", type=int, default=100)
    args = parser.parse_args()
    manifest = generate_batch(
        args.output_dir, {amount: args.per_denomination for amount in DENOMINATIONS}
    )
    print(
        f"已生成 {manifest['total_codes']} 张草稿卡密，"
        f"面值合计 ¥{manifest['total_face_value_cny']}；"
        f"尚未导入或激活。目录：{args.output_dir}"
    )
