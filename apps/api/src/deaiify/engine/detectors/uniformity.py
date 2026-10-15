"""维度 2：句长均匀度（uniformity）——句长变异系数越低越 AI。"""

from deaiify.engine.detectors.base import Context, DetectorResult, clamp
from deaiify.engine.segment import mean_std

# corpus 校准：CV ≥ 0.55 视为自然起伏；CV → 0.15（典型 AI）得分 → 100
_REF_CV = 0.55
_SPAN = 0.35


def detect(ctx: Context) -> DetectorResult:
    lengths = [len(s.text) for s in ctx.sentences]
    if len(lengths) < 3:
        return DetectorResult(
            score=0.0,
            findings=[],
            explanation=f"样本句数不足（{len(lengths)} < 3），不计句长均匀度",
        )
    mean, std = mean_std([float(v) for v in lengths])
    cv = std / mean if mean else 0.0
    score = clamp((_REF_CV - cv) / _SPAN * 100)
    return DetectorResult(
        score=score,
        findings=[],
        explanation=(
            f"句长均值 {mean:.0f} 字、变异系数 {cv:.2f}（CV < 0.40 说明句长过于均匀，像机器排版）"
        ),
    )
