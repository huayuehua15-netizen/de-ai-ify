"""维度 8：个性化信号（personal，反向）——人称/口语/问句/短句越少分越高。"""

import re

from deaiify.engine.detectors.base import Context, DetectorResult, clamp
from deaiify.engine.lexicon import find_literal

_PRON_ZH_RE = re.compile(r"我们|我|咱们|本人|笔者")
_PRON_EN_RE = re.compile(r"\b(?:I|we)\b")
_SHORT_MAX = 8  # ≤8 字视为短句
_SHORT_WEIGHT = 0.5
_PRON_WEIGHT = 1.5
_DENSITY_GAIN = 25.0


def detect(ctx: Context) -> DetectorResult:
    text = ctx.text
    pronouns = len(_PRON_ZH_RE.findall(text)) + len(_PRON_EN_RE.findall(text))

    colloq_terms = ctx.lexicon.hit_terms("personal")
    colloq = len(find_literal(text, colloq_terms, casefold=ctx.lang == "en"))

    questions = text.count("？") + text.count("?")
    short = sum(1 for s in ctx.sentences if len(s.text) <= _SHORT_MAX)

    signals = _PRON_WEIGHT * pronouns + colloq + questions + _SHORT_WEIGHT * short
    density = signals * ctx.per100
    score = clamp(100 - density * _DENSITY_GAIN)

    return DetectorResult(
        score=score,
        findings=[],
        explanation=(
            f"人味信号 {signals:.0f}（人称 {pronouns}、口语 {colloq}、"
            f"问句 {questions}、短句 {short}）"
        ),
    )
