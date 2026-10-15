"""模型适配层公共契约（规格见 docs/DEVELOPMENT.md §6.4）。

- `ProviderError`：把各家 SDK 异常归一为 {code, http_status}，由 API 层映射错误码；
- `BaseProvider.complete`：指数退避重试（仅超时/429/5xx，最多 2 次）；流式不重试。
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


@dataclass
class ModelRequest:
    messages: list[dict[str, str]]
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float | None = None


@dataclass
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def as_dict(self) -> dict[str, int]:
        out: dict[str, int] = {}
        if self.prompt_tokens is not None:
            out["prompt_tokens"] = self.prompt_tokens
        if self.completion_tokens is not None:
            out["completion_tokens"] = self.completion_tokens
        return out


@dataclass
class ModelInfo:
    id: str
    provider: str
    context_window: int | None = None
    owned_by: str | None = None


# 错误码 → 由 API 层映射为 HTTP 状态（docs §7.4）
PROVIDER_ERROR_STATUS = {
    "provider_timeout": 504,
    "rate_limited": 429,
    "provider_error": 502,
    "model_unavailable": 503,
}


class ProviderError(Exception):
    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status or PROVIDER_ERROR_STATUS.get(code, 502)


def _retryable(exc: BaseException) -> bool:
    """仅超时/上游限流/上游 5xx 可重试（docs §6.4）。"""
    if isinstance(exc, ProviderError):
        return exc.code in {"provider_timeout", "rate_limited"} or (
            exc.code == "provider_error" and exc.status == 502
        )
    return False


_RETRY_DECORATOR = retry(
    retry=retry_if_exception(_retryable),
    wait=wait_exponential(multiplier=0.3, max=2),
    stop=stop_after_attempt(3),  # 初始 1 次 + 最多重试 2 次
    reraise=True,
)


@runtime_checkable
class ModelProvider(Protocol):
    name: str

    def configured(self) -> bool: ...

    async def complete(self, req: ModelRequest) -> tuple[str, Usage]: ...

    def stream(self, req: ModelRequest) -> AsyncIterator[str]: ...

    async def list_models(self) -> list[ModelInfo]: ...


class BaseProvider:
    """子类实现 `_complete` / `stream` / `list_models`，错误统一转 ProviderError。"""

    name: str = "base"

    def configured(self) -> bool:  # pragma: no cover - 协议默认
        return True

    @_RETRY_DECORATOR
    async def complete(self, req: ModelRequest) -> tuple[str, Usage]:
        return await self._complete(req)

    async def _complete(self, req: ModelRequest) -> tuple[str, Usage]:
        raise NotImplementedError

    async def _iter_to_text(self, chunks: AsyncIterator[str]) -> tuple[str, Usage]:
        parts: list[str] = []
        async for chunk in chunks:
            parts.append(chunk)
        return "".join(parts), Usage()

    def _usage_from(self, usage: Any) -> Usage:
        if usage is None:
            return Usage()
        return Usage(
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
        )


@dataclass
class ProviderCapabilities:
    streaming: bool = True
    json_mode: bool = False
    native_json: bool = field(default=False)
