"""用户模型凭据加密，密钥与数据库分离，AAD 绑定账号避免密文交换。"""
import base64
import json
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def cipher():
    try:
        raw = os.environ.get("USER_CONFIG_ENCRYPTION_KEY", "")
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        if len(key) != 32:
            raise ValueError()
        return AESGCM(key)
    except Exception:
        raise RuntimeError("云端模型配置加密尚未配置，请联系管理员。") from None


def encrypt_config(owner_id, config):
    nonce = secrets.token_bytes(12)
    body = json.dumps(config, ensure_ascii=False).encode()
    aad = ("user-model-config:v1:" + owner_id).encode()
    return base64.urlsafe_b64encode(nonce + cipher().encrypt(nonce, body, aad)).decode()


def decrypt_config(owner_id, value):
    try:
        raw = base64.urlsafe_b64decode(value)
        aad = ("user-model-config:v1:" + owner_id).encode()
        return json.loads(cipher().decrypt(raw[:12], raw[12:], aad))
    except Exception:
        raise RuntimeError("云端模型配置无法解密，请重新保存配置或联系管理员。") from None
