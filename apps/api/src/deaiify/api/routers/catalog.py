"""GET /api/v1/models 与 /api/v1/styles：模型可达性探测与风格列表。

三 provider 并行探测（串行时最慢端点会叠加，实测 8.5s 拖垮首屏代理），
并带短 TTL 进程内缓存：同一浏览器会话反复拉目录时不再重复打上游。
"""

import asyncio
import time

from fastapi import APIRouter

from deaiify.api.schemas import ModelOut, ProviderOut, StyleOut
from deaiify.providers.base import ProviderError
from deaiify.providers.registry import get_provider, known_providers
from deaiify.services.styles import STYLES

router = APIRouter()

_PROBE_TIMEOUT_S = 4.0  # 单 provider 探测上限（list_models 内部 5s/2s connect）
_CACHE_TTL_S = 30.0
_cache: tuple[float, list[ProviderOut]] | None = None


async def _probe(name: str) -> ProviderOut:
    try:
        # get_provider 首次会同步 import openai/anthropic SDK（各需秒级），
        # 必须放线程池，否则阻塞事件循环、拖断同批次的 health/styles 请求
        provider = await asyncio.to_thread(get_provider, name)
        infos = await asyncio.wait_for(provider.list_models(), timeout=_PROBE_TIMEOUT_S)
        return ProviderOut(
            provider=name,
            available=True,
            models=[ModelOut(id=m.id, provider=name, owned_by=m.owned_by) for m in infos],
        )
    except ProviderError as exc:
        return ProviderOut(provider=name, available=False, reason=exc.message)
    except TimeoutError:
        return ProviderOut(provider=name, available=False, reason="探测超时")
    except Exception as exc:  # noqa: BLE001 - 探测失败不阻塞列表
        return ProviderOut(provider=name, available=False, reason=f"{type(exc).__name__}")


@router.get("/models", response_model=list[ProviderOut], summary="可用模型（含健康状态）")
async def models_endpoint() -> list[ProviderOut]:
    global _cache
    if _cache is not None and time.monotonic() - _cache[0] < _CACHE_TTL_S:
        return _cache[1]
    out = list(await asyncio.gather(*(_probe(name) for name in known_providers())))
    _cache = (time.monotonic(), out)
    return out


@router.get("/styles", response_model=list[StyleOut], summary="风格预设列表")
async def styles_endpoint() -> list[StyleOut]:
    return [StyleOut(id=s.id, name=s.name, description=s.description) for s in STYLES.values()]
