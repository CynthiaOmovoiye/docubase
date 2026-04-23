import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.chat import ChatSession
    from app.models.sharing import ShareSurface
    from app.models.source import Source
    from app.models.workspace import Workspace


class Twin(Base, UUIDMixin, TimestampMixin):
    """
    The core product entity.

    A Twin is a named, configurable AI agent grounded in one or more Sources.
    It is NOT a repo. It is NOT a document. It can be backed by any source type.
    """

    __tablename__ = "twins"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="twins")
    config: Mapped["TwinConfig"] = relationship(
        "TwinConfig", back_populates="twin", uselist=False, cascade="all, delete-orphan"
    )
    sources: Mapped[list["Source"]] = relationship(
        "Source", back_populates="twin", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession", back_populates="twin"
    )
    share_surfaces: Mapped[list["ShareSurface"]] = relationship(
        "ShareSurface", back_populates="twin"
    )

    def __repr__(self) -> str:
        return f"<Twin id={self.id} name={self.name}>"


class TwinConfig(Base, UUIDMixin, TimestampMixin):
    """
    Per-twin policy and display configuration.

    This is where the user controls:
    - Whether code snippets can be surfaced
    - Branding overrides
    - Custom system prompt additions
    - Visibility level
    """

    __tablename__ = "doctwin_configs"

    doctwin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("twins.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Policy
    allow_code_snippets: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # If True, relevant scoped code sections may appear in answers.
    # Full file dumps are never permitted regardless of this setting.
    # .env and secret files are always blocked regardless of this setting.

    # Visibility
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Branding (optional, used on public share pages)
    display_name: Mapped[str | None] = mapped_column(String(120))
    accent_color: Mapped[str | None] = mapped_column(String(7))  # hex color

    # Custom context appended to system prompt (owner-controlled)
    custom_context: Mapped[str | None] = mapped_column(Text)

    # Arbitrary extension point for future config keys
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # ── Engineering Memory Layer ─────────────────────────────────────────────
    # System-authored. NOT owner-editable. Set by the memory extraction job.
    # Do NOT conflate with custom_context — that field belongs to the owner.

    # The generated Memory Brief markdown document for this twin.
    # Populated by the generate_memory_brief ARQ job after ingestion.
    memory_brief: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamp of the last successful brief generation.
    memory_brief_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Lifecycle status: "pending" | "generating" | "ready" | "failed"
    memory_brief_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Relationships
    twin: Mapped["Twin"] = relationship("Twin", back_populates="config")
