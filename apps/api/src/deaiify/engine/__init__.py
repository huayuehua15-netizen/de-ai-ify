"""评分引擎（纯函数、零网络依赖）——规格见 docs/DEVELOPMENT.md §5。

用法：
    from deaiify.engine import analyze
    result = analyze("……文本……")
"""

from deaiify.engine.analyze import analyze
from deaiify.engine.lexicon import Term
from deaiify.engine.models import (
    AnalysisResult,
    DimensionScore,
    Finding,
    TextStats,
)

__all__ = [
    "AnalysisResult",
    "DimensionScore",
    "Finding",
    "Term",
    "TextStats",
    "analyze",
]
