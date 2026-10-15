"""Ollama 原生 /api/chat 适配（可选 provider，非开发必需）。"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from deaiify.config import Settings
from deaiify.providers.base import (
    BaseProvider,
    ModelInfo,
    ModelRequest,
    ProviderError,
    Usage,
)


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.ollama_base_url.rstrip("/")

    def configured(self) -> bool:
        # 本地服务默认地址即视为"已配置"，可达性由调用时探测
        return bool(self._settings.ollama_base_url)

    def _wrap(self, exc: Exception) -> ProviderError:
        if isinstance(exc, httpx.TimeoutException):
            return ProviderError("provider_timeout", "本地 Ollama 超时（CPU 推理较慢属正常）")
        if isinstance(exc, httpx.ConnectError):
            return ProviderError("model_unavailable", "Ollama 服务未启动（ollama serve）")
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code == 429:
                return ProviderError("rate_limited", "上游模型限流，请稍后重试")
            return ProviderError("provider_error", f"Ollama 返回 {exc.response.status_code}")
        return ProviderError("provider_error", f"Ollama 调用失败：{type(exc).__name__}")

    def _payload(self, req: ModelRequest, *, stream: bool) -> dict[str, Any]:
        return {
            "model": req.model,
            "messages": req.messages,
            "stream": stream,
            "options": {"temperature": req.temperature},
        }

    async def _complete(self, req: ModelRequest) -> tuple[str, Usage]:
        timeout = req.timeout or self._settings.rewrite_timeout_s
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self._base}/api/chat", json=self._payload(req, stream=False)
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc
        text = data.get("message", {}).get("content", "")
        usage = Usage(
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
        )
        return text, usage

    async def stream(self, req: ModelRequest) -> AsyncIterator[str]:
        timeout = req.timeout or self._settings.rewrite_timeout_s
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", f"{self._base}/api/chat", json=self._payload(req, stream=True)
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except ValueError:
                            continue
                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            yield chunk
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base}/api/tags")
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc) from exc
        return [ModelInfo(id=m.get("name", ""), provider=self.name) for m in data.get("models", [])]
