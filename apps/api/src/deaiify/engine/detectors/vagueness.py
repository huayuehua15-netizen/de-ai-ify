"""维度 7：空泛度（vagueness，反向）——具体信号越少分越高。"""

import re

from deaiify.engine.detectors.base import Context, DetectorResult, clamp
from deaiify.engine.lexicon import find_literal

_NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*%?")
_PROPER_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
_QUOTED_RE = re.compile(r"[《「“][^》」”\n]{1,40}[》」”]")

# 句首常见大写词不算专名
_EN_STOP = {
    "the",
    "this",
    "that",
    "with",
    "for",
    "and",
    "but",
    "not",
    "all",
    "can",
    "will",
    "one",
    "two",
    "how",
    "why",
    "when",
    "what",
    "where",
    "who",
    "are",
    "its",
    "it's",
    "from",
    "into",
    "than",
    "then",
    "these",
    "those",
    "have",
    "has",
    "had",
    "was",
    "were",
    "been",
    "being",
    "may",
    "might",
    "must",
    "should",
    "would",
    "could",
    "also",
    "after",
    "before",
    "during",
}

# 每百字 3.3 个具体信号即认为足够具体
_DENSITY_GAIN = 30.0
# 空泛词（vague 词表）每百字命中的加成权重
_VAGUE_HIT_GAIN = 6.0


def detect(ctx: Context) -> DetectorResult:
    text = ctx.text
    digits = _NUM_RE.findall(text)
    quoted = _QUOTED_RE.findall(text)
    proper = [w for w in _PROPER_RE.findall(text) if w.lower() not in _EN_STOP]

    vague_terms = ctx.lexicon.hit_terms("vague")
    vague_hits = len(find_literal(text, vague_terms, casefold=ctx.lang == "en"))

    signals = len(digits) + len(proper) + 2 * len(quoted)
    density = signals * ctx.per100
    # 具体信号压低分；空泛词命中抬高分（"空泛度"= 信息不足程度）
    score = clamp(100 - density * _DENSITY_GAIN + vague_hits * ctx.per100 * _VAGUE_HIT_GAIN)

    return DetectorResult(
        score=score,
        findings=[],
        explanation=(
            f"具体信号 {signals} 处（数字 {len(digits)}、专名 {len(proper)}、"
            f"引文 {len(quoted)}）、空泛词 {vague_hits} 处"
        ),
    )
