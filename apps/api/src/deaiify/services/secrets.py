"""API Key 落库加密（不引入 cryptography 重依赖）。

威胁模型（如实说明，docs 会同步）：防"顺手打开数据库看一眼就抄走 key"、
防备份文件泄露被直接读取；**不防**能拿到本机文件系统的攻击者
（密钥派生自 `DEAIIFY_SECRET_KEY` 或本机 .deaiify-secret 文件）。

实现：PBKDF2-HMAC-SHA256 派生 32 字节密钥 → HMAC-SHA256 计数器模式
生成密钥流 → 与明文 XOR → 拼接 nonce。这是标准的流密码构造，
但**不是**经过审计的密码学库，正式发行前应换成 cryptography.Fernet。
"""

import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path

_SECRET_FILE = Path(__file__).resolve().parents[5] / ".deaiify-secret"
_ITERATIONS = 120_000
_PREFIX = "v1:"


def _master_secret() -> bytes:
    """主密钥：优先环境变量，其次仓库根的 .deaiify-secret（首次自动生成）。"""
    env = os.getenv("DEAIIFY_SECRET_KEY")
    if env:
        return env.encode("utf-8")
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_bytes().strip()
    # 首次生成：32 字节随机数落盘（权限尽量收紧）
    secret = secrets.token_bytes(32)
    try:
        _SECRET_FILE.write_bytes(secret)
        if os.name == "posix":
            _SECRET_FILE.chmod(0o600)
    except OSError:
        # 不可写时退回进程内随机（重启后旧密文不可解，属可接受的降级）
        return secret
    return secret


def _derive(master: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", master, salt, _ITERATIONS, dklen=32)


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """HMAC-SHA256 计数器模式生成密钥流（每条消息独立 nonce）。"""
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt(plaintext: str) -> str:
    """明文 → `v1:<base64(salt|nonce|ciphertext)>`。"""
    if not plaintext:
        return ""
    master = _master_secret()
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    key = _derive(master, salt)
    data = plaintext.encode("utf-8")
    cipher = bytes(a ^ b for a, b in zip(data, _keystream(key, nonce, len(data)), strict=False))
    blob = base64.urlsafe_b64encode(salt + nonce + cipher).decode("ascii")
    return f"{_PREFIX}{blob}"


def decrypt(token: str) -> str:
    """密文 → 明文；格式不符或解不开时返回空串（视为未配置）。"""
    if not token or not token.startswith(_PREFIX):
        return ""
    try:
        raw = base64.urlsafe_b64decode(token[len(_PREFIX) :].encode("ascii"))
    except (ValueError, base64.binascii.Error):
        return ""
    if len(raw) < 32:
        return ""
    salt, nonce, cipher = raw[:16], raw[16:32], raw[32:]
    key = _derive(_master_secret(), salt)
    try:
        plain = bytes(
            a ^ b for a, b in zip(cipher, _keystream(key, nonce, len(cipher)), strict=False)
        )
        return plain.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return ""


def mask(plaintext: str) -> str:
    """脱敏展示：保留前 4 后 4，中间星号；过短则全星号。"""
    if not plaintext:
        return ""
    if len(plaintext) <= 8:
        return "*" * len(plaintext)
    return f"{plaintext[:4]}{'*' * (len(plaintext) - 8)}{plaintext[-4:]}"
