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
        # 配置变化（如测试换 key）只淘汰同 provider 的旧签名实例——
        # 全表 clear 会抹掉其他 provider 已注入/已缓存的实例（启动预热线程
        # 与请求并发时造成过 mock 被清、请求打到真实上游的竞态）
        for key in [k for k in _INSTANCES if k[0] == provider and k != sig]:
            _INSTANCES.pop(key, None)
        _INSTANCES[sig] = instance

    if not instance.configured():
        raise ProviderError(
            "model_unavailable",
            f"provider {provider} 未配置凭据（见 .env.example 对应变量）",
        )
    return instance


def known_providers() -> list[str]:
    return ["openai", "anthropic", "ollama"]


def build_from_config(kind: str, api_key: str | None, base_url: str | None, settings=None):
    """按 DB 供应商配置构造实例（UI 添加的供应商走这条路径）。

    与 get_provider 的区别：不读 .env 签名、不进全局缓存——每次调用新建，
    因为 UI 配置可能随时改；HTTP 客户端开销可忽略（每请求一个）。
    """
    settings = settings or get_settings()
    # 用 Settings 的副本承载 DB 值：适配器签名统一，内部逻辑无需改动
    overridden = settings.model_copy(
        update={
            "openai_api_key": api_key if kind == "openai" else settings.openai_api_key,
            "openai_base_url": base_url if kind == "openai" else settings.openai_base_url,
            "anthropic_api_key": api_key if kind == "anthropic" else settings.anthropic_api_key,
            "ollama_base_url": (base_url or settings.ollama_base_url)
            if kind == "ollama"
            else settings.ollama_base_url,
        }
    )
    if kind == "openai":
        from deaiify.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(overridden)
    if kind == "anthropic":
        from deaiify.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(overridden)
    from deaiify.providers.ollama_provider import OllamaProvider

    return OllamaProvider(overridden)


def install_instance(provider: ModelProvider) -> None:
    """测试注入口：把预构造的 provider 实例挂进注册表（含 MockTransport 客户端）。"""
    settings = get_settings()
    name = getattr(provider, "name", "")
    _INSTANCES[_signature(name, settings)] = provider  # type: ignore[arg-type]
