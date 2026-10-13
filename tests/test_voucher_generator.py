from __future__ import annotations

import csv
import stat

import pytest

from server.scripts.generate_workbench_vouchers import generate_batch, voucher_digest
from server.proposal.credit_security import workbench_voucher_digest


def test_offline_voucher_batch_is_unique_and_not_active(tmp_path):
    folder = tmp_path / "private"
    manifest = generate_batch(folder, {1: 2, 5: 1})
    with (folder / manifest["seller_csv"]).open(newline="") as stream:
        seller = list(csv.DictReader(stream))
    with (folder / manifest["hashes_csv"]).open(newline="") as stream:
        hashes = list(csv.DictReader(stream))

    assert manifest["total_codes"] == 3
    assert manifest["total_face_value_cny"] == 7
    assert manifest["total_credits_if_activated"] == 70
    assert len({row["code"] for row in seller}) == 3
    assert sorted(int(row["credits"]) for row in seller) == [10, 10, 50]
    assert [row["code_hash"] for row in hashes] == [
        voucher_digest(row["code"]) for row in seller
    ]
    assert [row["code_hash"] for row in hashes] == [
        workbench_voucher_digest(row["code"]).hex() for row in seller
    ]
    assert all(row["status"] == "draft" for row in hashes)
    assert all(row["code"] not in (folder / manifest["hashes_csv"]).read_text() for row in seller)
    assert stat.S_IMODE((folder / manifest["seller_csv"]).stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        generate_batch(folder, {1: 1})
