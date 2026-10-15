"""GET /api/v1/models 与 /api/v1/styles：模型可达性探测与风格列表。"""

from fastapi import APIRouter

from deaiify.api.schemas import ModelOut, ProviderOut, StyleOut
from deaiify.providers.base import ProviderError
from deaiify.providers.registry import get_provider, known_providers
from deaiify.services.styles import STYLES

router = APIRouter()


@router.get("/models", response_model=list[ProviderOut], summary="可用模型（含健康状态）")
async def models_endpoint() -> list[ProviderOut]:
    out: list[ProviderOut] = []
    for name in known_providers():
        try:
            provider = get_provider(name)
            infos = await provider.list_models()
            out.append(
                ProviderOut(
                    provider=name,
                    available=True,
                    models=[ModelOut(id=m.id, provider=name, owned_by=m.owned_by) for m in infos],
                )
            )
        except ProviderError as exc:
            out.append(ProviderOut(provider=name, available=False, reason=exc.message))
        except Exception as exc:  # noqa: BLE001 - 探测失败不阻塞列表
            out.append(ProviderOut(provider=name, available=False, reason=f"{type(exc).__name__}"))
    return out


@router.get("/styles", response_model=list[StyleOut], summary="风格预设列表")
async def styles_endpoint() -> list[StyleOut]:
    return [StyleOut(id=s.id, name=s.name, description=s.description) for s in STYLES.values()]
