"""analyze 端点契约与守卫测试（无需任何模型凭据）。"""

import pytest
from fastapi.testclient import TestClient

from deaiify.config import get_settings
from deaiify.main import create_app


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def test_analyze_ok(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/analyze",
        json={"text": "综上所述，效率至关重要。首先提升效率，其次降低成本。"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert 0 <= data["score"] <= 100
    assert data["band"] in {"natural", "mild", "obvious", "heavy"}
    assert len(data["dimensions"]) == 8
    assert resp.headers.get("X-Request-ID")


def test_analyze_empty_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/analyze", json={"text": ""})
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "validation_error"
    assert "request_id" in body


def test_analyze_whitespace_is_400(client: TestClient) -> None:
    resp = client.post("/api/v1/analyze", json={"text": "   \n  "})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_text"


def test_analyze_too_long(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEAIIFY_MAX_TEXT_CHARS", "50")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        resp = c.post("/api/v1/analyze", json={"text": "这个文本明显超过了五十字上限。" * 5})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_text"
    monkeypatch.delenv("DEAIIFY_MAX_TEXT_CHARS", raising=False)
    get_settings.cache_clear()


def test_auth_required_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEAIIFY_API_KEY", "sekrit")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        assert c.post("/api/v1/analyze", json={"text": "短文本。"}).status_code == 401
        ok = c.post(
            "/api/v1/analyze",
            json={"text": "短文本。"},
            headers={"Authorization": "Bearer sekrit"},
        )
        assert ok.status_code == 200
        # health 不受鉴权影响
        assert c.get("/api/v1/health").status_code == 200
    monkeypatch.delenv("DEAIIFY_API_KEY", raising=False)
    get_settings.cache_clear()


def test_rate_limit_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEAIIFY_RATE_LIMIT_PER_MIN", "3")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as c:
        for _ in range(3):
            assert c.post("/api/v1/analyze", json={"text": "文本。"}).status_code == 200
        resp = c.post("/api/v1/analyze", json={"text": "文本。"})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    monkeypatch.delenv("DEAIIFY_RATE_LIMIT_PER_MIN", raising=False)
    get_settings.cache_clear()


def test_styles_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/styles")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.json()}
    assert ids == {"natural", "concise", "academic", "business", "social"}


def test_openapi_document(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    for p in (
        "/api/v1/analyze",
        "/api/v1/rewrite",
        "/api/v1/rewrite/stream",
        "/api/v1/models",
        "/api/v1/styles",
        "/api/v1/health",
    ):
        assert p in paths, f"缺少端点 {p}"
