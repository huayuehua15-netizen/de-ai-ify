"""POST /api/v1/analyze：AI 味评分与高亮（纯本地，不需要任何模型）。

M4：支持 lexicon_ids（自定义词库）与内置词条停用；DB 不可达时优雅降级
为纯内置词库（评分永远可用，不因存储故障而 500）。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from deaiify.api.errors import ApiError
from deaiify.api.schemas import AnalyzeRequest
from deaiify.config import get_settings
from deaiify.db.session import get_session
from deaiify.engine import analyze
from deaiify.engine.lexicon import Term
from deaiify.engine.models import AnalysisResult
from deaiify.services.lexicons import load_engine_terms

router = APIRouter()


async def _lexicon_context(
    session: AsyncSession | None, lexicon_ids: list[str]
) -> tuple[list[Term], set[str]]:
    """读词库上下文；任何 DB 错误都降级为空（评分不依赖存储）。"""
    if session is None:
        return [], set()
    try:
        return await load_engine_terms(session, lexicon_ids)
    except Exception:  # noqa: BLE001 - 评分路径不允许因存储故障失败
        return [], set()


@router.post("/analyze", response_model=AnalysisResult, summary="AI 味评分")
async def analyze_endpoint(
    req: AnalyzeRequest,
    session: AsyncSession | None = Depends(get_session),
) -> AnalysisResult:
    settings = get_settings()
    if len(req.text) > settings.max_text_chars:
        raise ApiError(
            "invalid_text",
            f"文本超过 {settings.max_text_chars} 字上限（可通过 DEAIIFY_MAX_TEXT_CHARS 调整）",
        )
    extra, disabled = await _lexicon_context(session, req.lexicon_ids)
    # store 请求字段仅影响历史（analyze 不落库，findings 原文片段永不出网/落库）
    return analyze(req.text, lang=req.lang, extra_terms=extra, disabled=disabled)
