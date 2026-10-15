"""检测器注册表：维度顺序与展示名（权重见 weights.json）。"""

from collections.abc import Callable

from deaiify.engine.detectors import (
    cliche,
    connectives,
    nominalization,
    personal,
    repetition,
    template,
    uniformity,
    vagueness,
)
from deaiify.engine.detectors.base import Context, DetectorResult

Detector = Callable[[Context], DetectorResult]

# (维度 id, 展示名, 是否反向计分, 检测器)
DETECTORS: list[tuple[str, str, bool, Detector]] = [
    ("cliche", "套话密度", False, cliche.detect),
    ("uniformity", "句长均匀度", False, uniformity.detect),
    ("connectives", "连接词密度", False, connectives.detect),
    ("nominalization", "名词化倾向", False, nominalization.detect),
    ("repetition", "结构重复", False, repetition.detect),
    ("template", "模板句式", False, template.detect),
    ("vagueness", "空泛度（信息不足）", True, vagueness.detect),
    ("personal", "个性化信号", True, personal.detect),
]
