"""Provider 注册表：按配置解析实例（openai 同时覆盖所有兼容端点）。

SDK（openai/anthropic）在首次解析时才导入——它们的 import 各需约 1 秒，
延迟加载让 CLI/测试的冷启动不吃这笔开销。
"""

from deaiify.config import get_settings
from deaiify.providers.base import BaseProvider, ModelProvider, ProviderError

# (provider 名, 配置签名) → 实例缓存，避免每次请求重建 HTTP 客户端
_INSTANCES: dict[tuple[str, str, str], BaseProvider] = {}


def _signature(provider: str, settings) -> tuple[str, str, str]:
    if provider == "openai":
        return ("openai", settings.openai_api_key or "", settings.openai_base_url or "")
    if provider == "anthropic":
        return ("anthropic", settings.anthropic_api_key or "", "")
    return ("ollama", "", settings.ollama_base_url)


def get_provider(name: str | None = None) -> ModelProvider:
    """解析 provider；未配置凭据 → 503 model_unavailable（docs §7.4）。"""
    settings = get_settings()
    provider = (name or settings.default_provider).lower()
    if provider not in {"openai", "anthropic", "ollama"}:
        raise ProviderError(
            "model_unavailable", f"未知 provider：{name}（可选 openai/anthropic/ollama）"
        )

    sig = _signature(provider, settings)
    instance = _INSTANCES.get(sig)
    if instance is None:
        if provider == "openai":
            from deaiify.providers.openai_provider import OpenAIProvider

            instance = OpenAIProvider(settings)
        elif provider == "anthropic":
            from deaiify.providers.anthropic_provider import AnthropicProvider

            instance = AnthropicProvider(settings)
        else:
            from deaiify.providers.ollama_provider import OllamaProvider

            instance = OllamaProvider(settings)
        _INSTANCES.clear()  # 配置变化时（如测试换 key）不残留旧实例
        _INSTANCES[sig] = instance

    if not instance.configured():
        raise ProviderError(
            "model_unavailable",
            f"provider {provider} 未配置凭据（见 .env.example 对应变量）",
        )
    return instance


def known_providers() -> list[str]:
    return ["openai", "anthropic", "ollama"]


def install_instance(provider: ModelProvider) -> None:
    """测试注入口：把预构造的 provider 实例挂进注册表（含 MockTransport 客户端）。"""
    settings = get_settings()
    name = getattr(provider, "name", "")
    _INSTANCES[_signature(name, settings)] = provider  # type: ignore[arg-type]
