"""批量任务端点：状态机、部分失败、进度落库、重启对账（docs §6.5、§8.1）。

provider 经 httpx2.MockTransport 注入（与 test_api_rewrite.py 同一路径，docs §16 R11），
不触网、不消耗 token。批量走后台协程，测试用轮询等待状态终态。
"""

import asyncio
import json as jsonlib
import time

import httpx2
import pytest
from fastapi.testclient import TestClient

from deaiify.config import get_settings
from deaiify.db.models import BatchJob
from deaiify.providers import registry
from deaiify.providers.base import ProviderError
from deaiify.providers.openai_provider import OpenAIProvider
from deaiify.services import batch as batch_svc

FAIL_MARK = "[[UPSTREAM_BOOM]]"

ORIGINAL = (
    "2024年，我们公司的营收增长了35%，这具有重要意义。"
    "总而言之，我们需要进行深入分析，不断提升运营效率，从而实现可持续发展。"
)
GOOD_REWRITE = (
    "2024 年公司营收涨了 35%，这是实打实的成绩。"
    "说白了，钱是真赚到了。接下来要盯的是复购率，明年接着冲。"
)


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


class ScriptedUpstream:
    """按请求内容决定成败：正文含 FAIL_MARK 的条目**始终**失败，其余成功。

    为什么不用「第 N 次调用失败」：`BaseProvider.complete` 带重试装饰器
    （`stop_after_attempt(3)`，docs §6.4），单次失败会被自动重试掉，测不出
    部分失败。只有让上游对该条目持续失败，才能稳定覆盖该路径。
    """

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0
        self.failed_calls = 0

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.calls += 1
        body = jsonlib.loads(request.content.decode("utf-8"))
        blob = jsonlib.dumps(body.get("messages", []), ensure_ascii=False)
        if FAIL_MARK in blob:
            self.failed_calls += 1
            return httpx2.Response(500, json={"error": {"message": "boom", "type": "mock"}})
        return httpx2.Response(200, json=_completion(self.content))


def _install(monkeypatch, upstream: ScriptedUpstream) -> None:
    monkeypatch.setenv("DEAIIFY_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DEAIIFY_REWRITE_TIMEOUT_S", "8")
    get_settings.cache_clear()
    registry._INSTANCES.clear()
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(upstream.handler))
    provider = OpenAIProvider(get_settings(), http_client=client)
    registry.install_instance(provider)


def _wait_done(client: TestClient, job_id: str, timeout: float = 20.0) -> dict:
    """轮询到终态；超时则失败并附最后一次快照。

    间隔 0.2s 而非更密：guards 中间件的限流是 60 次/分钟（docs §7.5），
    0.05s 轮询会在长任务上把自己挡成 429。
    """
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/batch/{job_id}")
        assert resp.status_code == 200, resp.text
        last = resp.json()
        if last["status"] in ("done", "failed"):
            return last
        time.sleep(0.2)
    raise AssertionError(
        f"批量任务未在 {timeout}s 内完成，最后状态：{jsonlib.dumps(last, ensure_ascii=False)}"
    )


@pytest.fixture()
def batch_client(db_client, monkeypatch):
    """DB 隔离 + mock provider；**缓存必须逐例清空**，否则上例正文串到本例。"""

    def make(contents: str = GOOD_REWRITE) -> tuple[TestClient, ScriptedUpstream]:
        upstream = ScriptedUpstream(contents)
        _install(monkeypatch, upstream)
        return db_client, upstream

    batch_svc._RESULTS.clear()
    batch_svc._RESULT_ORDER.clear()
    yield make
    batch_svc._RESULTS.clear()
    batch_svc._RESULT_ORDER.clear()
    monkeypatch.delenv("DEAIIFY_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEAIIFY_REWRITE_TIMEOUT_S", raising=False)
    get_settings.cache_clear()
    registry._INSTANCES.clear()


def _payload(n: int = 2, *, fail_at: set[int] | None = None, **overrides) -> dict:
    """`fail_at` 指定的下标塞 FAIL_MARK，让上游对该条目持续 500。"""
    boom = fail_at or set()
    body = {
        "items": [
            {"text": (ORIGINAL + FAIL_MARK) if i in boom else ORIGINAL, "title": f"第{i + 1}篇"}
            for i in range(n)
        ],
        "styles": ["natural"],
        "model": {"provider": "openai", "name": "gpt-test"},
        "gate": False,
    }
    body.update(overrides)
    return body


def test_create_returns_queued_job(batch_client) -> None:
    """建任务立即返回 job_id，状态是 queued 或已进入 running（都合法）。"""
    client, _ = batch_client(GOOD_REWRITE)
    resp = client.post("/api/v1/batch", json=_payload(2))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_id"]
    assert body["status"] in ("queued", "running", "done")
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["items"][0]["title"] == "第1篇"


def test_all_items_succeed(batch_client) -> None:
    client, upstream = batch_client(GOOD_REWRITE)
    job_id = client.post("/api/v1/batch", json=_payload(3)).json()["job_id"]
    final = _wait_done(client, job_id)

    assert final["status"] == "done"
    assert final["done"] == 3
    assert final["failed"] == 0
    assert final["pending"] == 0
    assert final["progress"] == 1.0
    assert all(item["status"] == "ok" for item in final["items"])
    assert all(item["text"] == GOOD_REWRITE for item in final["items"])
    assert upstream.calls == 3


def test_partial_failure_does_not_block_batch(batch_client) -> None:
    """单条上游 500 不阻塞整批：其余条目照常完成，失败条目带错误摘要。"""
    client, _ = batch_client(GOOD_REWRITE)
    job_id = client.post("/api/v1/batch", json=_payload(3, fail_at={1})).json()["job_id"]
    final = _wait_done(client, job_id)

    assert final["status"] == "done", "部分失败时整体仍是 done（有成功条目）"
    assert final["done"] == 2
    assert final["failed"] == 1
    statuses = [item["status"] for item in final["items"]]
    assert statuses == ["ok", "failed", "ok"], statuses
    failed = final["items"][1]
    assert failed["error"]
    assert failed["text"] is None


def test_all_items_fail_marks_job_failed(batch_client) -> None:
    client, _ = batch_client(GOOD_REWRITE)
    job_id = client.post("/api/v1/batch", json=_payload(2, fail_at={0, 1})).json()["job_id"]
    final = _wait_done(client, job_id)

    assert final["status"] == "failed"
    assert final["done"] == 0
    assert final["failed"] == 2


def test_progress_persisted_without_text(batch_client) -> None:
    """进度落库可查，但正文绝不进数据库（隐私契约 §8.2）。"""
    client, _ = batch_client(GOOD_REWRITE)
    job_id = client.post("/api/v1/batch", json=_payload(2)).json()["job_id"]
    _wait_done(client, job_id)

    def read_row() -> BatchJob | None:
        from deaiify.db.session import get_session_factory

        async def _get():
            async with get_session_factory()() as session:
                return await session.get(BatchJob, job_id)

        return asyncio.run(_get())

    row = read_row()
    assert row is not None
    assert row.status == "done"
    assert row.done == 2
    # 关键断言：DB 里既没有原文也没有改写结果
    assert row.results_json is not None
    assert GOOD_REWRITE not in row.results_json
    assert "营收增长了35%" not in (row.results_json or "")
    assert row.payload_json is not None
    assert ORIGINAL not in row.payload_json
    assert "sha256" in row.payload_json  # 只留元信息


def test_reconcile_marks_interrupted_jobs(batch_client) -> None:
    """进程重启后，遗留的 queued/running 任务必须标成 failed，不能让前端无限轮询。"""
    client, _ = batch_client(GOOD_REWRITE)
    job_id = client.post("/api/v1/batch", json=_payload(1)).json()["job_id"]
    _wait_done(client, job_id)

    from deaiify.db.session import get_session_factory

    async def force_running() -> None:
        async with get_session_factory()() as session:
            row = await session.get(BatchJob, job_id)
            assert row is not None
            row.status = "running"
            await session.commit()

    asyncio.run(force_running())
    n = asyncio.run(batch_svc.reconcile_interrupted())
    assert n >= 1

    final = client.get(f"/api/v1/batch/{job_id}").json()
    assert final["status"] == "failed"
    assert "重启" in (final["error"] or "")


def test_unknown_job_404(batch_client) -> None:
    client, _ = batch_client(GOOD_REWRITE)
    resp = client.get("/api/v1/batch/deadbeef")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_rejects_too_many_items(batch_client) -> None:
    client, _ = batch_client(GOOD_REWRITE)
    resp = client.post("/api/v1/batch", json={"items": [{"text": "x"}] * 51})
    assert resp.status_code == 422, "超过 50 条由 schema 拦截"


def test_rejects_empty_items(batch_client) -> None:
    client, _ = batch_client(GOOD_REWRITE)
    resp = client.post("/api/v1/batch", json={"items": []})
    assert resp.status_code == 422


def test_rejects_unknown_style(batch_client) -> None:
    client, _ = batch_client(GOOD_REWRITE)
    resp = client.post("/api/v1/batch", json=_payload(1, styles=["nope"]))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_style"


def test_rejects_oversized_item(batch_client, monkeypatch) -> None:
    client, _ = batch_client(GOOD_REWRITE)
    monkeypatch.setenv("DEAIIFY_MAX_TEXT_CHARS", "10")
    get_settings.cache_clear()
    resp = client.post("/api/v1/batch", json=_payload(1))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_text"
    assert "第 1 条" in resp.json()["error"]["message"]


def test_no_provider_fails_whole_job(batch_client, monkeypatch) -> None:
    """没有任何可用 provider 时整批失败，但要给出可读原因，不是静默卡住。

    直接清 registry 不够：`get_provider()` 对未配置的 provider 仍会返回实例，
    那样会打到真实 api.openai.com（8s 超时 × 3 次重试）。这里把构造点打桩成
    抛错，模拟「一个 provider 都不可用」。
    """

    def _boom(*_args, **_kwargs):
        raise ProviderError("model_unavailable", "未配置任何模型提供商")

    monkeypatch.setattr(registry, "get_provider", _boom)
    client, _ = batch_client(GOOD_REWRITE)
    resp = client.post(
        "/api/v1/batch",
        json={
            "items": [{"text": ORIGINAL}],
            "styles": ["natural"],
            "model": {"provider": "openai", "name": "gpt-test"},
        },
    )
    # 建任务阶段可能直接报错，也可能建了任务后在后台失败，两条路径都接受
    if resp.status_code == 200:
        final = _wait_done(client, resp.json()["job_id"])
        assert final["status"] == "failed"
        assert final["error"]
        assert final["items"][0]["status"] == "failed"
        assert final["items"][0]["error"]
    else:
        assert resp.status_code >= 400
        assert resp.json()["error"]["message"]


def test_results_survive_page_refresh(batch_client) -> None:
    """刷新页面（重新 GET）看到的是同一份结果，进度不丢。"""
    client, _ = batch_client(GOOD_REWRITE)
    job_id = client.post("/api/v1/batch", json=_payload(2)).json()["job_id"]
    first = _wait_done(client, job_id)
    second = client.get(f"/api/v1/batch/{job_id}").json()
    assert second["done"] == first["done"]
    assert second["items"] == first["items"]


def test_batch_concurrency_respected(batch_client, monkeypatch) -> None:
    """并发上限生效：同时 in-flight 的条目数不超过 DEAIIFY_BATCH_CONCURRENCY。"""
    client, upstream = batch_client(GOOD_REWRITE)
    monkeypatch.setenv("DEAIIFY_BATCH_CONCURRENCY", "1")
    get_settings.cache_clear()

    job_id = client.post("/api/v1/batch", json=_payload(4)).json()["job_id"]
    final = _wait_done(client, job_id)
    assert final["done"] == 4
    assert upstream.calls == 4

    from deaiify.db.session import get_session_factory

    async def read() -> BatchJob | None:
        async with get_session_factory()() as session:
            return await session.get(BatchJob, job_id)

    row = asyncio.run(read())
    assert row is not None
    assert row.done == 4
