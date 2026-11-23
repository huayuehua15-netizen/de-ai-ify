"""批量任务端点（docs §6.5、§7.1）。

`POST /batch` 立即返回 job_id，任务在后台跑；`GET /batch/{job_id}` 读进度。
进度落库（刷新页面可恢复），改写正文只留在进程内（隐私，见 services/batch）。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from deaiify.api.errors import ApiError
from deaiify.api.schemas import (
    BatchItemOut,
    BatchJobOut,
    BatchRequest,
)
from deaiify.config import get_settings
from deaiify.db.session import get_session
from deaiify.services import batch as batch_svc
from deaiify.services.styles import get_style

router = APIRouter()


def _to_out(job, rows: list[dict]) -> BatchJobOut:
    settled = sum(1 for r in rows if r.get("status") in ("ok", "failed"))
    total = job.total or len(rows) or 1
    items = [
        BatchItemOut(
            index=row.get("index", i),
            title=row.get("title"),
            status=row.get("status", "pending"),
            text=row.get("text"),
            score_before=row.get("score_before"),
            score_after=row.get("score_after"),
            delta=row.get("delta"),
            gate=row.get("gate"),
            gate_reason=row.get("gate_reason"),
            attempts=row.get("attempts") or 0,
            error=row.get("error"),
        )
        for i, row in enumerate(rows)
    ]
    return BatchJobOut(
        job_id=job.id,
        status=job.status,  # type: ignore[arg-type]
        total=job.total,
        done=job.done,
        failed=job.failed,
        pending=max(0, job.total - settled),
        progress=round(settled / total, 4),
        style=job.style,
        model=job.model,
        error=job.error,
        created_at=job.created_at.isoformat() if job.created_at else None,
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
        items=items,
    )


@router.post("/batch", response_model=BatchJobOut, summary="创建批量改写任务")
async def create_batch(
    req: BatchRequest,
    session: AsyncSession | None = Depends(get_session),
) -> BatchJobOut:
    """建任务并立即返回（状态 queued），客户端轮询 GET /batch/{job_id}。"""
    settings = get_settings()
    for sid in req.styles:
        if get_style(sid) is None:
            raise ApiError("invalid_style", f"未知风格 {sid}")
    if len(req.items) > 50:
        raise ApiError("invalid_batch", "单次批量上限 50 条（docs §6.5）")
    for idx, item in enumerate(req.items):
        if len(item.text) > settings.max_text_chars:
            raise ApiError(
                "invalid_text",
                f"第 {idx + 1} 条超过 {settings.max_text_chars} 字上限"
                f"（可通过 DEAIIFY_MAX_TEXT_CHARS 调整）",
            )
    if session is None:
        raise ApiError("storage_unavailable", "批量任务需要可用存储；当前无法建任务", 503)

    try:
        job = await batch_svc.create_job(session, req)
    except ValueError as exc:
        raise ApiError("invalid_batch", str(exc)) from exc
    rows = await _rows(job.id)
    return _to_out(job, rows)


@router.get("/batch/{job_id}", response_model=BatchJobOut, summary="批量任务状态与结果")
async def get_batch(
    job_id: str,
    session: AsyncSession | None = Depends(get_session),
) -> BatchJobOut:
    if session is None:
        raise ApiError("storage_unavailable", "读取批量任务需要可用存储", 503)
    job, rows = await batch_svc.get_job(session, job_id)
    if job is None:
        raise ApiError("not_found", f"批量任务 {job_id} 不存在", 404)
    return _to_out(job, rows)


async def _rows(job_id: str) -> list[dict]:
    """建任务后立即回读一次，让响应带上每条 pending 的空壳。"""
    from deaiify.db.session import get_session_factory

    async with get_session_factory()() as session:
        _job, rows = await batch_svc.get_job(session, job_id)
    return rows
