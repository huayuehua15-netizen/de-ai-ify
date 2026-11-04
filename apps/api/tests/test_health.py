"""健康端点测试：版本/存储/模型就绪状态（失败降级，不阻塞启动）。"""

import os

import pytest
from fastapi.testclient import TestClient

from deaiify.main import app


def test_health_shape() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "deaiify"
    assert data["version"]
    assert data["engine_version"]
    assert data["db"]["status"] in {"ok", "unavailable"}
    assert data["redis"]["status"] in {"ok", "unavailable", "skipped"}
    # 模型就绪状态（M4 扩展）
    providers = data["providers"]
    assert isinstance(providers["ready"], bool)
    assert providers["source"] in {"ui", "env", "none"}
    assert isinstance(providers["count"], int)
    assert "env_fallback" in providers
    # 运行时限制：前端据此显示字数提示，避免硬编码不同步
    limits = data["limits"]
    assert limits["max_text_chars"] == 20000
    assert isinstance(limits["batch_concurrency"], int)


def test_health_providers_none_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """没配任何模型时：ready=False、source=none（前端据此显示「API 已连接」）。"""
    monkeypatch.delenv("DEAIIFY_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEAIIFY_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEAIIFY_OLLAMA_BASE_URL", raising=False)
    from deaiify.config import get_settings

    get_settings.cache_clear()
    with TestClient(app) as client:
        data = client.get("/api/v1/health").json()
    assert data["providers"]["ready"] is False
    assert data["providers"]["source"] == "none"
    get_settings.cache_clear()


def test_health_providers_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """只配 .env 时：ready=True、source=env（无 UI 配置也能改写）。"""
    monkeypatch.setenv("DEAIIFY_OPENAI_API_KEY", "sk-env-test")
    from deaiify.config import get_settings

    get_settings.cache_clear()
    with TestClient(app) as client:
        data = client.get("/api/v1/health").json()
    assert data["providers"]["ready"] is True
    assert data["providers"]["source"] == "env"
    assert data["providers"]["env_fallback"] is True
    monkeypatch.delenv("DEAIIFY_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()


def test_health_providers_ui_config(db_client: TestClient) -> None:
    """UI 里配了供应商：ready=True、source=ui、带默认名。"""
    resp = db_client.post(
        "/api/v1/providers",
        json={
            "name": "健康检查用",
            "kind": "openai",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-x",
            "is_default": True,
        },
    )
    assert resp.status_code == 201
    data = db_client.get("/api/v1/health").json()
    assert data["providers"]["ready"] is True
    assert data["providers"]["source"] == "ui"
    assert data["providers"]["count"] == 1
    assert data["providers"]["default"] == "健康检查用"


@pytest.mark.skipif(
    os.getenv("DEAIIFY_EXPECT_SERVICES") != "1",
    reason="需要标准栈 PG + Redis（docs/DEVELOPMENT.md §3.3；CI api-int 或本机 compose）",
)
def test_health_standard_stack() -> None:
    with TestClient(app) as client:
        data = client.get("/api/v1/health").json()
    assert data["db"]["status"] == "ok"
    assert data["redis"]["status"] == "ok"
