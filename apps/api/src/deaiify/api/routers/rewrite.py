"""POST /api/v1/rewrite 与 /rewrite/stream：多风格改写（docs §6、§7.2、§7.3）。"""

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from deaiify.api.errors import ApiError
from deaiify.api.schemas import RewriteRequest, RewriteResponse, RewriteVersionOut
from deaiify.config import get_settings
from deaiify.db.session import get_session
from deaiify.engine import analyze
from deaiify.providers.base import ProviderError
from deaiify.providers.registry import get_provider
from deaiify.services import history as history_svc
from deaiify.services.rewrite import rewrite_one, stream_rewrite
from deaiify.services.styles import get_style

router = APIRouter()


async def _record_history(
    session: AsyncSession | None,
    req: RewriteRequest,
    *,
    lang: str,
    model: str,
    style: str,
    score_before: int,
    score_after: int,
) -> None:
    """历史落库：失败不打断响应（never 模式只写哈希/分数，docs §8.2）。"""
    if session is None:
        return
    try:
        await history_svc.record(
            session,
            text=req.text,
            lang=lang,
            style=style,
            model=model,
            score_before=score_before,
            score_after=score_after,
            store_text=history_svc.should_store_text(req.store),
        )
    except Exception:  # noqa: BLE001 - 历史是非关键路径
        pass


async def _prepare(req: RewriteRequest) -> tuple[list[str], int, str, str, Any]:
    """公共校验：文本/风格/provider/模型；返回 (styles, before_score, lang, model, provider)。"""
    settings = get_settings()
    if len(req.text) > settings.max_text_chars:
        raise ApiError(
            "invalid_text",
            f"文本超过 {settings.max_text_chars} 字上限（可通过 DEAIIFY_MAX_TEXT_CHARS 调整）",
        )
    # 去重且保序
    styles: list[str] = list(dict.fromkeys(req.styles))
    for sid in styles:
        if get_style(sid) is None:
            raise ApiError(
                "invalid_style",
                f"未知风格 {sid}（可用：natural/concise/academic/business/social）",
            )
    # 首次调用会同步 import SDK，放线程池避免阻塞事件循环（与 catalog._probe 同理）
    provider = await asyncio.to_thread(get_provider, req.model.provider)  # 未配置 → 503
    model = req.model.name or settings.default_model
    if not model:
        raise ApiError(
            "model_unavailable",
            "未指定模型：在请求 model.name 或环境变量 DEAIIFY_DEFAULT_MODEL 中设置",
        )
    before = analyze(req.text)
    return styles, before.score, before.lang, model, provider


def _outcomes_to_versions(outcomes) -> list[RewriteVersionOut]:
    return [
        RewriteVersionOut(
            style=o.style,
            text=o.text,
            score_before=o.score_before,
            score_after=o.score_after,
            delta=o.delta,
            gate=o.gate,  # type: ignore[arg-type]
            model=o.model,
            usage=o.usage,
            attempts=o.attempts,
            gate_reason=o.gate_reason,
        )
        for o in outcomes
    ]


@router.post("/rewrite", response_model=RewriteResponse, summary="多风格改写")
async def rewrite_endpoint(
    req: RewriteRequest,
    session: AsyncSession | None = Depends(get_session),
) -> RewriteResponse:
    styles, before_score, lang, model, provider = await _prepare(req)
    outcomes = await asyncio.gather(
        *(
            rewrite_one(
                req.text,
                get_style(sid),  # type: ignore[arg-type]
                lang,
                provider,
                model,
                score_before=before_score,
                use_gate=req.gate,
            )
            for sid in styles
        )
    )
    for outcome in outcomes:
        await _record_history(
            session,
            req,
            lang=lang,
            model=outcome.model,
            style=outcome.style,
            score_before=outcome.score_before,
            score_after=outcome.score_after,
        )
    return RewriteResponse(
        versions=_outcomes_to_versions(outcomes),
        engine_version=analyze(req.text).engine_version,
    )


def _sse(event: str, data: dict) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


@router.post("/rewrite/stream", summary="流式改写（SSE，docs §7.3 事件协议）")
async def rewrite_stream_endpoint(
    req: RewriteRequest,
    session: AsyncSession | None = Depends(get_session),
) -> EventSourceResponse:
    styles, before_score, lang, model, provider = await _prepare(req)

    async def generator():
        started = time.perf_counter()
        yield _sse(
            "start",
            {"styles": styles, "before": before_score, "model": model},
        )
        finished = 0
        # 流式按风格顺序执行：并行流会让多路 chunk 交错，客户端解析复杂化（docs §6.1 说明）
        for sid in styles:
            style = get_style(sid)
            try:
                async for ev in stream_rewrite(
                    req.text,
                    style,  # type: ignore[arg-type]
                    lang,
                    provider,
                    model,
                    score_before=before_score,
                    use_gate=req.gate,
                ):
                    yield _sse(ev.kind, ev.data)
                    if ev.kind == "version":
                        finished += 1
                    elif ev.kind == "score":
                        # 每风格拿到最终分后记历史（依赖会话在流结束才释放，安全）
                        await _record_history(
                            session,
                            req,
                            lang=lang,
                            model=ev.data.get("model") or model,
                            style=sid,
                            score_before=ev.data.get("before", before_score),
                            score_after=ev.data.get("after", before_score),
                        )
            except ProviderError as exc:
                yield _sse("error", {"code": exc.code, "message": exc.message, "style": sid})
            except Exception as exc:  # noqa: BLE001 - 流已开始，必须转为事件而非断连
                yield _sse(
                    "error",
                    {
                        "code": "provider_error",
                        "message": f"{type(exc).__name__}: {exc}",
                        "style": sid,
                    },
                )
        yield _sse(
            "done",
            {
                "versions": finished,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            },
        )

    return EventSourceResponse(generator())
