"""供应商配置测试（M4 扩展）：CRUD、密钥加密、连通性预检、默认切换。"""

from fastapi.testclient import TestClient

from conftest import run_async
from deaiify.services import secrets as crypto


def _create(client: TestClient, **overrides) -> dict:
    body = {
        "name": "我的 DeepSeek",
        "kind": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-1234567890abcdef",
        "default_model": "deepseek-chat",
    }
    body.update(overrides)
    resp = client.post("/api/v1/providers", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_presets_listed(db_client: TestClient) -> None:
    resp = db_client.get("/api/v1/providers/presets")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    # 截图里那类常见供应商应齐备
    assert {"openai", "deepseek", "zhipu", "moonshot", "minimax", "dashscope", "ollama"} <= ids
    deepseek = next(p for p in resp.json() if p["id"] == "deepseek")
    assert deepseek["base_url"] == "https://api.deepseek.com/v1"
    assert deepseek["needs_key"] is True


def test_create_never_returns_plain_key(db_client: TestClient) -> None:
    created = _create(db_client)
    assert created["has_key"] is True
    # 明文 key 绝不出现在响应里
    assert "1234567890abcdef" not in str(created)
    assert created["key_mask"].startswith("sk-1")
    assert "*" in created["key_mask"]


def test_key_is_encrypted_at_rest(db_client: TestClient) -> None:
    _create(db_client)
    from sqlalchemy import select

    from deaiify.db.models import ProviderConfig
    from deaiify.db.session import get_session_factory

    async def fetch():
        async with get_session_factory()() as s:
            return (await s.scalars(select(ProviderConfig))).first()

    row = run_async(fetch())
    assert row is not None
    assert row.api_key_enc is not None
    assert row.api_key_enc.startswith("v2:"), "落库应为 Fernet 密文"
    assert "sk-1234567890abcdef" not in row.api_key_enc
    # 解密可还原（服务端自用）
    assert crypto.decrypt(row.api_key_enc) == "sk-1234567890abcdef"


def test_update_and_clear_key(db_client: TestClient) -> None:
    cfg = _create(db_client)
    cid = cfg["id"]

    resp = db_client.patch(f"/api/v1/providers/{cid}", json={"name": "改名后"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "改名后"
    assert resp.json()["has_key"] is True  # 不传 api_key 时保持

    # 传空串 → 清除 key
    resp = db_client.patch(f"/api/v1/providers/{cid}", json={"api_key": ""})
    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    assert resp.json()["key_mask"] == ""


def test_default_is_exclusive(db_client: TestClient) -> None:
    a = _create(db_client, name="A")
    b = _create(db_client, name="B")
    resp = db_client.post(f"/api/v1/providers/{a['id']}/default")
    assert resp.status_code == 200
    resp = db_client.post(f"/api/v1/providers/{b['id']}/default")
    assert resp.status_code == 200

    rows = db_client.get("/api/v1/providers").json()
    defaults = [r for r in rows if r["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == b["id"]


def test_delete(db_client: TestClient) -> None:
    cfg = _create(db_client)
    assert db_client.delete(f"/api/v1/providers/{cfg['id']}").status_code == 204
    assert db_client.get("/api/v1/providers").json() == []


def test_invalid_kind_rejected(db_client: TestClient) -> None:
    resp = db_client.post("/api/v1/providers", json={"name": "x", "kind": "nope"})
    assert resp.status_code == 422  # Literal 校验


def test_not_found(db_client: TestClient) -> None:
    assert db_client.get("/api/v1/providers/nope").status_code == 404
    assert db_client.post("/api/v1/providers/nope/default").status_code == 404
    assert db_client.delete("/api/v1/providers/nope").status_code == 404


def test_presave_connectivity_probe(db_client: TestClient) -> None:
    """预检端点必须返回结构化结果（不因上游不可达而 500）。"""
    resp = db_client.post(
        "/api/v1/providers/test",
        json={"kind": "ollama", "base_url": "http://127.0.0.1:11434"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "ok" in body and "models" in body and "error" in body


def test_secrets_roundtrip() -> None:
    plain = "sk-test-key-abcdefgh"
    token = crypto.encrypt(plain)
    assert token.startswith("v2:"), "新密文应为 Fernet（v2）格式"
    assert crypto.decrypt(token) == plain
    # Fernet 带随机 IV：同一明文两次结果必然不同
    assert crypto.encrypt(plain) != token
    assert crypto.decrypt("") == ""
    assert crypto.decrypt("garbage") == ""


def test_secret_not_plaintext_in_ciphertext() -> None:
    """密文里不得出现明文片段（基本防呆）。"""
    plain = "sk-super-secret-value-123456"
    token = crypto.encrypt(plain)
    assert plain not in token
    assert "super-secret" not in token


def test_fernet_detects_tampering() -> None:
    """Fernet 自带 HMAC：密文被篡改后解密必须失败（返回空串，不抛异常）。"""
    import base64 as b64

    token = crypto.encrypt("sk-tamper-me")
    raw = token[len("v2:") :]
    # 解码 → 翻转最后一个字节 → 重新编码
    data = bytearray(b64.urlsafe_b64decode(raw.encode("ascii")))
    data[-1] ^= 0xFF
    tampered = "v2:" + b64.urlsafe_b64encode(bytes(data)).decode("ascii")
    assert crypto.decrypt(tampered) == ""


def test_legacy_v1_decrypt_compat() -> None:
    """历史 v1 格式仍可解密（平滑迁移，不清空用户已有配置）。"""
    import base64 as b64
    import hashlib

    plain = "sk-legacy-key-999"
    master = crypto._master_secret()

    # 按 v1 算法手工构造一条密文
    salt = b"0123456789abcdef"
    nonce = b"fedcba9876543210"
    key = hashlib.pbkdf2_hmac("sha256", master, salt, crypto._V1_ITERATIONS, dklen=32)
    data = plain.encode("utf-8")
    stream = crypto._v1_keystream(key, nonce, len(data))
    cipher = bytes(a ^ b for a, b in zip(data, stream, strict=False))
    token = "v1:" + b64.urlsafe_b64encode(salt + nonce + cipher).decode("ascii")

    assert crypto.decrypt(token) == plain, "v1 历史密文必须仍能解密"


def test_bare_fernet_token_tolerated() -> None:
    """无前缀的裸 Fernet token 也能解（容错手工写入）。"""
    token = crypto.encrypt("sk-bare-token")
    bare = token[len("v2:") :]
    assert crypto.decrypt(bare) == "sk-bare-token"


def test_mask_helper() -> None:
    assert crypto.mask("sk-1234567890abcdef") == "sk-1***********cdef"  # 16 字符 → 中间 8 个星号
    assert crypto.mask("short") == "*****"
    assert crypto.mask("") == ""
