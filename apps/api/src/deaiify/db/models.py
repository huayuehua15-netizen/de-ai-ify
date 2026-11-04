"""ORM 模型（表结构见 docs/DEVELOPMENT.md §8.1）。

仅含 M4 两组表：自定义词库（lexicons/lexicon_terms/disabled_terms）
与改写历史（rewrite_history，默认 stored_text 为 NULL —— 隐私承诺 §8.2）。
批量任务 jobs、presets、settings 属 M4 后续/CLI 场景，待需要时再加。
"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Lexicon(Base):
    """用户自定义词库（一个词库含多条词条）。"""

    __tablename__ = "lexicons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str] = mapped_column(String(8), default="zh", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    terms: Mapped[list["LexiconTerm"]] = relationship(
        back_populates="lexicon",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class LexiconTerm(Base):
    """词条：term + 归属检测层 + 匹配方式 + 权重 + 可选替换建议（docs §5.6）。

    layer 决定词条喂给引擎哪个检测器（cliches/vague/templates/…，见 engine.LAYERS）；
    docs §8.1 原表缺此列，v0.3 已同步补入。
    """

    __tablename__ = "lexicon_terms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    lexicon_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lexicons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    term: Mapped[str] = mapped_column(String(200), nullable=False)
    layer: Mapped[str] = mapped_column(String(24), default="cliches", nullable=False)
    match_mode: Mapped[str] = mapped_column(String(12), default="exact", nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    replacement: Mapped[str | None] = mapped_column(String(300), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lexicon: Mapped[Lexicon] = relationship(back_populates="terms")


class DisabledTerm(Base):
    """用户停用的内置词库条目（docs §5.6 disabled_terms）。"""

    __tablename__ = "disabled_terms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    term: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(12), default="builtin", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderConfig(Base):
    """用户配置的模型供应商（UI「模型设置」页管理，替代手改 .env）。

    安全约定：api_key 落库前经 services/secrets 加密（Fernet），
    对外响应永不返回明文（只返回 has_key 布尔 + 掩码）。
    """

    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)  # 展示名
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # openai/anthropic/ollama/兼容
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fernet 密文
    default_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RewriteHistory(Base):
    """改写历史：默认只存哈希/长度/分数，stored_text 恒 NULL（§8.2 隐私）。"""

    __tablename__ = "rewrite_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    text_len: Mapped[int] = mapped_column(Integer, nullable=False)
    lang: Mapped[str] = mapped_column(String(8), nullable=False)
    style: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    score_before: Mapped[int] = mapped_column(Integer, nullable=False)
    score_after: Mapped[int] = mapped_column(Integer, nullable=False)
    stored_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 仅 optin 且 store=true
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
