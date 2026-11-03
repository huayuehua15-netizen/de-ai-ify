"""FastAPI 应用工厂（接口设计见 docs/DEVELOPMENT.md §7）。"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from deaiify import __version__
from deaiify.api.errors import error_response, register_error_handlers
from deaiify.api.ratelimit import SlidingWindowLimiter
from deaiify.api.router import api_router
from deaiify.config import get_settings
from deaiify.db.session import dispose_engine


def _warm_providers() -> None:
    """后台预 import 三个 provider 实现模块（SDK 各需秒级，anthropic ~9s）。

    只 import、不 get_provider 构造实例：构造会读 settings 并写注册表，
    在启动早期与测试注入/配置变更产生竞态；import 本身才是这笔开销的大头。
    """
    import deaiify.providers.anthropic_provider  # noqa: F401
    import deaiify.providers.ollama_provider  # noqa: F401
    import deaiify.providers.openai_provider  # noqa: F401


async def _init_schema() -> None:
    """启动建表（幂等 create_all）。

    M4 用 create_all 而非 Alembic：当前只有一版表结构，两模式（PG/SQLite）
    同一套 metadata 即可；出现第一个破坏性结构变更时再引入 Alembic 迁移链。
    存储不可用时不阻塞启动（health 会如实报告 unavailable）。
    """
    from sqlalchemy import text

    from deaiify.db.models import Base
    from deaiify.db.session import get_engine

    try:
        engine = get_engine()
        # SQLite 保证父目录存在（lite 模式 ./data/ 可能未创建）
        if engine.dialect.name == "sqlite" and engine.url.database:
            from pathlib import Path

            db_path = Path(engine.url.database)
            if db_path.parent and str(db_path.parent) not in ("", "."):
                db_path.parent.mkdir(parents=True, exist_ok=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # 触发一次真实往返，暴露连接问题给 health（而非启动崩溃）
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - 存储故障降级启动
        print(f"[deaiify] schema init skipped: {type(exc).__name__}: {exc}")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # health 惰性探测不阻塞启动；建表失败仅告警
    await _init_schema()
    warm = asyncio.create_task(asyncio.to_thread(_warm_providers))
    yield
    warm.cancel()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="de-ai-ify API",
        version=__version__,
        description="去 AI 味：可解释的 AI 文本评分与改写（接口设计见 docs/DEVELOPMENT.md §7）",
        lifespan=lifespan,
    )
    app.state.limiter = SlidingWindowLimiter(settings.rate_limit_per_min)
    register_error_handlers(app)

    @app.middleware("http")
    async def guards(request: Request, call_next):
        # 请求 ID：透传入站或生成，响应头回写（错误体同用）
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        path = request.url.path
        if path.startswith("/api/") and not path.endswith("/health"):
            # 1) 可选 API key 鉴权（DEAIIFY_API_KEY 未设置则不鉴权）
            if settings.api_key:
                auth = request.headers.get("authorization", "")
                if auth != f"Bearer {settings.api_key}":
                    return error_response(request, "unauthorized", "缺少或无效的 API Key", 401)
            # 2) 限流：IP + 所提供 key 双维度（docs §7.5）
            host = request.client.host if request.client else "unknown"
            suffix = auth.split()[-1][-4:] if settings.api_key else ""
            if not app.state.limiter.allow(f"{host}|{suffix}"):
                return error_response(request, "rate_limited", "请求过于频繁，请稍后再试", 429)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
