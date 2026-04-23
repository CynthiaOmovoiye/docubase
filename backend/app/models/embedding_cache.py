from __future__ import annotations

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class EmbeddingCacheEntry(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "embedding_cache_entries"
    __table_args__ = (
        UniqueConstraint(
            "text_hash",
            "provider",
            "model",
            "dimensions",
            "task",
            name="uq_embedding_cache_profile_text",
        ),
        Index("ix_embedding_cache_profile", "provider", "model", "dimensions", "task"),
    )

    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
