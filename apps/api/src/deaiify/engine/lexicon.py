"""内置词库加载与匹配（四层结构见 docs/DEVELOPMENT.md §5.6）。

文件行格式：
- 字面层（cliches/connectives/vague/personal）：词条可用 `,`、`，`、`、` 分隔，`#` 为注释；
- 正则层（templates）：每行一条正则。
加载按 (layer, lang) 缓存；运行期可叠加自定义词条、屏蔽内置词条。
"""

import re
from dataclasses import dataclass, field
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
    """一条词库词条。"""

    text: str
    layer: str
    weight: float = 1.0


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
        ls.literal.setdefault(term.layer, []).append(term)
    return ls


def find_literal(
    text: str, terms: list[Term], *, casefold: bool = False
) -> list[tuple[int, int, Term]]:
    """查找所有字面词条命中，返回 (start, end, term) 并按位置排序。

    casefold 用于英文：在小写副本上匹配，ASCII 大小写不改变偏移。
    """
    hay = text.lower() if casefold else text
    hits: list[tuple[int, int, Term]] = []
    seen: set[tuple[int, int]] = set()
    for term in terms:
        needle = term.text.lower() if casefold else term.text
        if not needle:
            continue
        pos = hay.find(needle)
        while pos != -1:
            key = (pos, pos + len(needle))
            if key not in seen:
                seen.add(key)
                hits.append((pos, pos + len(needle), term))
            pos = hay.find(needle, pos + 1)
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits


def find_patterns(text: str, pats: list[tuple[str, re.Pattern[str]]]) -> list[tuple[int, int, str]]:
    """正则层命中（templates 等），按位置排序。"""
    hits: list[tuple[int, int, str]] = []
    for pattern_str, pat in pats:
        for m in pat.finditer(text):
            if m.end() > m.start():
                hits.append((m.start(), m.end(), pattern_str))
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits
