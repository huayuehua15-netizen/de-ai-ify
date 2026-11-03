"""API 请求/响应契约（OpenAPI 自动生成，见 docs/DEVELOPMENT.md §7）。"""

from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, description="待评分文本")
    lang: Literal["auto", "zh", "en"] = "auto"
    lexicon_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="启用的自定义词库 id（M4；DB 不可达时自动忽略并用内置词库）",
    )
    store: bool = Field(
        default=False,
        description="是否保存原文（隐私默认 never；仅影响历史，见 docs §8.2）",
    )


class ModelChoice(BaseModel):
    provider: Literal["openai", "anthropic", "ollama"] | None = None
    name: str | None = Field(default=None, description="模型名；留空用 DEAIIFY_DEFAULT_MODEL")


class RewriteRequest(BaseModel):
    text: str = Field(min_length=1)
    styles: list[str] = Field(default_factory=lambda: ["natural"], min_length=1, max_length=6)
    model: ModelChoice = Field(default_factory=ModelChoice)
    gate: bool = Field(default=True, description="质量闸门（docs §6.3）")
    store: bool = Field(
        default=False,
        description="本次是否保存原文到历史（仅 DEAIIFY_STORE=optin 时生效，docs §8.2）",
    )


class RewriteVersionOut(BaseModel):
    style: str
    text: str
    score_before: int
    score_after: int
    delta: int
    gate: Literal["pass", "weak", "fail", "off"]
    model: str
    usage: dict[str, int] | None = None
    attempts: int = 1
    gate_reason: str | None = None


class RewriteResponse(BaseModel):
    versions: list[RewriteVersionOut]
    engine_version: str


class ModelOut(BaseModel):
    id: str
    provider: str
    owned_by: str | None = None


class ProviderOut(BaseModel):
    provider: str
    available: bool
    reason: str | None = None
    models: list[ModelOut] = []


class StyleOut(BaseModel):
    id: str
    name: str
    description: str
