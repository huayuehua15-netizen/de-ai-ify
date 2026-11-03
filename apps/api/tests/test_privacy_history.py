"""隐私存储测试（M4，docs §4.3、§8.2）：

- 默认 never：历史行落库但 stored_text 恒 NULL，API 响应也不外发原文；
- optin + 请求 store=true：才写 stored_text；
- DELETE /history 一键清除；
- TTL（history_ttl_days）算 expires_at。
"""

import httpx2
import pytest
from fastapi.testclient import TestClient

from conftest import query_all, run_async
from deaiify.config import get_settings
from deaiify.db.models import RewriteHistory
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


def _completion(content: str) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180},
    }


@pytest.fixture()
def rewrite_env(db_client, monkeypatch: pytest.MonkeyPatch):
    """db_client + mock openai provider（返回固定改写）。"""
    monkeypatch.setenv("DEAIIFY_OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    registry._INSTANCES.clear()

    def install(content: str) -> None:
        client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(
                lambda _r: httpx2.Response(200, json=_completion(content))
            )
        )
        registry.install_instance(OpenAIProvider(get_settings(), http_client=client))

    install(GOOD_REWRITE)
    yield db_client
    monkeypatch.delenv("DEAIIFY_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    registry._INSTANCES.clear()


def _rewrite(client: TestClient, **overrides) -> dict:
    body = {
        "text": ORIGINAL,
        "styles": ["natural"],
        "model": {"provider": "openai", "name": "gpt-test"},
    }
    body.update(overrides)
    resp = client.post("/api/v1/rewrite", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_never_mode_history_has_no_text(rewrite_env: TestClient) -> None:
    """默认隐私模式：行入库（分数/哈希），stored_text 恒 NULL。"""
    assert get_settings().store == "never"  # 先确认默认
    _rewrite(rewrite_env, store=True)  # 即便请求勾了 store

    rows = run_async(query_all(RewriteHistory))
    assert len(rows) == 1
    assert rows[0].stored_text is None
    assert rows[0].text_hash and len(rows[0].text_hash) == 64
    assert rows[0].text_len == len(ORIGINAL)
    assert rows[0].score_before > 0 and rows[0].score_after > 0
    # 原文不以任何形式出现在行上
    assert ORIGINAL not in (rows[0].text_hash + str(rows[0].text_len))


def test_never_mode_history_api_hides_text(rewrite_env: TestClient) -> None:
    _rewrite(rewrite_env, store=True)
    resp = rewrite_env.get("/api/v1/history")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["stored_text"] is None
    assert items[0]["delta"] == items[0]["score_after"] - items[0]["score_before"]
    assert ORIGINAL[:20] not in resp.text


def test_optin_mode_stores_text(monkeypatch: pytest.MonkeyPatch, db_client) -> None:
    """optin + 请求 store=true → 落原文；optin 但请求没勾 → 不落。"""
    import httpx2 as hx2

    from deaiify.config import get_settings as gs

    monkeypatch.setenv("DEAIIFY_STORE", "optin")
    monkeypatch.setenv("DEAIIFY_OPENAI_API_KEY", "sk-test")
    gs.cache_clear()
    registry._INSTANCES.clear()
    client = hx2.AsyncClient(
        transport=hx2.MockTransport(lambda _r: hx2.Response(200, json=_completion(GOOD_REWRITE)))
    )
    registry.install_instance(OpenAIProvider(gs(), http_client=client))

    try:
        # 勾选 store → 落原文
        _rewrite(db_client, store=True)
        # 未勾选 → 不落
        _rewrite(db_client, store=False, styles=["concise"])

        rows = run_async(query_all(RewriteHistory))
        assert len(rows) == 2
        by_style = {r.style: r for r in rows}
        assert by_style["natural"].stored_text == ORIGINAL
        assert by_style["concise"].stored_text is None

        # optin 模式下 API 返回 stored_text
        items = db_client.get("/api/v1/history").json()
        texts = {i["style"]: i["stored_text"] for i in items}
        assert texts["natural"] == ORIGINAL
        assert texts["concise"] is None
    finally:
        monkeypatch.delenv("DEAIIFY_STORE", raising=False)
        monkeypatch.delenv("DEAIIFY_OPENAI_API_KEY", raising=False)
        gs.cache_clear()
        registry._INSTANCES.clear()


def test_clear_history_endpoint(rewrite_env: TestClient) -> None:
    _rewrite(rewrite_env)
    _rewrite(rewrite_env, styles=["concise"])
    assert len(rewrite_env.get("/api/v1/history").json()) == 2

    resp = rewrite_env.delete("/api/v1/history")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2
    assert resp.json()["store_mode"] == "never"
    assert rewrite_env.get("/api/v1/history").json() == []
    assert run_async(query_all(RewriteHistory)) == []


def test_history_ttl_expiry(monkeypatch: pytest.MonkeyPatch, db_client) -> None:
    """history_ttl_days → expires_at 有值；purge_expired 能清。"""
    import httpx2 as hx2

    from deaiify.config import get_settings as gs
    from deaiify.services.history import purge_expired

    monkeypatch.setenv("DEAIIFY_HISTORY_TTL_DAYS", "7")
    monkeypatch.setenv("DEAIIFY_OPENAI_API_KEY", "sk-test")
    gs.cache_clear()
    registry._INSTANCES.clear()
    client = hx2.AsyncClient(
        transport=hx2.MockTransport(lambda _r: hx2.Response(200, json=_completion(GOOD_REWRITE)))
    )
    registry.install_instance(OpenAIProvider(gs(), http_client=client))

    try:
        _rewrite(db_client)
        rows = run_async(query_all(RewriteHistory))
        assert rows[0].expires_at is not None

        # 未过期 → purge 不清
        assert run_async(purge_expired(_session())) == 0

        # 手动把过期时间改到过去 → 被清
        run_async(_expire_first())
        assert run_async(purge_expired(_session())) == 1
        assert run_async(query_all(RewriteHistory)) == []
    finally:
        monkeypatch.delenv("DEAIIFY_HISTORY_TTL_DAYS", raising=False)
        monkeypatch.delenv("DEAIIFY_OPENAI_API_KEY", raising=False)
        gs.cache_clear()
        registry._INSTANCES.clear()


def _session():
    from deaiify.db.session import get_session_factory

    return get_session_factory()()


async def _expire_first() -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from deaiify.db.session import get_session_factory

    async with get_session_factory()() as session:
        row = (await session.scalars(select(RewriteHistory))).first()
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()
