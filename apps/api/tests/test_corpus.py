"""金标准语料回归（M1 验收门槛，见 corpus/README.md 与 docs §13.1）。"""

import re
from pathlib import Path

from deaiify.engine import analyze

_CORPUS_DIR = Path(__file__).resolve().parents[3] / "corpus"
_SPLIT = re.compile(r"\n-{3,}\n")

AI_MEAN_MIN = 65.0
HUMAN_MEAN_MAX = 35.0
# 宽松的个体界：抓双峰/错分，不苛求每篇完美
AI_INDIVIDUAL_MIN = 45
HUMAN_INDIVIDUAL_MAX = 55


def _load(kind: str, lang: str) -> list[str]:
    path = _CORPUS_DIR / f"{kind}-{lang}.txt"
    if not path.exists():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    blocks = [b.strip() for b in _SPLIT.split("\n".join(lines))]
    return [b for b in blocks if b]


def _load_kind(kind: str) -> list[str]:
    return _load(kind, "zh") + _load(kind, "en")


AI_SAMPLES = _load_kind("ai")
HUMAN_SAMPLES = _load_kind("human")

AI_SCORES = [analyze(t).score for t in AI_SAMPLES]
HUMAN_SCORES = [analyze(t).score for t in HUMAN_SAMPLES]


def _mean(values: list[int]) -> float:
    return sum(values) / len(values)


def test_corpus_size() -> None:
    assert len(AI_SAMPLES) >= 50, f"AI 样本仅 {len(AI_SAMPLES)} 篇"
    assert len(HUMAN_SAMPLES) >= 50, f"人写样本仅 {len(HUMAN_SAMPLES)} 篇"


def test_ai_corpus_mean() -> None:
    mean = _mean(AI_SCORES)
    assert mean >= AI_MEAN_MIN, (
        f"AI 均分 {mean:.1f} < {AI_MEAN_MIN}；最低 5 篇: {sorted(AI_SCORES)[:5]}"
    )


def test_human_corpus_mean() -> None:
    mean = _mean(HUMAN_SCORES)
    worst = sorted(HUMAN_SCORES, reverse=True)[:5]
    assert mean <= HUMAN_MEAN_MAX, f"人写均分 {mean:.1f} > {HUMAN_MEAN_MAX}；最高 5 篇: {worst}"


def test_individual_bounds() -> None:
    min_ai = min(AI_SCORES)
    max_human = max(HUMAN_SCORES)
    assert min_ai >= AI_INDIVIDUAL_MIN, f"最低 AI 样本 {min_ai} 分，疑似欠拟合"
    assert max_human <= HUMAN_INDIVIDUAL_MAX, f"最高人写样本 {max_human} 分，疑似误伤"


def test_samples_offset_invariant() -> None:
    for text in AI_SAMPLES + HUMAN_SAMPLES:
        for f in analyze(text).findings:
            assert text[f.start : f.end] == f.matched
