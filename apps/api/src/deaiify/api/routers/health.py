"""/api/v1/health：版本 + 存储连通性 + 模型就绪状态（失败降级，不阻塞启动）。

`providers` 只查**配置是否齐备**（DB 里有启用的供应商 / .env 里有 key），
不探测上游可达性——否则 health 会被网络超时拖慢，而徽标是每次打开页面都请求的。
上游真实可达性由 /providers/{id}/test 单独按需测。
"""

import platform
import time

import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text

from deaiify import __version__
from deaiify.config import get_settings
from deaiify.db.session import get_engine
from deaiify.engine.version import ENGINE_VERSION

router = APIRouter()


async def check_db() -> dict[str, str]:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "dialect": engine.dialect.name}
    except Exception as exc:
        # health 需兜底任意驱动错误；只回传异常类型名，避免泄露连接细节
        return {"status": "unavailable", "detail": type(exc).__name__}


async def check_redis() -> dict[str, str]:
    url = get_settings().redis_url
    if not url:
        # lite 模式（SQLite + 进程内队列）不依赖 Redis
        return {"status": "skipped"}
    client = aioredis.from_url(url, socket_connect_timeout=2)
    try:
        await client.ping()
    except Exception as exc:
        return {"status": "unavailable", "detail": type(exc).__name__}
    finally:
        await client.aclose()
    return {"status": "ok"}


async def check_providers() -> dict[str, object]:
    """模型是否可改写：DB 配置优先，回落 .env；只查配置，不探上游。"""
    settings = get_settings()

    # 1) DB 里启用的供应商（UI 配的）
    db_count = 0
    default_name: str | None = None
    db_ok = True
    try:
        from sqlalchemy import select

        from deaiify.db.models import ProviderConfig
        from deaiify.db.session import get_session_factory

        async with get_session_factory()() as session:
            rows = list(
                await session.scalars(
                    select(ProviderConfig).where(ProviderConfig.enabled.is_(True))
                )
            )
            db_count = len(rows)
            default = next((r for r in rows if r.is_default), None)
            default_name = default.name if default else (rows[0].name if rows else None)
    except Exception:  # noqa: BLE001 - 存储不可用属正常降级
        db_ok = False

    # 2) .env 兜底：只认真实配置过的凭据。
    #    注意 ollama_base_url 有默认值（127.0.0.1:11434），不能仅凭"非空"就判定
    #    已配置——否则没装 Ollama 的机器也会显示"可改写"（实测踩过）。
    #    判定：显式设了 OpenAI/Anthropic key，或显式把 ollama 地址设成非默认值。
    from deaiify.config import Settings

    default_ollama = Settings().ollama_base_url
    ollama_explicit = settings.ollama_base_url and settings.ollama_base_url != default_ollama
    env_configured = bool(settings.openai_api_key or settings.anthropic_api_key or ollama_explicit)

    ready = db_count > 0 or (db_ok and env_configured)
    source = "ui" if db_count > 0 else ("env" if env_configured else "none")
    return {
        "ready": ready,
        "source": source,
        "count": db_count,
        "default": default_name,
        "env_fallback": env_configured,
    }


@router.get("/health", summary="服务健康")
async def health() -> dict:
    settings = get_settings()
    return {
        "service": "deaiify",
        "version": __version__,
        "engine_version": ENGINE_VERSION,
        "env": settings.env,
        "python": platform.python_version(),
        "db": await check_db(),
        "redis": await check_redis(),
        "providers": await check_providers(),
        "time": int(time.time()),
    }
