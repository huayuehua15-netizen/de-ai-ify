"""批量任务服务（docs §6.5、§8.1 jobs 表）。

状态机：`queued → running → done | failed`。

**进度与正文的分工**——这是本模块最重要的设计取舍：
- 进度、逐条分数、错误摘要 → 落库（`batch_jobs`），刷新页面可恢复；
- 改写正文 → 只留在进程内 `_RESULTS`，**绝不写数据库**。

理由：隐私承诺（§8.2 never 模式不落原文）是全局约束，批量任务不该成为
后门。代价是进程重启后正文拿不回来；这种情况由 `reconcile_interrupted()`
把 `queued/running` 的任务标成 `failed` 并说明原因，而不是让它永远转圈。

并发由 `DEAIIFY_BATCH_CONCURRENCY`（默认 3）控制，单条失败不阻塞整批。
"""

import asyncio
import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deaiify.api.schemas import BatchItemIn, BatchRequest
from deaiify.config import get_settings
from deaiify.db.models import BatchJob
from deaiify.db.session import get_session_factory
from deaiify.engine import analyze
from deaiify.providers.base import ProviderError
from deaiify.services import history as history_svc
from deaiify.services.providers import resolve_model
from deaiify.services.rewrite import rewrite_one
from deaiify.services.styles import get_style

_MAX_JOBS = 20  # 保留最近多少个任务（DB 与内存同步裁剪）

# 进程内正文缓存：job_id → 逐条结果（含 text）。进程退出即消失，符合隐私约定。
_RESULTS: dict[str, list[dict[str, Any]]] = {}
_RESULT_ORDER: list[str] = []

# 后台任务强引用：asyncio 不持有强引用时任务可能被 GC 掉
_TASKS: set[asyncio.Task[None]] = set()


def _new_id() -> str:
    return uuid.uuid4().hex


def _text_meta(item: BatchItemIn) -> dict[str, Any]:
    """落库的条目元信息：只有长度与哈希，不含正文。"""
    return {
        "title": item.title,
        "len": len(item.text),
        "sha256": hashlib.sha256(item.text.encode("utf-8")).hexdigest()[:16],
    }


def _remember(job_id: str, items: list[dict[str, Any]]) -> None:
    """写入进程内正文缓存，并按创建顺序裁剪到 _MAX_JOBS。"""
    _RESULTS[job_id] = items
    if job_id not in _RESULT_ORDER:
        _RESULT_ORDER.append(job_id)
    while len(_RESULT_ORDER) > _MAX_JOBS:
        dropped = _RESULT_ORDER.pop(0)
        _RESULTS.pop(dropped, None)


async def _save_results(job_id: str) -> None:
    """把内存里的逐条状态（去掉正文）写回 DB。

    不截断：只存元信息（状态/分数/错误摘要），50 条也就几 KB，
    截断反而让「刷新进度不丢」在大批次上失效。
    """
    import json

    rows = _RESULTS.get(job_id)
    if rows is None:
        return
    payload = [{k: v for k, v in row.items() if k != "text"} for row in rows]
    async with get_session_factory()() as session:
        job = await session.get(BatchJob, job_id)
        if job is None:
            return
        job.results_json = json.dumps(payload, ensure_ascii=False)
        job.done = sum(1 for r in rows if r["status"] == "ok")
        job.failed = sum(1 for r in rows if r["status"] == "failed")
        await session.commit()


async def _set_status(job_id: str, status: str, *, error: str | None = None) -> None:
    async with get_session_factory()() as session:
        job = await session.get(BatchJob, job_id)
        if job is None:
            return
        job.status = status
        if error is not None:
            job.error = error
        await session.commit()


async def _set_model(job_id: str, model: str) -> None:
    """回填解析出的真实模型名（建任务时可能还不知道，见 create_job 注释）。"""
    if not model:
        return
    async with get_session_factory()() as session:
        job = await session.get(BatchJob, job_id)
        if job is None or job.model == model:
            return
        job.model = model
        await session.commit()


async def _trim_jobs(session: AsyncSession) -> None:
    """只保留最近 _MAX_JOBS 个任务，避免 DB 无限膨胀。"""
    rows = list(
        await session.scalars(
            select(BatchJob).order_by(BatchJob.created_at.desc()).offset(_MAX_JOBS)
        )
    )
    for stale in rows:
        await session.delete(stale)
    if rows:
        await session.commit()


async def create_job(session: AsyncSession, req: BatchRequest) -> BatchJob:
    """建任务 + 落库 + 起后台协程。请求立即返回 job_id（docs §6.5）。"""
    settings = get_settings()
    style = get_style(req.styles[0])
    if style is None:  # 路由已校验，此处兜底
        raise ValueError(f"未知风格 {req.styles[0]}")

    # 模型名此刻可能还解析不出来（走 DB 默认供应商时，模型取自该配置），
    # 先记请求里显式给的值，_run_job 解析完再回填真实值。
    requested_model = req.model.name or settings.default_model or ""

    for idx, item in enumerate(req.items):
        if len(item.text) > settings.max_text_chars:
            raise ValueError(
                f"第 {idx + 1} 条超过 {settings.max_text_chars} 字上限"
                f"（可通过 DEAIIFY_MAX_TEXT_CHARS 调整）"
            )

    job_id = _new_id()
    job = BatchJob(
        id=job_id,
        status="queued",
        total=len(req.items),
        done=0,
        failed=0,
        style=style.id,
        model=requested_model,
        payload_json=None,
        results_json=None,
    )
    import json

    job.payload_json = json.dumps([_text_meta(i) for i in req.items], ensure_ascii=False)
    session.add(job)
    await session.commit()
    await _trim_jobs(session)

    _remember(
        job_id,
        [
            {
                "index": idx,
                "title": item.title,
                "status": "pending",
                "text": None,
                "score_before": None,
                "score_after": None,
                "delta": None,
                "gate": None,
                "gate_reason": None,
                "attempts": 0,
                "error": None,
            }
            for idx, item in enumerate(req.items)
        ],
    )

    task = asyncio.create_task(_run_job(job_id, req))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return job


async def _run_job(job_id: str, req: BatchRequest) -> None:
    """后台执行：并发受限地跑完所有条目，逐条落状态，单条失败不中断。"""
    settings = get_settings()
    rows = _RESULTS.get(job_id, [])
    await _set_status(job_id, "running")

    try:
        async with get_session_factory()() as session:
            provider, model = await resolve_model(
                session,
                provider_config_id=req.model.provider_config_id,
                provider=req.model.provider,
                name=req.model.name,
                settings=settings,
            )
    except Exception as exc:  # noqa: BLE001 - 整批级失败：无 provider 就无从改写
        message = (
            f"{exc.code}: {exc.message}"
            if isinstance(exc, ProviderError)
            else f"{type(exc).__name__}: {exc}"
        )
        for row in rows:
            if row["status"] == "pending":
                row["status"] = "failed"
                row["error"] = message
        await _save_results(job_id)
        await _set_status(job_id, "failed", error=message)
        return

    style = get_style(req.styles[0])
    sem = asyncio.Semaphore(max(1, settings.batch_concurrency))

    # 回填真实模型名（用户看到的是"这次到底用的哪个模型"）
    await _set_model(job_id, model)

    async def _one(idx: int, item: BatchItemIn) -> None:
        row = rows[idx]
        async with sem:
            row["status"] = "running"
            try:
                before = analyze(item.text)
                outcome = await rewrite_one(
                    item.text,
                    style,  # type: ignore[arg-type]
                    before.lang,
                    provider,
                    model,
                    score_before=before.score,
                    use_gate=req.gate,
                )
                row.update(
                    status="ok",
                    text=outcome.text,
                    score_before=outcome.score_before,
                    score_after=outcome.score_after,
                    delta=outcome.delta,
                    gate=outcome.gate,
                    gate_reason=outcome.gate_reason,
                    attempts=outcome.attempts,
                    error=None,
                )
                await _record_history(
                    session=None,
                    text=item.text,
                    lang=before.lang,
                    style=style.id,  # type: ignore[union-attr]
                    model=outcome.model,
                    score_before=outcome.score_before,
                    score_after=outcome.score_after,
                )
            except ProviderError as exc:
                row.update(status="failed", error=f"{exc.code}: {exc.message}")
            except Exception as exc:  # noqa: BLE001 - 单条失败不得中断整批
                row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            finally:
                # 每条出结果就落库：刷新页面立刻看到真实进度
                await _save_results(job_id)

    await asyncio.gather(*(_one(i, item) for i, item in enumerate(req.items)))

    failed = sum(1 for r in rows if r["status"] == "failed")
    await _save_results(job_id)
    if failed < len(rows):
        await _set_status(job_id, "done")
    else:
        # 全批失败：给一条整批级原因，避免前端只看到「失败」却不知为何
        first = next((r["error"] for r in rows if r.get("error")), None)
        summary = f"全部 {len(rows)} 条均失败"
        await _set_status(job_id, "failed", error=f"{summary}：{first}" if first else summary)


async def _record_history(
    *,
    session: AsyncSession | None,
    text: str,
    lang: str,
    style: str,
    model: str,
    score_before: int,
    score_after: int,
) -> None:
    """批量条目的历史落库：用独立会话，失败不影响任务本身。"""
    try:
        async with get_session_factory()() as own:
            await history_svc.record(
                own,
                text=text,
                lang=lang,
                style=style,
                model=model,
                score_before=score_before,
                score_after=score_after,
                store_text=False,  # 批量任务不提供原文落库选项（§8.2）
            )
    except Exception:  # noqa: BLE001 - 历史是非关键路径
        pass


async def get_job(
    session: AsyncSession, job_id: str
) -> tuple[BatchJob | None, list[dict[str, Any]]]:
    """取任务行 + 合并进程内正文；正文缺失时按 DB 摘要降级。"""
    job = await session.get(BatchJob, job_id)
    if job is None:
        return None, []
    rows = _RESULTS.get(job_id)
    if rows is not None:
        return job, rows
    # 进程重启后的旧任务：只有摘要，没有正文
    import json

    try:
        stored = json.loads(job.results_json) if job.results_json else []
    except ValueError:
        stored = []
    # 返回副本：调用方不得改动进程内状态
    return job, [dict(r) for r in stored]


async def reconcile_interrupted() -> int:
    """启动时把上次进程遗留的 queued/running 任务标成 failed。

    没有这一步，任务会永远停在「运行中」，前端无限轮询。
    """
    async with get_session_factory()() as session:
        rows = list(
            await session.scalars(
                select(BatchJob).where(BatchJob.status.in_(("queued", "running")))
            )
        )
        for job in rows:
            job.status = "failed"
            job.error = "服务重启，任务中断（批量结果仅存于进程内存）"
        if rows:
            await session.commit()
        return len(rows)


def in_memory_jobs() -> int:
    """当前进程内缓存的任务数（health / 调试用）。"""
    return len(_RESULTS)
