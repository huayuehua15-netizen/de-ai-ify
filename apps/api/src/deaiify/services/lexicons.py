"""词库服务：自定义词库 CRUD、CSV/JSON 导入导出、内置词条停用（docs §5.6、§7.1）。

DB 记录 ↔ 引擎 Term 的桥接在这里完成：match_mode/replacement/weight 一并映射，
disabled_terms 表决定内置词条是否参与评分（写入引擎 build_lexicon 的 disabled 集）。
"""

import csv
import io
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from deaiify.api.errors import ApiError
from deaiify.db.models import DisabledTerm, Lexicon, LexiconTerm
from deaiify.engine.lexicon import LAYERS, Term

# 引擎层 id（词库 term 归属哪个检测维度）
VALID_LAYERS = tuple(LAYERS.keys())
VALID_MATCH_MODES = ("exact", "regex", "contains")

_MAX_TERMS_PER_LEXICON = 500
_MAX_IMPORT_ROWS = 1000


def _new_id() -> str:
    return uuid.uuid4().hex


async def load_engine_terms(
    session: AsyncSession, lexicon_ids: list[str]
) -> tuple[list[Term], set[str]]:
    """读取所选词库的 enabled 词条 + 全部停用的内置词条，供 analyze 使用。"""
    extra: list[Term] = []
    if lexicon_ids:
        rows = await session.scalars(
            select(LexiconTerm).where(
                LexiconTerm.lexicon_id.in_(lexicon_ids), LexiconTerm.enabled.is_(True)
            )
        )
        extra = [
            Term(
                text=t.term,
                layer=t.layer,
                weight=t.weight,
                match_mode=t.match_mode,
                replacement=t.replacement,
            )
            for t in rows
        ]
    disabled = set(await session.scalars(select(DisabledTerm.term)))
    return extra, disabled


async def list_lexicons(session: AsyncSession) -> list[Lexicon]:
    result = await session.scalars(select(Lexicon).order_by(Lexicon.created_at.desc()))
    return list(result)


async def get_lexicon(session: AsyncSession, lexicon_id: str) -> Lexicon:
    lex = await session.get(Lexicon, lexicon_id)
    if lex is None:
        raise ApiError("not_found", f"词库 {lexicon_id} 不存在", 404)
    return lex


async def create_lexicon(
    session: AsyncSession,
    *,
    name: str,
    description: str | None,
    lang: str,
    terms: list[dict[str, Any]] | None = None,
) -> Lexicon:
    lex = Lexicon(id=_new_id(), name=name, description=description, lang=lang)
    session.add(lex)
    for raw in terms or []:
        session.add(_term_row(lex.id, raw))
    await session.commit()
    await session.refresh(lex)
    return lex


def _term_row(lexicon_id: str, raw: dict[str, Any]) -> LexiconTerm:
    term = str(raw.get("term", "")).strip()
    if not term:
        raise ApiError("invalid_term", "词条 term 不能为空", 400)
    layer = str(raw.get("layer", "cliches"))
    if layer not in VALID_LAYERS:
        raise ApiError("invalid_term", f"未知层 {layer}（可用：{'/'.join(VALID_LAYERS)}）", 400)
    mode = str(raw.get("match_mode", "exact"))
    if mode not in VALID_MATCH_MODES:
        raise ApiError(
            "invalid_term", f"未知 match_mode {mode}（可用：{'/'.join(VALID_MATCH_MODES)}）", 400
        )
    if mode == "regex":
        import re

        try:
            re.compile(term)
        except re.error as exc:
            raise ApiError("invalid_term", f"正则不合法：{exc}", 400) from exc
    weight = float(raw.get("weight", 1.0))
    if not 0.0 < weight <= 10.0:
        raise ApiError("invalid_term", "weight 须在 (0, 10] 区间", 400)
    return LexiconTerm(
        id=_new_id(),
        lexicon_id=lexicon_id,
        term=term,
        match_mode=mode,
        weight=weight,
        replacement=(str(raw["replacement"]) if raw.get("replacement") else None),
        enabled=bool(raw.get("enabled", True)),
    )


async def add_terms(session: AsyncSession, lexicon_id: str, terms: list[dict[str, Any]]) -> int:
    await get_lexicon(session, lexicon_id)
    existing = await session.scalars(
        select(LexiconTerm).where(LexiconTerm.lexicon_id == lexicon_id)
    )
    count = len(list(existing)) + len(terms)
    if count > _MAX_TERMS_PER_LEXICON:
        raise ApiError(
            "terms_limit", f"单个词库最多 {_MAX_TERMS_PER_LEXICON} 条（当前将达 {count}）", 400
        )
    for raw in terms:
        session.add(_term_row(lexicon_id, raw))
    await session.commit()
    return len(terms)


async def update_lexicon(session: AsyncSession, lexicon_id: str, patch: dict[str, Any]) -> Lexicon:
    lex = await get_lexicon(session, lexicon_id)
    if "name" in patch and patch["name"]:
        lex.name = str(patch["name"])
    if "description" in patch:
        lex.description = patch["description"] or None
    if "lang" in patch and patch["lang"]:
        lex.lang = str(patch["lang"])
    await session.commit()
    await session.refresh(lex)
    return lex


async def delete_lexicon(session: AsyncSession, lexicon_id: str) -> None:
    await get_lexicon(session, lexicon_id)
    await session.execute(delete(LexiconTerm).where(LexiconTerm.lexicon_id == lexicon_id))
    await session.execute(delete(Lexicon).where(Lexicon.id == lexicon_id))
    await session.commit()


async def delete_term(session: AsyncSession, lexicon_id: str, term_id: str) -> None:
    row = await session.get(LexiconTerm, term_id)
    if row is None or row.lexicon_id != lexicon_id:
        raise ApiError("not_found", f"词条 {term_id} 不存在", 404)
    await session.delete(row)
    await session.commit()


# —— 导入 / 导出 ——


def parse_import(payload: str, fmt: str) -> list[dict[str, Any]]:
    """CSV/JSON 导入体 → 词条 dict 列表（统一校验交给 _term_row）。"""
    rows: list[dict[str, Any]] = []
    if fmt == "json":
        import json

        try:
            data = json.loads(payload)
        except ValueError as exc:
            raise ApiError("invalid_import", f"JSON 解析失败：{exc}", 400) from exc
        if isinstance(data, dict) and "terms" in data:
            data = data["terms"]
        if not isinstance(data, list):
            raise ApiError("invalid_import", "JSON 须为数组或 {terms:[...]} 对象", 400)
        rows = [r for r in data if isinstance(r, dict)]
    else:  # csv
        try:
            reader = csv.DictReader(io.StringIO(payload))
            rows = [dict(r) for r in reader]
        except csv.Error as exc:
            raise ApiError("invalid_import", f"CSV 解析失败：{exc}", 400) from exc
    if not rows:
        raise ApiError("invalid_import", "导入内容为空", 400)
    if len(rows) > _MAX_IMPORT_ROWS:
        raise ApiError(
            "invalid_import", f"单次最多导入 {_MAX_IMPORT_ROWS} 条（收到 {len(rows)}）", 400
        )
    # CSV 全是字符串：归一化数值/布尔
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        row = {k: v for k, v in raw.items() if v not in (None, "")}
        if "weight" in row:
            try:
                row["weight"] = float(row["weight"])
            except (TypeError, ValueError) as exc:
                raise ApiError("invalid_import", f"weight 非数字：{row['weight']}", 400) from exc
        if "enabled" in row:
            row["enabled"] = str(row["enabled"]).lower() not in {"0", "false", "no"}
        normalized.append(row)
    return normalized


def export_json(lex: Lexicon) -> str:
    import json

    return json.dumps(
        {
            "name": lex.name,
            "description": lex.description,
            "lang": lex.lang,
            "terms": [
                {
                    "term": t.term,
                    "layer": t.layer,
                    "match_mode": t.match_mode,
                    "weight": t.weight,
                    "replacement": t.replacement,
                    "enabled": t.enabled,
                }
                for t in sorted(lex.terms, key=lambda x: x.created_at)
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def export_csv(lex: Lexicon) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["term", "layer", "match_mode", "weight", "replacement", "enabled"])
    for t in sorted(lex.terms, key=lambda x: x.created_at):
        writer.writerow(
            [t.term, t.layer, t.match_mode, t.weight, t.replacement or "", int(t.enabled)]
        )
    return buf.getvalue()


# —— 内置词条停用 ——


async def list_disabled(session: AsyncSession) -> list[str]:
    return list(await session.scalars(select(DisabledTerm.term)))


async def set_disabled(session: AsyncSession, terms: list[str], disabled: bool) -> list[str]:
    """批量停用/恢复内置词条；停用不存在的词不报错（幂等，含批内去重）。"""
    # dict.fromkeys 保序去重：同批重复词不得撞 term 的 UNIQUE 约束
    cleaned = list(dict.fromkeys(t.strip() for t in terms if t.strip()))[:200]
    if disabled:
        existing = set(
            await session.scalars(select(DisabledTerm.term).where(DisabledTerm.term.in_(cleaned)))
        )
        for term in cleaned:
            if term not in existing:
                session.add(DisabledTerm(id=_new_id(), term=term))
    else:
        await session.execute(delete(DisabledTerm).where(DisabledTerm.term.in_(cleaned)))
    await session.commit()
    return await list_disabled(session)
