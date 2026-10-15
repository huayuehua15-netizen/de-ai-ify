"""维度 6：模板句式（template）——固定骨架正则，词库层为正则。"""

from deaiify.engine.detectors.base import Context, DetectorResult, clamp, finding
from deaiify.engine.lexicon import find_patterns


def detect(ctx: Context) -> DetectorResult:
    pats = ctx.lexicon.patterns.get("templates", [])
    hits = find_patterns(ctx.text, pats)
    per100 = len(hits) * ctx.per100
    score = clamp(per100 * 100)

    findings = [
        finding(
            ctx,
            "template",
            start,
            end,
            reason=f"模板句式“{ctx.text[start:end]}”，机械感的直接来源",
            suggestion="用自己的话重写：先给结论和事实，去掉固定骨架",
            severity="high",
        )
        for start, end, _ in hits
    ]
    return DetectorResult(
        score=score,
        findings=findings,
        explanation=f"命中模板句式 {len(hits)} 处（每百字 {per100:.1f}）",
    )
