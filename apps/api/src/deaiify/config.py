"""运行配置：环境变量前缀 DEAIIFY_，可选 .env 文件（全量说明见 .env.example）。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DEAIIFY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # —— 运行 ——
    env: str = "dev"
    host: str = "127.0.0.1"
    port: int = 8000

    # —— 存储（标准栈=Docker PG/Redis；lite=SQLite+进程内队列，见 §3.3）——
    database_url: str = "postgresql+asyncpg://deaiify:deaiify@127.0.0.1:5433/deaiify"
    redis_url: str = "redis://127.0.0.1:6380/0"

    # —— 鉴权与限流（api_key 留空 = 不鉴权，适合本地/内网）——
    api_key: str | None = None
    rate_limit_per_min: int = 60

    # —— 隐私（never = 默认不保存原文，见 §8.2）——
    store: str = "never"
    history_ttl_days: int | None = None  # optin 模式下历史保留天数；空 = 永久

    # —— 模型（评分不需要模型；改写默认走维护者提供的 OpenAI 兼容端点）——
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"
    default_provider: str = "openai"
    default_model: str = ""

    # —— 引擎 ——
    max_text_chars: int = 20000
    batch_concurrency: int = 3
    rewrite_timeout_s: int = 120


@lru_cache
def get_settings() -> Settings:
    """进程内单例；测试可用 get_settings.cache_clear() 重置。"""
    return Settings()
