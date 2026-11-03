"""改写历史：隐私规则的唯一落库入口（docs §4.3、§8.2）。

规则：
- settings.store == "never"（默认）：写行（哈希/长度/分数，供趋势与去重），
  stored_text 恒 NULL；
- settings.store == "optin" 且请求 store=true：额外写 stored_text + expires_at；
- 日志/响应中不出现原文（历史接口返回 stored_text 字段仅在 optin 时可能非空）。
"""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from deaiify.config import get_settings
from deaiify.db.models import RewriteHistory


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def should_store_text(requested: bool) -> bool:
    """是否允许落原文：仅 optin 模式 + 请求显式勾选。"""
    return get_settings().store == "optin" and requested


async def record(
    session: AsyncSession,
    *,
    text: str,
    lang: str,
    style: str,
    model: str,
    score_before: int,
    score_after: int,
    store_text: bool,
) -> RewriteHistory | None:
    """写一条历史；DB 异常时返回 None（历史失败不打断改写响应）。"""
    settings = get_settings()
    expires_at = None
    if settings.history_ttl_days:
        expires_at = datetime.now(UTC) + timedelta(days=settings.history_ttl_days)
    row = RewriteHistory(
        id=hashlib.sha256(
            f"{_hash(text)}{style}{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:32],
        text_hash=_hash(text),
        text_len=len(text),
        lang=lang,
        style=style,
        model=model,
        score_before=score_before,
        score_after=score_after,
        stored_text=text if store_text else None,
        expires_at=expires_at,
    )
    session.add(row)
    await session.commit()
    return row


async def list_history(session: AsyncSession, limit: int = 50) -> list[RewriteHistory]:
    rows = await session.scalars(
        select(RewriteHistory).order_by(RewriteHistory.created_at.desc()).limit(limit)
    )
    return list(rows)


async def clear_history(session: AsyncSession) -> int:
    """一键清除：删除全部历史行（§8.2 DELETE /history）。"""
    result = await session.execute(delete(RewriteHistory))
    await session.commit()
    return result.rowcount or 0


async def purge_expired(session: AsyncSession) -> int:
    """清理超过 expires_at 的行（启动时与定期调用，optin+TTL 场景）。"""
    now = datetime.now(UTC)
    result = await session.execute(
        delete(RewriteHistory).where(
            RewriteHistory.expires_at.is_not(None), RewriteHistory.expires_at < now
        )
    )
    await session.commit()
    return result.rowcount or 0
