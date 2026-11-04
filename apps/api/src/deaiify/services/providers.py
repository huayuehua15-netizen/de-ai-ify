"""供应商配置服务：DB 里的供应商 ↔ 运行期 provider 实例。

解析优先级（用户直觉）：DB 配置（UI 添加的）> .env（传统配置）。
这样 UI 里配好就能直接用，不用改 .env 重启；env 仍作为无 UI 时的兜底。
"""

import uuid
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from deaiify.api.errors import ApiError
from deaiify.db.models import ProviderConfig
from deaiify.services import secrets as crypto

_MAX_CONFIGS = 20


def _new_id() -> str:
    return uuid.uuid4().hex


def public_view(cfg: ProviderConfig) -> dict[str, Any]:
    """对外视图：永不返回明文 key，只给 has_key + 掩码。"""
    plain = crypto.decrypt(cfg.api_key_enc or "")
    return {
        "id": cfg.id,
        "name": cfg.name,
        "kind": cfg.kind,
        "base_url": cfg.base_url or "",
        "default_model": cfg.default_model or "",
        "has_key": bool(plain),
        "key_mask": crypto.mask(plain),
        "is_default": cfg.is_default,
        "enabled": cfg.enabled,
        "created_at": cfg.created_at.isoformat() if cfg.created_at else None,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


async def list_configs(session: AsyncSession) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(ProviderConfig).order_by(ProviderConfig.is_default.desc(), ProviderConfig.created_at)
    )
    return [public_view(c) for c in rows]


async def get_config(session: AsyncSession, cfg_id: str) -> ProviderConfig:
    cfg = await session.get(ProviderConfig, cfg_id)
    if cfg is None:
        raise ApiError("not_found", f"供应商配置 {cfg_id} 不存在", 404)
    return cfg


async def create_config(
    session: AsyncSession,
    *,
    name: str,
    kind: str,
    base_url: str | None,
    api_key: str | None,
    default_model: str | None,
    is_default: bool = False,
) -> dict[str, Any]:
    count = len(list(await session.scalars(select(ProviderConfig))))
    if count >= _MAX_CONFIGS:
        raise ApiError("provider_limit", f"最多配置 {_MAX_CONFIGS} 个供应商（当前 {count}）", 400)
    if kind not in {"openai", "anthropic", "ollama"}:
        raise ApiError(
            "invalid_provider", f"未知供应商类型 {kind}（可用 openai/anthropic/ollama）", 400
        )
    cfg = ProviderConfig(
        id=_new_id(),
        name=name.strip(),
        kind=kind,
        base_url=(base_url or "").strip() or None,
        api_key_enc=crypto.encrypt(api_key) if api_key else None,
        default_model=(default_model or "").strip() or None,
        is_default=False,
        enabled=True,
    )
    session.add(cfg)
    await session.commit()
    if is_default:
        await set_default(session, cfg.id)
        await session.refresh(cfg)
    return public_view(cfg)


async def update_config(
    session: AsyncSession, cfg_id: str, patch: dict[str, Any]
) -> dict[str, Any]:
    cfg = await get_config(session, cfg_id)
    if "name" in patch and patch["name"]:
        cfg.name = str(patch["name"]).strip()
    if "kind" in patch and patch["kind"]:
        if patch["kind"] not in {"openai", "anthropic", "ollama"}:
            raise ApiError("invalid_provider", f"未知供应商类型 {patch['kind']}", 400)
        cfg.kind = patch["kind"]
    if "base_url" in patch:
        cfg.base_url = (patch["base_url"] or "").strip() or None
    if "default_model" in patch:
        cfg.default_model = (patch["default_model"] or "").strip() or None
    if "enabled" in patch:
        cfg.enabled = bool(patch["enabled"])
    # api_key：显式 null/空串 = 清除；非空 = 覆写
    if "api_key" in patch:
        raw = patch["api_key"]
        cfg.api_key_enc = crypto.encrypt(str(raw)) if raw else None
    await session.commit()
    await session.refresh(cfg)
    return public_view(cfg)


async def delete_config(session: AsyncSession, cfg_id: str) -> None:
    cfg = await get_config(session, cfg_id)
    await session.delete(cfg)
    await session.commit()


async def set_default(session: AsyncSession, cfg_id: str) -> dict[str, Any]:
    """把某个配置设为默认（全局唯一）。"""
    cfg = await get_config(session, cfg_id)
    await session.execute(update(ProviderConfig).values(is_default=False))
    cfg.is_default = True
    cfg.enabled = True
    await session.commit()
    await session.refresh(cfg)
    return public_view(cfg)


async def resolve_for_engine(
    session: AsyncSession, cfg_id: str | None
) -> tuple[str, str, str | None] | None:
    """解析为引擎可用三元组 (kind, api_key, base_url)；无 DB 配置时返回 None。

    引擎侧（registry）优先用这个；返回 None 表示回落到 .env 配置。
    """
    if cfg_id:
        cfg = await session.get(ProviderConfig, cfg_id)
        if cfg is None or not cfg.enabled:
            raise ApiError("not_found", f"供应商配置 {cfg_id} 不存在或已停用", 404)
        return cfg.kind, crypto.decrypt(cfg.api_key_enc or ""), cfg.base_url
    # 未指定：取默认配置
    cfg = await session.scalars(
        select(ProviderConfig)
        .where(ProviderConfig.is_default.is_(True), ProviderConfig.enabled.is_(True))
        .limit(1)
    )
    first = cfg.first()
    if first is None:
        return None
    return first.kind, crypto.decrypt(first.api_key_enc or ""), first.base_url


async def test_connection(
    kind: str, base_url: str | None, api_key: str | None, timeout: float = 8.0
) -> dict[str, Any]:
    """实测连通性：列模型（不消耗 token）。返回 {ok, models, error}。"""
    base = (base_url or "").rstrip("/")
    if kind == "ollama":
        url = f"{base or 'http://127.0.0.1:11434'}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            return {
                "ok": True,
                "models": [m.get("name", "") for m in data.get("models", [])],
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "models": [], "error": f"{type(exc).__name__}: {exc}"}

    if kind == "anthropic":
        url = "https://api.anthropic.com/v1/models"
        headers = {"x-api-key": api_key or "", "anthropic-version": "2023-06-01"}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            return {
                "ok": True,
                "models": [m.get("id", "") for m in data.get("data", [])],
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "models": [], "error": f"{type(exc).__name__}: {exc}"}

    # openai 兼容：GET /models
    url = f"{base or 'https://api.openai.com/v1'}/models"
    headers = {"Authorization": f"Bearer {api_key or ''}"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return {
            "ok": True,
            "models": [m.get("id", "") for m in data.get("data", [])],
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "models": [], "error": f"{type(exc).__name__}: {exc}"}
