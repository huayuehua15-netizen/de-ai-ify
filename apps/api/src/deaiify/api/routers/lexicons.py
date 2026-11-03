"""词库端点（docs §7.1）：

GET/POST     /lexicons                列表 / 创建（可带初始词条）
GET/PATCH/DELETE /lexicons/{id}       读取 / 改名 / 删除（级联删词条）
POST         /lexicons/{id}/terms     追加词条
DELETE       /lexicons/{id}/terms/{tid}  删单条
POST         /lexicons/{id}/import    CSV/JSON 导入（body: {format, content}）
GET          /lexicons/{id}/export    导出（?format=csv|json）
GET          /lexicons/builtin        内置词库统计 + 已停用清单
PUT          /lexicons/builtin/disabled  批量停用/恢复内置词条
"""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from deaiify.api.errors import ApiError
from deaiify.db.session import get_session
from deaiify.engine.lexicon import built_in_count
from deaiify.services import lexicons as svc

router = APIRouter()


class TermIn(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    layer: str = "cliches"
    match_mode: Literal["exact", "regex", "contains"] = "exact"
    weight: float = Field(default=1.0, gt=0, le=10)
    replacement: str | None = None
    enabled: bool = True


class LexiconCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    lang: Literal["zh", "en"] = "zh"
    terms: list[TermIn] = Field(default_factory=list, max_length=500)


class LexiconPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    lang: Literal["zh", "en"] | None = None


class TermsIn(BaseModel):
    terms: list[TermIn] = Field(min_length=1, max_length=500)


class ImportIn(BaseModel):
    format: Literal["csv", "json"] = "csv"
    content: str = Field(min_length=1)


class DisabledIn(BaseModel):
    terms: list[str] = Field(min_length=1, max_length=200)
    disabled: bool = True


class TermOut(BaseModel):
    id: str
    term: str
    layer: str
    match_mode: str
    weight: float
    replacement: str | None
    enabled: bool


class LexiconOut(BaseModel):
    id: str
    name: str
    description: str | None
    lang: str
    terms: list[TermOut] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


def _out(lex) -> LexiconOut:  # noqa: ANN001 - SQLAlchemy 实例
    return LexiconOut(
        id=lex.id,
        name=lex.name,
        description=lex.description,
        lang=lex.lang,
        terms=[
            TermOut(
                id=t.id,
                term=t.term,
                layer=t.layer,
                match_mode=t.match_mode,
                weight=t.weight,
                replacement=t.replacement,
                enabled=t.enabled,
            )
            for t in sorted(lex.terms, key=lambda x: x.created_at)
        ],
        created_at=lex.created_at.isoformat() if lex.created_at else None,
        updated_at=lex.updated_at.isoformat() if lex.updated_at else None,
    )


@router.get("/lexicons", response_model=list[LexiconOut], summary="词库列表")
async def list_lexicons(session: AsyncSession = Depends(get_session)) -> list[LexiconOut]:
    return [_out(x) for x in await svc.list_lexicons(session)]


@router.post("/lexicons", response_model=LexiconOut, status_code=201, summary="创建词库")
async def create_lexicon(
    body: LexiconCreateIn, session: AsyncSession = Depends(get_session)
) -> LexiconOut:
    lex = await svc.create_lexicon(
        session,
        name=body.name,
        description=body.description,
        lang=body.lang,
        terms=[t.model_dump() for t in body.terms],
    )
    return _out(lex)


@router.get("/lexicons/builtin", summary="内置词库统计与停用清单")
async def builtin_info(session: AsyncSession = Depends(get_session)) -> dict:
    return {
        "total": built_in_count(),
        "disabled": await svc.list_disabled(session),
    }


@router.put("/lexicons/builtin/disabled", summary="批量停用/恢复内置词条")
async def set_builtin_disabled(
    body: DisabledIn, session: AsyncSession = Depends(get_session)
) -> dict:
    return {"disabled": await svc.set_disabled(session, body.terms, body.disabled)}


@router.get("/lexicons/{lexicon_id}", response_model=LexiconOut, summary="词库详情")
async def get_lexicon(lexicon_id: str, session: AsyncSession = Depends(get_session)) -> LexiconOut:
    return _out(await svc.get_lexicon(session, lexicon_id))


@router.patch("/lexicons/{lexicon_id}", response_model=LexiconOut, summary="修改词库元信息")
async def update_lexicon(
    lexicon_id: str, body: LexiconPatchIn, session: AsyncSession = Depends(get_session)
) -> LexiconOut:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise ApiError("invalid_request", "没有可更新的字段", 400)
    return _out(await svc.update_lexicon(session, lexicon_id, patch))


@router.delete("/lexicons/{lexicon_id}", status_code=204, summary="删除词库（级联删词条）")
async def delete_lexicon(lexicon_id: str, session: AsyncSession = Depends(get_session)) -> None:
    await svc.delete_lexicon(session, lexicon_id)


@router.post("/lexicons/{lexicon_id}/terms", response_model=LexiconOut, summary="追加词条")
async def add_terms(
    lexicon_id: str, body: TermsIn, session: AsyncSession = Depends(get_session)
) -> LexiconOut:
    await svc.add_terms(session, lexicon_id, [t.model_dump() for t in body.terms])
    return _out(await svc.get_lexicon(session, lexicon_id))


@router.delete("/lexicons/{lexicon_id}/terms/{term_id}", status_code=204, summary="删除单条词条")
async def delete_term(
    lexicon_id: str, term_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    await svc.delete_term(session, lexicon_id, term_id)


@router.post("/lexicons/{lexicon_id}/import", response_model=LexiconOut, summary="导入词条")
async def import_terms(
    lexicon_id: str, body: ImportIn, session: AsyncSession = Depends(get_session)
) -> LexiconOut:
    rows = svc.parse_import(body.content, body.format)
    await svc.add_terms(session, lexicon_id, rows)
    return _out(await svc.get_lexicon(session, lexicon_id))


@router.get("/lexicons/{lexicon_id}/export", summary="导出词库（CSV/JSON）")
async def export_lexicon(
    lexicon_id: str,
    format: Literal["csv", "json"] = Query(default="json"),  # noqa: A002 - 对外契约名
    session: AsyncSession = Depends(get_session),
):
    lex = await svc.get_lexicon(session, lexicon_id)
    if format == "csv":
        return PlainTextResponse(
            svc.export_csv(lex),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="lexicon-{lex.id}.csv"'},
        )
    return PlainTextResponse(
        svc.export_json(lex),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="lexicon-{lex.id}.json"'},
    )
