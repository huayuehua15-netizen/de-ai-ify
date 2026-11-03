"""历史端点（docs §8.2）：

GET    /history   最近改写历史（never 模式 stored_text 恒 null）
DELETE /history   一键清除全部历史行
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from deaiify.config import get_settings
from deaiify.db.session import get_session
from deaiify.services import history as svc

router = APIRouter()


class HistoryOut(BaseModel):
    id: str
    style: str
    model: str
    lang: str
    score_before: int
    score_after: int
    delta: int
    text_len: int
    text_hash: str
    stored_text: str | None = None
    created_at: str | None = None
    expires_at: str | None = None


class ClearOut(BaseModel):
    deleted: int
    store_mode: str


def _out(row) -> HistoryOut:  # noqa: ANN001 - SQLAlchemy 实例
    return HistoryOut(
        id=row.id,
        style=row.style,
        model=row.model,
        lang=row.lang,
        score_before=row.score_before,
        score_after=row.score_after,
        delta=row.score_after - row.score_before,
        text_len=row.text_len,
        text_hash=row.text_hash,
        # 双保险：即便 DB 有值，never 模式也不外发原文
        stored_text=(row.stored_text if get_settings().store == "optin" else None),
        created_at=row.created_at.isoformat() if row.created_at else None,
        expires_at=row.expires_at.isoformat() if row.expires_at else None,
    )


@router.get("/history", response_model=list[HistoryOut], summary="改写历史")
async def list_history(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[HistoryOut]:
    return [_out(r) for r in await svc.list_history(session, limit)]


@router.delete("/history", response_model=ClearOut, summary="一键清除历史")
async def clear_history(session: AsyncSession = Depends(get_session)) -> ClearOut:
    deleted = await svc.clear_history(session)
    return ClearOut(deleted=deleted, store_mode=get_settings().store)
