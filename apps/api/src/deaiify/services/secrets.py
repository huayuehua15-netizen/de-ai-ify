"""API Key 落库加密（cryptography.Fernet）。

## 保护什么

`/settings` 页填入的模型供应商 API Key（DeepSeek / 智谱 / Kimi 等），
存进数据库时加密，避免明文躺在 `data/deaiify.db` 或备份里。

## 威胁模型（如实说明）

防：打开数据库顺手抄走 key、备份文件泄露、误把数据库提交进 git。
**不防**：能读取本机文件系统的攻击者——主密钥就在本机
（`.deaiify-secret` 文件或 `DEAIIFY_SECRET_KEY` 环境变量），
这是自托管单机应用的固有边界，换任何加密库都改变不了。

## 实现

Fernet（AES-128-CBC + HMAC-SHA256，带时间戳与认证），
Python 生态事实标准，经广泛审计，API 不易用错。

## 格式与兼容

- `v2:` 前缀 = Fernet 密文（当前实现）
- `v1:` 前缀 = 历史实现（标准库 PBKDF2 + HMAC 流密码），**只读兼容**
  ——2026-11 之前的数据库里可能有，读到则走旧路径解密；
  下次保存该条记录时会自动升级为 `v2:`。
- 无前缀/无法解密 → 返回空串（视为未配置，不抛异常，避免一条坏数据
  让整个供应商列表 500）
"""

import base64
import hashlib
import hmac
import os
import secrets as pysecrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_SECRET_FILE = Path(__file__).resolve().parents[5] / ".deaiify-secret"

_V2_PREFIX = "v2:"
_V1_PREFIX = "v1:"

# —— v1 历史实现常量（仅解密用）——
_V1_ITERATIONS = 120_000


# ============================================================
# 主密钥
# ============================================================


def _master_secret() -> bytes:
    """主密钥：优先环境变量，其次仓库根的 .deaiify-secret（首次自动生成）。"""
    env = os.getenv("DEAIIFY_SECRET_KEY")
    if env:
        return env.encode("utf-8")
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_bytes().strip()
    secret = pysecrets.token_bytes(32)
    try:
        _SECRET_FILE.write_bytes(secret)
        if os.name == "posix":
            _SECRET_FILE.chmod(0o600)
    except OSError:
        # 不可写时退回进程内随机（重启后旧密文不可解，属可接受的降级）
        return secret
    return secret


def _fernet() -> Fernet:
    """由主密钥派生 Fernet 密钥（base64url(32 字节)）。

    用 HKDF 风格的简单派生（HMAC 域分离）把任意长度的主密钥
    规整成 Fernet 要求的 32 字节，避免直接截断/填充带来的弱化。
    """
    master = _master_secret()
    derived = hmac.new(master, b"deaiify/fernet/v2", hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


# ============================================================
# v2（当前）：Fernet
# ============================================================


def encrypt(plaintext: str) -> str:
    """明文 → `v2:<fernet token>`。空串返回空串。"""
    if not plaintext:
        return ""
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_V2_PREFIX}{token}"


def decrypt(token: str) -> str:
    """密文 → 明文；支持 v2（Fernet）与 v1（历史格式）双读。

    任何解析/解密失败都返回空串而非抛异常——一条损坏的记录
    不应让供应商列表整体 500。
    """
    if not token:
        return ""
    if token.startswith(_V2_PREFIX):
        return _decrypt_v2(token[len(_V2_PREFIX) :])
    if token.startswith(_V1_PREFIX):
        return _decrypt_v1(token)
    # 无前缀：尝试当 v2 裸 token 解（容错手工写入的情况）
    return _decrypt_v2(token)


def _decrypt_v2(raw: str) -> str:
    try:
        return _fernet().decrypt(raw.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return ""


# ============================================================
# v1（历史）：PBKDF2 + HMAC 计数器模式流密码，仅保留解密能力
# ============================================================


def _v1_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _decrypt_v1(token: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(token[len(_V1_PREFIX) :].encode("ascii"))
    except (ValueError, base64.binascii.Error):
        return ""
    if len(raw) < 32:
        return ""
    salt, nonce, cipher = raw[:16], raw[16:32], raw[32:]
    try:
        key = hashlib.pbkdf2_hmac("sha256", _master_secret(), salt, _V1_ITERATIONS, dklen=32)
        plain = bytes(
            a ^ b for a, b in zip(cipher, _v1_keystream(key, nonce, len(cipher)), strict=False)
        )
        return plain.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return ""


# ============================================================
# 展示用脱敏
# ============================================================


def mask(plaintext: str) -> str:
    """脱敏展示：保留前 4 后 4，中间星号；过短则全星号。"""
    if not plaintext:
        return ""
    if len(plaintext) <= 8:
        return "*" * len(plaintext)
    return f"{plaintext[:4]}{'*' * (len(plaintext) - 8)}{plaintext[-4:]}"
