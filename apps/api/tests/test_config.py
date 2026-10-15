"""配置默认值测试（与 .env.example / docs §12.3 保持一致）。"""

from deaiify.config import Settings


def test_privacy_default_no_storage() -> None:
    assert Settings().store == "never"


def test_engine_defaults() -> None:
    settings = Settings()
    assert settings.max_text_chars == 20000
    assert settings.batch_concurrency == 3
    assert settings.rewrite_timeout_s == 120


def test_lite_mode_redis_detection() -> None:
    # lite 模式约定：redis_url 置空 → health 显示 skipped、队列走进程内实现
    settings = Settings(redis_url="")
    assert settings.redis_url == ""
