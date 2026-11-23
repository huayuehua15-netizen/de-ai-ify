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
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _secret_file() -> Path:
    """主密钥文件位置：优先 DEAIIFY_SECRET_FILE，否则在"项目根"下找。

    不能写死 `parents[N]` —— 源码树（apps/api/src/deaiify/services）与
    容器镜像（/app/src/deaiify/services）的层级深度不同，写死会在其中
    一种环境里抛 IndexError（实测踩过）。
    这里从当前文件向上找，取第一个含 pyproject.toml 或 .git 的目录。
    """
    env_path = os.getenv("DEAIIFY_SECRET_FILE")
    if env_path:
        return Path(env_path).expanduser()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent / ".deaiify-secret"
    # 兜底：容器内工作目录
    return Path.cwd() / ".deaiify-secret"


_SECRET_FILE = _secret_file()


def _fallback_files() -> list[Path]:
    """主路径不可写时的备选落点。

    典型场景：容器里代码目录归 root、进程以非 root 运行（`/app` 只读），
    此时"项目根"写不进去，但 `./data`（compose 挂的卷）、家目录、临时目录
    通常可写。**必须有一个能真正落盘的落点**——否则重启后已存的 API Key
    全部解不开（实测踩过，见 docs §14.2）。
    """
    candidates = [Path.cwd() / "data", Path.home()]
    if os.name == "posix":
        candidates.append(Path("/tmp"))
    elif os.getenv("TEMP"):
        candidates.append(Path(os.environ["TEMP"]))
    return [base / ".deaiify-secret" for base in candidates]


# 进程内缓存：写盘失败时也必须稳定，否则同进程里 encrypt 之后立刻 decrypt 都会失败
_cached_secret: bytes | None = None
_warned_not_persistent = False

_V2_PREFIX = "v2:"
_V1_PREFIX = "v1:"

# —— v1 历史实现常量（仅解密用）——
_V1_ITERATIONS = 120_000


# ============================================================
# 主密钥
# ============================================================


def _read_secret(path: Path) -> bytes | None:
    """读主密钥文件；不存在或内容过短视为无效。

    两种格式都认：
    - 新格式：64 个十六进制字符（本函数 `_write_secret` 写的）
    - 旧格式：32 字节原始二进制（早期版本写的，读到继续用）

    新格式写成十六进制是为了绕开「二进制密钥末尾恰好是 0x0a / 0x20，
    被 `.strip()` 吃掉」这一类静默错位——实测在测试里真的踩到过。
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    text = data.strip()
    if len(text) == 64 and all(c in b"0123456789abcdef" for c in text):
        try:
            return bytes.fromhex(text.decode("ascii"))
        except ValueError:
            return None
    return text if len(text) >= 16 else None


def _write_secret(path: Path, secret: bytes) -> bool:
    """原子写入主密钥（先写临时文件再替换，避免并发读到半截文件）。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(secret.hex().encode("ascii"))
        if os.name == "posix":
            tmp.chmod(0o600)
        tmp.replace(path)
        return True
    except OSError:
        return False


def _master_secret() -> bytes:
    """主密钥：优先环境变量，其次落盘文件（首次自动生成）。

    三级回退，且**进程内缓存在最外层**：

    1. `DEAIIFY_SECRET_KEY` 环境变量（生产推荐：显式给定，换机器也能解）
    2. 主路径 `_SECRET_FILE`（源码树/仓库根，本地开发就是这样）
    3. 备选路径 `_fallback_files()`（容器里 `/app` 只读时落到 `/app/data`）

    三者都不行时用进程内随机密钥——但此时**同进程内一致、重启即失效**，
    并且会在 stderr 打一次告警，绝不静默。此前"每次都取新随机密钥"的
    写法会让刚保存的 API Key 立刻解不开（`has_key: false`），已在
    docs §14.2 记录为真实 bug。
    """
    global _cached_secret, _warned_not_persistent

    env = os.getenv("DEAIIFY_SECRET_KEY")
    if env:
        return env.encode("utf-8")

    if _cached_secret is not None:
        return _cached_secret

    existing = _read_secret(_SECRET_FILE)
    if existing is not None:
        _cached_secret = existing
        return _cached_secret

    secret = pysecrets.token_bytes(32)

    for path in [_SECRET_FILE, *_fallback_files()]:
        if _write_secret(path, secret):
            _cached_secret = secret
            if path != _SECRET_FILE and not _warned_not_persistent:
                _warned_not_persistent = True
                print(
                    f"[deaiify] 主密钥无法写入 {_SECRET_FILE}（目录不可写），"
                    f"已改存 {path}。建议设 DEAIIFY_SECRET_FILE 指向可持久化目录。",
                    file=sys.stderr,
                )
            return _cached_secret

    # 全都不行：至少保证进程内稳定，否则一次请求内都解不开同一个 key
    _cached_secret = secret
    if not _warned_not_persistent:
        _warned_not_persistent = True
        print(
            "[deaiify] 主密钥无处可写，已退回进程内随机值：重启后已保存的"
            "供应商 API Key 将全部失效。请设置 DEAIIFY_SECRET_KEY 或 "
            "DEAIIFY_SECRET_FILE。",
            file=sys.stderr,
        )
    return _cached_secret


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
