from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CreditSecurityConfigError(RuntimeError):
    pass


def _key() -> bytes:
    encoded = os.environ.get("WORKBENCH_REDEEM_ENCRYPTION_KEY", "").strip()
    try:
        key = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except Exception as exc:
        raise CreditSecurityConfigError("工作台卡密加密密钥未正确配置") from exc
    if len(key) != 32:
        raise CreditSecurityConfigError("工作台卡密加密密钥必须是 32 字节 Base64")
    return key


def normalize_card_code(code: str) -> str:
    normalized = "".join(str(code).split()).upper()
    if not 8 <= len(normalized) <= 128:
        raise ValueError("卡密格式无效")
    return normalized


def normalize_workbench_voucher_code(code: str) -> str:
    normalized = "".join(str(code).split()).upper()
    if not re.fullmatch(r"AGT1-(?:[0-9A-F]{8}-){3}[0-9A-F]{8}", normalized):
        raise ValueError("工作台卡密格式无效")
    return normalized


def workbench_voucher_digest(code: str) -> bytes:
    normalized = normalize_workbench_voucher_code(code)
    return hashlib.sha256(
        b"workbench-voucher-v1:" + normalized.encode("ascii")
    ).digest()


def card_code_digest(code: str) -> bytes:
    key = _key()
    digest_key = hmac.new(key, b"workbench-card-code-digest-v1", hashlib.sha256).digest()
    normalized = normalize_card_code(code)
    return hmac.new(digest_key, normalized.encode("utf-8"), hashlib.sha256).digest()


def encrypt_card_code(code: str) -> bytes:
    key = _key()
    nonce = secrets.token_bytes(12)
    normalized = normalize_card_code(code)
    ciphertext = AESGCM(key).encrypt(nonce, normalized.encode("utf-8"), b"workbench-card-v1")
    return nonce + ciphertext


def decrypt_card_code(ciphertext: bytes) -> str:
    key = _key()
    if len(ciphertext) < 29:
        raise ValueError("卡密密文格式无效")
    plaintext = AESGCM(key).decrypt(ciphertext[:12], ciphertext[12:], b"workbench-card-v1")
    return plaintext.decode("utf-8")
