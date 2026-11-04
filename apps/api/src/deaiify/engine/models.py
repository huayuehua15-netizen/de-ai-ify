"""评分引擎数据模型（对外契约，见 docs/DEVELOPMENT.md §5.1）。"""

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "mid", "high"]
Band = Literal["natural", "mild", "obvious", "heavy"]

BANDS: list[tuple[int, Band]] = [
    (25, "natural"),
    (50, "mild"),
    (75, "obvious"),
    (101, "heavy"),
]

BAND_LABELS: dict[Band, str] = {
    "natural": "自然",
    "mild": "轻微",
    "obvious": "明显",
    "heavy": "强 AI 味",
}


def band_of(score: int) -> Band:
    for upper, band in BANDS:
        if score < upper:
            return band
    return "heavy"


class Finding(BaseModel):
    """一条高亮证据：原文区间 + 命中片段 + 原因 + 修改建议。

    不变量：text[start:end] == matched（由检测器直接从原文切片构造）。
    """

    dimension: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    matched: str
    reason: str
    suggestion: str
    severity: Severity = "mid"


class DimensionScore(BaseModel):
    """单维度得分（0-100）；inverted=True 表示分数高=信号缺失（如信息密度不足）。"""

    id: str
    name: str
    score: int = Field(ge=0, le=100)
    inverted: bool = False
    explanation: str


class TextStats(BaseModel):
    chars: int
    sentences: int
    words: int
    paragraphs: int
    sent_len_mean: float
    sent_len_std: float
    sent_len_cv: float
    confidence: Literal["low", "medium", "high"]
    lang: str


class AnalysisResult(BaseModel):
    score: int = Field(ge=0, le=100, description="AI 味浓度，越高越像 AI 写的")
    band: Band
    band_label: str
    dimensions: list[DimensionScore]
    findings: list[Finding]
    stats: TextStats
    lang: str
    engine_version: str
    text_register: str = Field(
        default="unknown",
        description="识别出的文体（academic/official/legal/technical/product/news/casual）",
    )
    text_register_label: str = Field(default="通用", description="文体中文名，供 UI 展示")
    text_register_confidence: float = Field(
        default=0.0, description="文体识别置信度 0-1（按文体调整权重，见 engine/weights_register）"
    )
