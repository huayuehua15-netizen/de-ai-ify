"""/api/v1/health：版本 + 存储连通性探测（失败降级，不阻塞启动）。"""

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
        "time": int(time.time()),
    }
