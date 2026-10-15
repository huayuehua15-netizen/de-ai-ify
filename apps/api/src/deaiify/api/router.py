"""v1 路由聚合。"""

from fastapi import APIRouter

from deaiify.api.routers import health

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
