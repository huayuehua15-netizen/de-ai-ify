"""供应商预设目录（UI「添加供应商」页的一键填充项）。

每个预设给出：默认 base_url、是否需要 key、文档链接、推荐模型。
用户添加后可在 UI 改 base_url/模型名——预设只是省去手填，不是白名单。
所有 OpenAI 兼容端点（智谱/Kimi/MiniMax/DeepSeek/百炼/Ollama/vLLM/网关）
都走同一 `openai` 适配器，差别只在 base_url。
"""

from typing import TypedDict


class Preset(TypedDict):
    id: str
    name: str
    kind: str  # openai | anthropic | ollama
    base_url: str
    needs_key: bool
    docs_url: str
    models: list[str]
    note: str


PRESETS: list[Preset] = [
    {
        "id": "openai",
        "name": "OpenAI 官方",
        "kind": "openai",
        "base_url": "https://api.openai.com/v1",
        "needs_key": True,
        "docs_url": "https://platform.openai.com/api-keys",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1"],
        "note": "官方端点；也可留空 base_url 使用 SDK 默认",
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "kind": "anthropic",
        "base_url": "",
        "needs_key": True,
        "docs_url": "https://console.anthropic.com/settings/keys",
        "models": ["claude-sonnet-4", "claude-opus-4"],
        "note": "使用 Anthropic 原生 Messages API",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "kind": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "needs_key": True,
        "docs_url": "https://platform.deepseek.com/api_keys",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "note": "OpenAI 兼容端点",
    },
    {
        "id": "zhipu",
        "name": "智谱 BigModel",
        "kind": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "needs_key": True,
        "docs_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "models": ["glm-4-plus", "glm-4-flash", "glm-4.5"],
        "note": "OpenAI 兼容端点",
    },
    {
        "id": "moonshot",
        "name": "Kimi (Moonshot)",
        "kind": "openai",
        "base_url": "https://api.moonshot.cn/v1",
        "needs_key": True,
        "docs_url": "https://platform.moonshot.cn/console/api-keys",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2"],
        "note": "OpenAI 兼容端点",
    },
    {
        "id": "minimax",
        "name": "MiniMax",
        "kind": "openai",
        "base_url": "https://api.minimax.chat/v1",
        "needs_key": True,
        "docs_url": "https://platform.minimaxi.com/user-center/basic-information/interface-key",
        "models": ["abab6.5s-chat", "MiniMax-M1"],
        "note": "OpenAI 兼容端点",
    },
    {
        "id": "dashscope",
        "name": "阿里云百炼",
        "kind": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "needs_key": True,
        "docs_url": "https://bailian.console.aliyun.com/",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
        "note": "OpenAI 兼容模式端点",
    },
    {
        "id": "ollama",
        "name": "Ollama 本地",
        "kind": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "needs_key": False,
        "docs_url": "https://ollama.com/download",
        "models": ["qwen2.5:7b", "llama3.2", "deepseek-r1:7b"],
        "note": "原生 /api/chat；全程不出机器",
    },
    {
        "id": "custom",
        "name": "自定义 OpenAI 兼容端点",
        "kind": "openai",
        "base_url": "",
        "needs_key": True,
        "docs_url": "",
        "models": [],
        "note": "填 vLLM / OneAPI / 自建网关等任意兼容地址",
    },
]

PRESETS_BY_ID: dict[str, Preset] = {p["id"]: p for p in PRESETS}
