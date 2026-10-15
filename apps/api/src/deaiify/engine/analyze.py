"""评分编排：跑八个检测器 → 合并高亮 → 加权总分（docs/DEVELOPMENT.md §5.3-5.5）。"""

import json
from functools import lru_cache
from pathlib import Path

from deaiify.engine.detectors import DETECTORS
from deaiify.engine.detectors.base import Context, clamp
from deaiify.engine.lexicon import Term, build_lexicon
from deaiify.engine.models import (
    BAND_LABELS,
    AnalysisResult,
    DimensionScore,
    Finding,
    TextStats,
    band_of,
)
from deaiify.engine.segment import (
    count_words,
    detect_lang,
    mean_std,
    paragraphs_of,
    split_sentences,
)
from deaiify.engine.version import ENGINE_VERSION

_WEIGHTS_PATH = Path(__file__).parent / "weights.json"
_SEVERITY_RANK = {"high": 0, "mid": 1, "low": 2}
_MAX_FINDINGS = 200


@lru_cache(maxsize=1)
def load_weights() -> dict[str, float]:
    """加载权重并归一化（保证 Σw = 1，调参后无需手工配平）。"""
    data: dict[str, float] = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
    total = sum(data.values())
    if total <= 0:
        raise ValueError("weights.json 权重和必须为正")
    return {key: value / total for key, value in data.items()}


def _merge_findings(text: str, findings: list[Finding]) -> list[Finding]:
    """按 severity 优先去重重叠（同区间保留更严重者）、回校原文切片、截断 200 条。"""
    ordered = sorted(
        findings,
        key=lambda f: (_SEVERITY_RANK.get(f.severity, 1), f.start, f.end),
    )
    accepted: list[Finding] = []
    for cand in ordered:
        # 不变式：text[start:end] == matched，不满足则丢弃（防未来改动引入偏移错位）
        if text[cand.start : cand.end] != cand.matched:
            continue
        if any(cand.start < acc.end and acc.start < cand.end for acc in accepted):
            continue  # 与更高 severity 的已接受项重叠 → 合并（保留严重者）
        accepted.append(cand)
        if len(accepted) >= _MAX_FINDINGS:
            break
    accepted.sort(key=lambda f: (f.start, f.end))
    return accepted


def _confidence(chars: int) -> str:
    if chars < 120:
        return "low"
    if chars < 300:
        return "medium"
    return "high"


def analyze(
    text: str,
    *,
    lang: str = "auto",
    extra_terms: list[Term] | None = None,
    disabled: set[str] | None = None,
) -> AnalysisResult:
    """对文本做 AI 味评分与高亮——纯本地、零网络依赖（M1 核心入口）。"""
    if not text or not text.strip():
        raise ValueError("文本为空")

    resolved_lang = detect_lang(text) if lang == "auto" else lang
    sentences = split_sentences(text)
    chars = sum(1 for c in text if not c.isspace())
    lexicon = build_lexicon(resolved_lang, extra_terms, disabled)

    ctx = Context(
        text=text,
        lang=resolved_lang,
        sentences=sentences,
        tokens=[],
        lexicon=lexicon,
        chars=chars,
    )

    weights = load_weights()
    dimensions: list[DimensionScore] = []
    all_findings: list[Finding] = []
    total = 0.0
    for dim_id, name, inverted, detector in DETECTORS:
        result = detector(ctx)
        score = clamp(result.score)
        total += weights.get(dim_id, 0.0) * score
        dimensions.append(
            DimensionScore(
                id=dim_id,
                name=name,
                score=score,
                inverted=inverted,
                explanation=result.explanation,
            )
        )
        all_findings.extend(result.findings)

    score = clamp(total)
    band = band_of(score)

    lengths = [float(len(s.text)) for s in sentences] or [0.0]
    mean, std = mean_std(lengths)
    cv = std / mean if mean else 0.0

    return AnalysisResult(
        score=score,
        band=band,
        band_label=BAND_LABELS[band],
        dimensions=dimensions,
        findings=_merge_findings(text, all_findings),
        stats=TextStats(
            chars=chars,
            sentences=len(sentences),
            words=count_words(text, resolved_lang),
            paragraphs=len(paragraphs_of(text)),
            sent_len_mean=round(mean, 1),
            sent_len_std=round(std, 1),
            sent_len_cv=round(cv, 3),
            confidence=_confidence(chars),
            lang=resolved_lang,
        ),
        lang=resolved_lang,
        engine_version=ENGINE_VERSION,
    )
