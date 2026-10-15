"""rewrite 端点契约：openai 路径经 httpx2.MockTransport 注入（docs §16 R11）。

覆盖成功、质量闸门（含重试）、超时/429/5xx 归一化、SSE 流式与流式重试。
上游错误的 respx 用例见 test_api_rewrite_respx.py（覆盖 httpx 系的 Ollama 路径）。
"""

import json as jsonlib

import httpx2
import pytest
from fastapi.testclient import TestClient

from deaiify.config import get_settings
from deaiify.main import create_app
from deaiify.providers import registry
from deaiify.providers.openai_provider import OpenAIProvider

ORIGINAL = (
    "2024年，我们公司的营收增长了35%，这具有重要意义。"
    "总而言之，我们需要进行深入分析，不断提升运营效率，从而实现可持续发展。"
)
GOOD_REWRITE = (
    "2024 年公司营收涨了 35%，这是实打实的成绩。"
    "说白了，钱是真赚到了。接下来要盯的是复购率，明年接着冲。"
)
BAD_REWRITE = "这家公司营收涨了不少，成绩相当亮眼。说白了，钱赚到了，接下来要继续努力。"


def _completion(content: str, model: str = "gpt-test") -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180},
    }


def ok(content: str) -> httpx2.Response:
    return httpx2.Response(200, json=_completion(content))


def status(code: int) -> httpx2.Response:
    return httpx2.Response(code, json={"error": {"message": "upstream", "type": "mock"}})


def sse(*deltas: str) -> httpx2.Response:
    parts = []
    for d in deltas:
        chunk = {"choices": [{"index": 0, "delta": {"content": d}, "finish_reason": None}]}
        parts.append(f"data: {jsonlib.dumps(chunk, ensure_ascii=False)}\n\n")
    stop = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
    parts.append(f"data: {jsonlib.dumps(stop)}\n\n")
    parts.append("data: [DONE]\n\n")
    return httpx2.Response(
        200,
        content="".join(parts).encode(),
        headers={"content-type": "text/event-stream"},
    )


class MockUpstream:
    """按调用序返回响应/抛异常；最后一步重复（供重试场景）。"""

    def __init__(self, *steps: object) -> None:
        self.steps = steps
        self.calls = 0

    def handler(self, _request: httpx2.Request) -> httpx2.Response:
        step = self.steps[min(self.calls, len(self.steps) - 1)]
        self.calls += 1
        if isinstance(step, BaseException):
            raise step
        assert isinstance(step, httpx2.Response)
        return step


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                payload = line[5:].strip()
                if payload != "[DONE]":
                    data = jsonlib.loads(payload)
        if event:
            events.append((event, data or {}))
    return events


@pytest.fixture()
def openai_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEAIIFY_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DEAIIFY_REWRITE_TIMEOUT_S", "8")
    get_settings.cache_clear()
    registry._INSTANCES.clear()

    def install(*steps: object) -> MockUpstream:
        """注入带 MockTransport 的 openai provider，返回其上游替身。"""
        upstream = MockUpstream(*steps)
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(upstream.handler))
        provider = OpenAIProvider(get_settings(), http_client=client)
        registry.install_instance(provider)
        return upstream

    yield TestClient(create_app()), install

    monkeypatch.delenv("DEAIIFY_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEAIIFY_REWRITE_TIMEOUT_S", raising=False)
    get_settings.cache_clear()
    registry._INSTANCES.clear()


def _payload(**overrides) -> dict:
    body = {
        "text": ORIGINAL,
        "styles": ["natural"],
        "model": {"provider": "openai", "name": "gpt-test"},
    }
    body.update(overrides)
    return body


def test_rewrite_success_passes_gate(openai_env) -> None:
    client, install = openai_env
    upstream = install(ok(GOOD_REWRITE))
    resp = client.post("/api/v1/rewrite", json=_payload())
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    v = payload["versions"][0]
    assert v["gate"] == "pass"
    assert v["delta"] <= -10
    assert v["score_before"] > v["score_after"]
    assert v["model"] == "gpt-test"
    assert v["attempts"] == 1
    assert v["usage"]["prompt_tokens"] == 100
    assert payload["engine_version"]
    assert upstream.calls == 1


def test_rewrite_gate_retries_then_fails(openai_env) -> None:
    """劣质改写（丢事实锚点）→ 自动重试 1 次 → 仍失败标记 fail（docs §6.3）。"""
    client, install = openai_env
    upstream = install(ok(BAD_REWRITE))
    resp = client.post("/api/v1/rewrite", json=_payload())
    assert resp.status_code == 200
    v = resp.json()["versions"][0]
    assert v["gate"] == "fail"
    assert v["attempts"] == 2
    assert "锚点" in (v["gate_reason"] or "")
    assert upstream.calls == 2


def test_rewrite_gate_retry_recovers(openai_env) -> None:
    """首次劣质、重试合格 → pass。"""
    client, install = openai_env
    upstream = install(ok(BAD_REWRITE), ok(GOOD_REWRITE))
    resp = client.post("/api/v1/rewrite", json=_payload())
    v = resp.json()["versions"][0]
    assert v["gate"] == "pass"
    assert v["attempts"] == 2
    assert upstream.calls == 2


def test_rewrite_timeout_maps_to_504(openai_env) -> None:
    client, install = openai_env
    upstream = install(httpx2.ConnectTimeout("boom"))
    resp = client.post("/api/v1/rewrite", json=_payload())
    assert resp.status_code == 504
    assert resp.json()["error"]["code"] == "provider_timeout"
    assert upstream.calls == 3  # 初始 1 + 重试 2（docs §6.4）


def test_rewrite_upstream_429_maps_to_429(openai_env) -> None:
    client, install = openai_env
    upstream = install(status(429))
    resp = client.post("/api/v1/rewrite", json=_payload())
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"
    assert upstream.calls == 3


def test_rewrite_upstream_500_maps_to_502(openai_env) -> None:
    client, install = openai_env
    upstream = install(status(500))
    resp = client.post("/api/v1/rewrite", json=_payload())
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "provider_error"
    assert upstream.calls == 3


def test_rewrite_stream_event_sequence(openai_env) -> None:
    client, install = openai_env
    install(
        sse(
            "2024 年公司营收涨了 35%，",
            "这是实打实的成绩。说白了，钱是真赚到了。",
            "接下来要盯的是复购率，明年接着冲。",
        )
    )
    with client.stream("POST", "/api/v1/rewrite/stream", json=_payload()) as resp:
        assert resp.status_code == 200
        raw = "".join(resp.iter_text())
    events = _parse_sse(raw)
    names = [e for e, _ in events]
    assert names[0] == "start"
    assert names[-1] == "done"
    assert "delta" in names
    version = next(d for e, d in events if e == "version")
    score = next(d for e, d in events if e == "score")
    assert version["gate"] == "pass"
    assert score["delta"] <= -10
    assert "retry" not in names


def test_rewrite_stream_retries_failed_gate(openai_env) -> None:
    """流式路径同样走闸门重试：劣质 → retry 事件（客户端重置缓冲）→ 合格。"""
    client, install = openai_env
    upstream = install(sse(BAD_REWRITE), sse(GOOD_REWRITE))
    with client.stream("POST", "/api/v1/rewrite/stream", json=_payload()) as resp:
        raw = "".join(resp.iter_text())
    events = _parse_sse(raw)
    names = [e for e, _ in events]
    assert "retry" in names
    versions = [d for e, d in events if e == "version"]
    assert len(versions) == 1
    assert versions[0]["gate"] == "pass"
    assert versions[0]["attempts"] == 2
    assert upstream.calls == 2


def test_rewrite_unconfigured_provider_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEAIIFY_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    registry._INSTANCES.clear()
    with TestClient(create_app()) as c:
        resp = c.post("/api/v1/rewrite", json=_payload())
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "model_unavailable"


def test_rewrite_invalid_style_400(openai_env) -> None:
    client, _install = openai_env
    resp = client.post("/api/v1/rewrite", json=_payload(styles=["klingon"]))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_style"


def test_gate_unit_anchors_and_ratio() -> None:
    from deaiify.services.rewrite import evaluate_gate, extract_anchors

    assert {"2024", "35"} <= extract_anchors(ORIGINAL)
    verdict = evaluate_gate(ORIGINAL, BAD_REWRITE, score_before=80)
    assert verdict.status == "fail"
    assert verdict.reason and "锚点" in verdict.reason
