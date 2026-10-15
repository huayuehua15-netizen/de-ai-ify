"""OpenAI 官方 + 一切 OpenAI 兼容端点（vLLM / DeepSeek / 网关等，改 base_url 即可）。"""

from collections.abc import AsyncIterator

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from deaiify.config import Settings
from deaiify.providers.base import (
    BaseProvider,
    ModelInfo,
    ModelRequest,
    ProviderError,
    Usage,
)


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self, settings: Settings, http_client: object | None = None) -> None:
        """`http_client` 为测试注入口：openai 3.x 基于 httpx2，respx 无法拦截；
        测试用 httpx2.MockTransport 构造客户端注入（docs §16 R11）。"""
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key or "missing-key",
            base_url=settings.openai_base_url or None,
            max_retries=0,  # 重试由 BaseProvider 统一处理
            http_client=http_client,
        )

    def configured(self) -> bool:
        return bool(self._settings.openai_api_key)

    def _wrap(self, exc: Exception) -> ProviderError:
        if isinstance(exc, APITimeoutError | httpx.TimeoutException):
            return ProviderError("provider_timeout", "上游模型超时，请稍后重试")
        if isinstance(exc, APIStatusError):
            if exc.status_code == 429:
                return ProviderError("rate_limited", "上游模型限流，请稍后重试")
            return ProviderError("provider_error", f"上游模型返回 {exc.status_code}")
        if isinstance(exc, APIConnectionError | httpx.HTTPError):
            return ProviderError("provider_error", "无法连接上游模型端点")
        return ProviderError("provider_error", f"模型调用失败：{type(exc).__name__}")

    async def _complete(self, req: ModelRequest) -> tuple[str, Usage]:
        try:
            resp = await self._client.chat.completions.create(
                model=req.model,
                messages=req.messages,  # type: ignore[arg-type]
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                timeout=req.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - 归一化为 ProviderError
            raise self._wrap(exc) from exc
        content = resp.choices[0].message.content or ""
        return content, self._usage_from(resp.usage)

    async def stream(self, req: ModelRequest) -> AsyncIterator[str]:
        """流式增量；不自动重试（中途重放会产生重复文本）。"""
        try:
            stream = await self._client.chat.completions.create(
                model=req.model,
                messages=req.messages,  # type: ignore[arg-type]
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                timeout=req.timeout,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc

    async def list_models(self) -> list[ModelInfo]:
        try:
            page = await self._client.models.list(timeout=5)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc
        return [
            ModelInfo(id=m.id, provider=self.name, owned_by=getattr(m, "owned_by", None))
            for m in page.data
        ]
