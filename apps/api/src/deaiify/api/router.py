"""v1 路由聚合（前缀由 main 统一挂载为 /api/v1）。"""

from fastapi import APIRouter

from deaiify.api.routers import (
    analyze,
    catalog,
    health,
    history,
    lexicons,
    providers,
    rewrite,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(analyze.router, tags=["analyze"])
api_router.include_router(rewrite.router, tags=["rewrite"])
api_router.include_router(catalog.router, tags=["catalog"])
api_router.include_router(lexicons.router, tags=["lexicons"])
api_router.include_router(history.router, tags=["history"])
api_router.include_router(providers.router, tags=["providers"])
