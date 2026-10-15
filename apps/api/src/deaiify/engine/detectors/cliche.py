"""维度 1：套话密度（cliche）。"""

from deaiify.engine.detectors.base import Context, DetectorResult, clamp, finding
from deaiify.engine.lexicon import find_literal


def detect(ctx: Context) -> DetectorResult:
    terms = ctx.lexicon.hit_terms("cliches")
    hits = find_literal(ctx.text, terms, casefold=ctx.lang == "en")
    per100 = len(hits) * ctx.per100
    score = clamp(per100 * 62)

    findings = [
        finding(
            ctx,
            "cliche",
            start,
            end,
            reason=f"套话短语“{ctx.text[start:end]}”，读者已对这类表达免疫",
            suggestion="删掉，或换成具体的事实、数字或你自己的结论",
            severity="high" if end - start >= 6 else "mid",
        )
        for start, end, _ in hits
    ]
    return DetectorResult(
        score=score,
        findings=findings,
        explanation=f"命中套话 {len(hits)} 处（每百字 {per100:.1f}）",
    )
