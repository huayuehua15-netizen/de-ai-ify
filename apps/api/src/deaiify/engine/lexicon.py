"""内置词库加载与匹配（四层结构见 docs/DEVELOPMENT.md §5.6）。

文件行格式：
- 字面层（cliches/connectives/vague/personal）：词条可用 `,`、`，`、`、` 分隔，`#` 为注释；
- 正则层（templates）：每行一条正则。
加载按 (layer, lang) 缓存；运行期可叠加自定义词条、屏蔽内置词条。
"""

import re
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path

_LEXDIR = Path(__file__).parent / "lexicons"

# 层名 → 是否正则
LAYERS = {
    "cliches": False,
    "connectives": False,
    "templates": True,
    "vague": False,
    "personal": False,
}

_SPLIT = re.compile(r"[,，、]")


@dataclass(frozen=True)
class Term:
    """一条词库词条。

    match_mode（M4 自定义词条，docs §5.6）：
    - contains：子串匹配（内置词条与默认）；
    - exact：子串匹配且边界不得是 ASCII 单词字符（"AI" 不命中 "SAID"；中文无词边界）；
    - regex：编译后经 compiled 字段执行（build_lexicon 编译一次，热路径不现场编译）。
    """

    text: str
    layer: str
    weight: float = 1.0
    match_mode: str = "contains"
    replacement: str | None = None
    compiled: re.Pattern[str] | None = None


@dataclass
class LexiconSet:
    """一次分析使用的词库快照。"""

    literal: dict[str, list[Term]] = field(default_factory=dict)  # layer → terms
    patterns: dict[str, list[tuple[str, re.Pattern[str]]]] = field(default_factory=dict)

    def hit_terms(self, layer: str) -> list[Term]:
        return self.literal.get(layer, [])


@cache
def _read_entries(layer: str, lang: str) -> tuple[str, ...]:
    path = _LEXDIR / f"{layer}.{lang}.txt"
    if not path.exists():
        return ()
    is_regex = LAYERS[layer]
    entries: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if is_regex:
            entries.append(line)
        else:
            entries.extend(part.strip() for part in _SPLIT.split(line) if part.strip())
    return tuple(entries)


def built_in_count() -> int:
    """内置词条总数（含正则层条数），供自检与文档核对。"""
    return sum(len(_read_entries(layer, lang)) for layer in LAYERS for lang in ("zh", "en"))


def build_lexicon(
    lang: str,
    extra_terms: list[Term] | None = None,
    disabled: set[str] | None = None,
) -> LexiconSet:
    """合并内置与自定义词条；disabled 中的内置词条被剔除。"""
    disabled = disabled or set()
    ls = LexiconSet()
    for layer, is_regex in LAYERS.items():
        if is_regex:
            pats: list[tuple[str, re.Pattern[str]]] = []
            for line in _read_entries(layer, lang):
                if line in disabled:
                    continue
                try:
                    pats.append((line, re.compile(line, re.IGNORECASE)))
                except re.error:
                    continue  # 内置正则坏行不致命
            ls.patterns[layer] = pats
        else:
            terms = [
                Term(entry, layer) for entry in _read_entries(layer, lang) if entry not in disabled
            ]
            ls.literal[layer] = terms
    # 自定义词条并入其所属层（DB 词库服务 M4 接同一入口）
    for term in extra_terms or []:
        if term.match_mode == "regex" and LAYERS.get(term.layer, False):
            # 正则层（templates）：与内置正则同路径
            try:
                ls.patterns.setdefault(term.layer, []).append(
                    (term.text, re.compile(term.text, re.IGNORECASE))
                )
            except re.error:
                continue
        elif term.match_mode == "regex":
            # 字面层的自定义正则：预编译挂到 Term 上，find_literal 统一执行
            # （避免热路径现场编译，也让所有检测器自动支持）
            try:
                compiled = re.compile(term.text, re.IGNORECASE)
            except re.error:
                continue
            ls.literal.setdefault(term.layer, []).append(replace(term, compiled=compiled))
        else:
            ls.literal.setdefault(term.layer, []).append(term)
    return ls


def find_literal(
    text: str, terms: list[Term], *, casefold: bool = False
) -> list[tuple[int, int, Term]]:
    """查找所有字面词条命中，返回 (start, end, term) 并按位置排序。

    casefold 用于英文：在小写副本上匹配，ASCII 大小写不改变偏移。
    match_mode=exact 额外要求命中边界不是 ASCII 单词字符（自定义词条，M4）。
    """
    hay = text.lower() if casefold else text
    hits: list[tuple[int, int, Term]] = []
    seen: set[tuple[int, int]] = set()
    for term in terms:
        if term.compiled is not None:
            # 自定义正则词条：在原文上执行（IGNORECASE 编译时已带）
            for m in term.compiled.finditer(text):
                if m.end() <= m.start():
                    continue
                key = (m.start(), m.end())
                if key not in seen:
                    seen.add(key)
                    hits.append((m.start(), m.end(), term))
            continue
        needle = term.text.lower() if casefold else term.text
        if not needle:
            continue
        pos = hay.find(needle)
        while pos != -1:
            key = (pos, pos + len(needle))
            if key not in seen and (
                term.match_mode != "exact" or _word_boundary_ok(hay, pos, pos + len(needle))
            ):
                seen.add(key)
                hits.append((pos, pos + len(needle), term))
            pos = hay.find(needle, pos + 1)
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits


def _word_boundary_ok(hay: str, start: int, end: int) -> bool:
    """exact 模式：命中两端不得紧邻 ASCII 单词字符（中文无词边界，视作通过）。"""
    word = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")

    def adjacent(ch: str) -> bool:
        return bool(ch) and ch in word

    return not ((start > 0 and adjacent(hay[start - 1])) or (end < len(hay) and adjacent(hay[end])))


def find_patterns(text: str, pats: list[tuple[str, re.Pattern[str]]]) -> list[tuple[int, int, str]]:
    """正则层命中（templates 等），按位置排序。"""
    hits: list[tuple[int, int, str]] = []
    for pattern_str, pat in pats:
        for m in pat.finditer(text):
            if m.end() > m.start():
                hits.append((m.start(), m.end(), pattern_str))
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits
