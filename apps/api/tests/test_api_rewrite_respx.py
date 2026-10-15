"""上游错误归一化（respx 覆盖基于 httpx 的 Ollama 路径）。

M2 验收要求 respx 模拟超时/429/5xx：openai/anthropic SDK 已迁至 httpx2（respx 无法拦截，
见 docs §16 R11），故 respx 用例打在 httpx 系的 Ollama provider 上——错误归一化在
`BaseProvider.complete` 重试 + ProviderError 映射层是同一套代码。
"""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from deaiify.config import get_settings
from deaiify.main import create_app
from deaiify.providers import registry

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

ORIGINAL = (
    "2024年，我们公司的营收增长了35%，这具有重要意义。"
    "总而言之，我们需要进行深入分析，不断提升运营效率。"
)
GOOD_REWRITE = (
    "2024 年公司营收涨了 35%，这是实打实的成绩。"
    "说白了，钱是真赚到了。接下来要盯的是复购率，明年接着冲。"
)


def _payload(**overrides) -> dict:
    body = {
        "text": ORIGINAL,
        "styles": ["natural"],
        "model": {"provider": "ollama", "name": "qwen2.5:7b"},
    }
    body.update(overrides)
    return body


@pytest.fixture()
def ollama_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEAIIFY_REWRITE_TIMEOUT_S", "8")
    get_settings.cache_clear()
    registry._INSTANCES.clear()
    yield TestClient(create_app())
    monkeypatch.delenv("DEAIIFY_REWRITE_TIMEOUT_S", raising=False)
    get_settings.cache_clear()
    registry._INSTANCES.clear()


@respx.mock
def test_respx_ollama_timeout_to_504(ollama_env: TestClient) -> None:
    respx.post(OLLAMA_URL).mock(side_effect=httpx.ConnectTimeout("down"))
    resp = ollama_env.post("/api/v1/rewrite", json=_payload())
    assert resp.status_code == 504
    assert resp.json()["error"]["code"] == "provider_timeout"
    assert respx.calls.call_count == 3  # 初始 + 2 次重试


@respx.mock
def test_respx_ollama_429_to_429(ollama_env: TestClient) -> None:
    respx.post(OLLAMA_URL).mock(return_value=httpx.Response(429, json={"error": "rate"}))
    resp = ollama_env.post("/api/v1/rewrite", json=_payload())
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    assert respx.calls.call_count == 3


@respx.mock
def test_respx_ollama_500_to_502(ollama_env: TestClient) -> None:
    respx.post(OLLAMA_URL).mock(return_value=httpx.Response(500, json={"error": "boom"}))
    resp = ollama_env.post("/api/v1/rewrite", json=_payload())
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "provider_error"
    assert respx.calls.call_count == 3


@respx.mock
def test_respx_ollama_success(ollama_env: TestClient) -> None:
    respx.post(OLLAMA_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": GOOD_REWRITE},
                "prompt_eval_count": 120,
                "eval_count": 88,
            },
        )
    )
    resp = ollama_env.post("/api/v1/rewrite", json=_payload())
    assert resp.status_code == 200, resp.text
    v = resp.json()["versions"][0]
    assert v["gate"] == "pass"
    assert v["delta"] <= -10
    assert v["usage"]["completion_tokens"] == 88
    assert respx.calls.call_count == 1
