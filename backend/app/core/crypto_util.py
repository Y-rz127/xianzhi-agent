"""用户敏感配置的认证加密（仅标准库，encrypt-then-MAC）。

格式：``v1.<base64(nonce(16B) || ciphertext || HMAC-SHA256 tag)>``。
密钥来自 USER_LLM_KEY_SECRET，未配置时复用 ADMIN_SESSION_SECRET；两者都为空时拒绝
保存，绝不使用公开的内置弱密钥。更换密钥后旧配置需由用户重新填写。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets as _secrets

from app.core.config import settings

_BLOCK = 32
_NONCE_SIZE = 16
_TAG_SIZE = 32
_PREFIX = "v1."


class SecretDecryptError(ValueError):
    """密文无法解密（密钥更换、数据损坏或篡改）。"""


class SecretConfigError(RuntimeError):
    """服务端未配置敏感字段加密密钥。"""


def _secret() -> bytes:
    key = settings.user_llm_key_secret.strip() or settings.admin_session_secret.strip()
    if not key:
        raise SecretConfigError("服务端未配置 USER_LLM_KEY_SECRET，无法安全保存 API Key")
    return key.encode("utf-8")


def _keys() -> tuple[bytes, bytes]:
    master = _secret()
    enc_key = hmac.new(master, b"xianzhi-user-llm/encryption", hashlib.sha256).digest()
    mac_key = hmac.new(master, b"xianzhi-user-llm/authentication", hashlib.sha256).digest()
    return enc_key, mac_key


def encrypt_secret(plaintext: str) -> str:
    """加密并认证明文字符串；空串原样返回。"""
    if not plaintext:
        return ""
    enc_key, mac_key = _keys()
    data = plaintext.encode("utf-8")
    nonce = _secrets.token_bytes(_NONCE_SIZE)
    cipher = _xor_stream(data, nonce, enc_key)
    tag = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()
    return _PREFIX + base64.b64encode(nonce + cipher + tag).decode("ascii")


def decrypt_secret(token: str) -> str:
    """解密并校验密文；空串原样返回，格式/认证失败抛 SecretDecryptError。"""
    if not token:
        return ""
    try:
        if not token.startswith(_PREFIX):
            raise SecretDecryptError("旧版或未认证的密文需重新填写")
        raw = base64.b64decode(token[len(_PREFIX):].encode("ascii"), validate=True)
        if len(raw) <= _NONCE_SIZE + _TAG_SIZE:
            raise SecretDecryptError("密文过短")
        nonce = raw[:_NONCE_SIZE]
        cipher = raw[_NONCE_SIZE:-_TAG_SIZE]
        actual_tag = raw[-_TAG_SIZE:]
        _, mac_key = _keys()
        expected_tag = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(actual_tag, expected_tag):
            raise SecretDecryptError("密文认证失败")
        enc_key, _ = _keys()
        return _xor_stream(cipher, nonce, enc_key).decode("utf-8")
    except SecretDecryptError:
        raise
    except (ValueError, UnicodeDecodeError, base64.binascii.Error) as exc:
        raise SecretDecryptError("密文格式错误") from exc


def _xor_stream(data: bytes, nonce: bytes, key: bytes) -> bytes:
    blocks = (len(data) + _BLOCK - 1) // _BLOCK
    stream = bytearray()
    for i in range(blocks):
        stream += hmac.new(key, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest()
    return bytes(value ^ mask for value, mask in zip(data, stream))
