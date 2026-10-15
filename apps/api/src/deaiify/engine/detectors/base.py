"""检测器公共结构：文本上下文与结果约定（docs/DEVELOPMENT.md §5.3）。"""

from collections.abc import Callable
from dataclasses import dataclass

from deaiify.engine.lexicon import LexiconSet
from deaiify.engine.models import Finding
from deaiify.engine.segment import Sentence


@dataclass
class Context:
    """一次分析的共享上下文（惰性派生字段在 analyze 中填充）。"""

    text: str
    lang: str
    sentences: list[Sentence]
    tokens: list[str]
    lexicon: LexiconSet
    chars: int  # 非空白字符数，比率分母

    @property
    def n_sentences(self) -> int:
        return len(self.sentences)

    @property
    def per100(self) -> float:
        """每百字比例因子。"""
        return 100.0 / max(self.chars, 1)


@dataclass
class DetectorResult:
    score: float  # 原始 0-100（编排层统一 clamp）
    findings: list[Finding]
    explanation: str


Detector = Callable[[Context], DetectorResult]


def clamp(value: float) -> int:
    return max(0, min(100, int(round(value))))


def finding(
    ctx: Context,
    dimension: str,
    start: int,
    end: int,
    reason: str,
    suggestion: str,
    severity: str = "mid",
) -> Finding:
    """从原文切片构造 Finding（保证 text[start:end] == matched 不变量）。"""
    return Finding(
        dimension=dimension,
        start=start,
        end=end,
        matched=ctx.text[start:end],
        reason=reason,
        suggestion=suggestion,
        severity=severity,  # type: ignore[arg-type]
    )
