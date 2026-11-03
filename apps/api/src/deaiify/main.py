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
    """后台预 import 三个 provider SDK（openai/anthropic 各需秒级）。

    不设凭据也预热：import 只付一次成本，否则首个 /models 或 /rewrite
    请求会在事件循环里同步 import（已用 to_thread 兜底，这里进一步让
    启动后第一批请求就拿到热缓存）。
    """
    from deaiify.providers.registry import get_provider, known_providers

    for name in known_providers():
        try:
            get_provider(name)
        except Exception:  # noqa: BLE001 - 未配置凭据属正常，预热只关心 import
            pass


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # 启动不主动连库（health 惰性探测）；M4 起在此做迁移检查
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
