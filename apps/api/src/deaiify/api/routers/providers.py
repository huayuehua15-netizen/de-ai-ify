"""供应商配置端点（UI「模型设置」页的数据源）：

GET    /providers/presets          预设供应商列表（一键填充用）
GET    /providers                  已配置供应商（永不返回明文 key）
POST   /providers                  添加供应商
PATCH  /providers/{id}             修改（含覆写/清除 key）
DELETE /providers/{id}             删除
POST   /providers/{id}/default     设为默认
POST   /providers/{id}/test        实测连通性（列模型，不消耗 token）
POST   /providers/test             未保存前的预检（body 带 kind/base_url/api_key）
"""

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from deaiify.db.session import get_session
from deaiify.services import providers as svc
from deaiify.services.provider_presets import PRESETS

router = APIRouter()

ProviderKind = Literal["openai", "anthropic", "ollama"]


class ProviderCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: ProviderKind = "openai"
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    is_default: bool = False


class ProviderPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: ProviderKind | None = None
    base_url: str | None = None
    api_key: str | None = Field(default=None, description="传空串清除已有 key；不传则不修改")
    default_model: str | None = None
    enabled: bool | None = None


class ProviderTestIn(BaseModel):
    kind: ProviderKind = "openai"
    base_url: str | None = None
    api_key: str | None = None


@router.get("/providers/presets", summary="供应商预设列表")
async def presets_endpoint() -> list[dict[str, Any]]:
    return list(PRESETS)


@router.get("/providers", summary="已配置供应商")
async def list_endpoint(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return await svc.list_configs(session)


@router.post("/providers", status_code=201, summary="添加供应商")
async def create_endpoint(
    body: ProviderCreateIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    return await svc.create_config(
        session,
        name=body.name,
        kind=body.kind,
        base_url=body.base_url,
        api_key=body.api_key,
        default_model=body.default_model,
        is_default=body.is_default,
    )


@router.post("/providers/test", summary="预检连通性（保存前）")
async def test_endpoint(body: ProviderTestIn) -> dict[str, Any]:
    return await svc.test_connection(body.kind, body.base_url, body.api_key)


@router.get("/providers/{cfg_id}", summary="单个供应商详情")
async def get_endpoint(cfg_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    cfg = await svc.get_config(session, cfg_id)
    return svc.public_view(cfg)


@router.patch("/providers/{cfg_id}", summary="修改供应商")
async def patch_endpoint(
    cfg_id: str, body: ProviderPatchIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    # 只把显式传入的字段纳入 patch（api_key 传空串 = 清除，需区分"没传"）
    patch = body.model_dump(exclude_unset=True)
    return await svc.update_config(session, cfg_id, patch)


@router.delete("/providers/{cfg_id}", status_code=204, summary="删除供应商")
async def delete_endpoint(cfg_id: str, session: AsyncSession = Depends(get_session)) -> None:
    await svc.delete_config(session, cfg_id)


@router.post("/providers/{cfg_id}/default", summary="设为默认供应商")
async def default_endpoint(
    cfg_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    return await svc.set_default(session, cfg_id)


@router.post("/providers/{cfg_id}/test", summary="实测已保存供应商的连通性")
async def test_saved_endpoint(
    cfg_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    cfg = await svc.get_config(session, cfg_id)
    from deaiify.services import secrets as crypto

    return await svc.test_connection(cfg.kind, cfg.base_url, crypto.decrypt(cfg.api_key_enc or ""))
