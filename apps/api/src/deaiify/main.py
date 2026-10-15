"""FastAPI 应用工厂（接口设计见 docs/DEVELOPMENT.md §7）。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from deaiify import __version__
from deaiify.api.router import api_router
from deaiify.db.session import dispose_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # M0：启动不主动连库（health 惰性探测）；M4 起在此做迁移检查与预热
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="de-ai-ify API",
        version=__version__,
        description="去 AI 味：可解释的 AI 文本评分与改写（接口设计见 docs/DEVELOPMENT.md §7）",
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
