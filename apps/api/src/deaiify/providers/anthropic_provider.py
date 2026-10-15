"""Anthropic Messages API 适配。"""

from collections.abc import AsyncIterator

import anthropic
import httpx

from deaiify.config import Settings
from deaiify.providers.base import (
    BaseProvider,
    ModelInfo,
    ModelRequest,
    ProviderError,
    Usage,
)


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key or "missing-key",
            max_retries=0,
        )

    def configured(self) -> bool:
        return bool(self._settings.anthropic_api_key)

    def _wrap(self, exc: Exception) -> ProviderError:
        if isinstance(exc, anthropic.APITimeoutError | httpx.TimeoutException):
            return ProviderError("provider_timeout", "上游模型超时，请稍后重试")
        if isinstance(exc, anthropic.APIStatusError):
            if exc.status_code == 429:
                return ProviderError("rate_limited", "上游模型限流，请稍后重试")
            return ProviderError("provider_error", f"上游模型返回 {exc.status_code}")
        if isinstance(exc, anthropic.APIConnectionError | httpx.HTTPError):
            return ProviderError("provider_error", "无法连接上游模型端点")
        return ProviderError("provider_error", f"模型调用失败：{type(exc).__name__}")

    @staticmethod
    def _split(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        """Anthropic 要求 system 独立传参，且首条非 system。"""
        system_parts: list[str] = []
        rest: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                rest.append({"role": msg["role"], "content": msg["content"]})
        return "\n\n".join(system_parts), rest

    async def _complete(self, req: ModelRequest) -> tuple[str, Usage]:
        system, rest = self._split(req.messages)
        try:
            resp = await self._client.messages.create(
                model=req.model,
                system=system or anthropic.NOT_GIVEN,
                messages=rest,  # type: ignore[arg-type]
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                timeout=req.timeout,
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc
        text = "".join(block.text for block in resp.content if block.type == "text")
        return text, Usage(
            prompt_tokens=getattr(resp.usage, "input_tokens", None),
            completion_tokens=getattr(resp.usage, "output_tokens", None),
        )

    async def stream(self, req: ModelRequest) -> AsyncIterator[str]:
        system, rest = self._split(req.messages)
        try:
            async with self._client.messages.stream(
                model=req.model,
                system=system or anthropic.NOT_GIVEN,
                messages=rest,  # type: ignore[arg-type]
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                timeout=req.timeout,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield event.delta.text
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc

    async def list_models(self) -> list[ModelInfo]:
        try:
            page = await self._client.models.list(timeout=5)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc
        return [ModelInfo(id=m.id, provider=self.name) for m in page.data]
