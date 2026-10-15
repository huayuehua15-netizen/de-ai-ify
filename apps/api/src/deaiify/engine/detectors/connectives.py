"""维度 3：连接词密度（connectives）。"""

from deaiify.engine.detectors.base import Context, DetectorResult, clamp, finding
from deaiify.engine.lexicon import find_literal

# 每句 0.10 次以下不计；每句 0.50 次判高（corpus 校准）
_BASELINE = 0.10
_SATURATION = 0.50


def detect(ctx: Context) -> DetectorResult:
    terms = ctx.lexicon.hit_terms("connectives")
    hits = find_literal(ctx.text, terms, casefold=ctx.lang == "en")
    ratio = len(hits) / max(ctx.n_sentences, 1)
    score = clamp((ratio - _BASELINE) / (_SATURATION - _BASELINE) * 100)

    findings = [
        finding(
            ctx,
            "connectives",
            start,
            end,
            reason=f"连接词“{ctx.text[start:end]}”，此处未必需要显式过渡",
            suggestion="试着删掉它直接接下一句，或与前句合并",
            severity="low",
        )
        for start, end, _ in hits
    ]
    return DetectorResult(
        score=score,
        findings=findings,
        explanation=f"连接词 {len(hits)} 处 / {ctx.n_sentences} 句（{ratio:.2f} 次/句）",
    )
