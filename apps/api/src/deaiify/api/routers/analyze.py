"""POST /api/v1/analyze：AI 味评分与高亮（纯本地，不需要任何模型）。"""

from fastapi import APIRouter

from deaiify.api.schemas import AnalyzeRequest
from deaiify.config import get_settings
from deaiify.engine import analyze
from deaiify.engine.models import AnalysisResult

router = APIRouter()


@router.post("/analyze", response_model=AnalysisResult, summary="AI 味评分")
async def analyze_endpoint(req: AnalyzeRequest) -> AnalysisResult:
    settings = get_settings()
    if len(req.text) > settings.max_text_chars:
        from deaiify.api.errors import ApiError

        raise ApiError(
            "invalid_text",
            f"文本超过 {settings.max_text_chars} 字上限（可通过 DEAIIFY_MAX_TEXT_CHARS 调整）",
        )
    # store 请求字段已接收：隐私默认 never，持久化在 M4 实现（当前不落任何库）
    return analyze(req.text, lang=req.lang)
