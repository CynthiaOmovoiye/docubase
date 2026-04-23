import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.chunk import Chunk
    from app.models.integration import ConnectedAccount
    from app.models.twin import Twin


class SourceType(enum.StrEnum):
    """
    All supported source types.

    google_drive is a dedicated type; 'url' remains for raw webpage ingestion.
    """
    google_drive = "google_drive"
    pdf = "pdf"
    markdown = "markdown"
    url = "url"
    manual = "manual"


class SourceStatus(enum.StrEnum):
    pending = "pending"
    ingesting = "ingesting"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    needs_resync = "needs_resync"


class SourceIndexMode(enum.StrEnum):
    """
    Index trust mode for this source.

    legacy — older or partial index contract; canonical hydration may fall back
             to stored chunk content.
    strict — chunk lineage, snapshot identity, and evidence invariants are
             present for the source's supported evidence types.
    """

    legacy = "legacy"
    strict = "strict"


class Source(Base, UUIDMixin, TimestampMixin):
    """
    A data origin attached to a Twin.

    Each Source is typed. The connection_config stores type-specific
    connection details (e.g., repo URL, file path, API token reference).
    Actual secrets are NEVER stored here — only references to them.
    """

    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum"), nullable=False
    )
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, name="source_status_enum"),
        default=SourceStatus.pending,
        nullable=False,
    )

    doctwin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("twins.id", ondelete="CASCADE"), nullable=False
    )

    # Type-specific config. No secrets stored here — only references.
    # Example for google_drive: {"folder_id": "..."} or {"file_id": "..."}
    connection_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Last ingestion error message if status == failed
    last_error: Mapped[str | None] = mapped_column(Text)

    # OAuth integration link — nullable so sources added without OAuth still work.
    # SET NULL on delete so removing a connected account doesn't destroy sources.
    connected_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("connected_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Sync state for incremental ingestion
    # For git sources: last synced commit SHA (40 hex chars)
    last_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # For Google Drive: last changes pageToken for delta sync
    last_page_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Canonical snapshot identity for the latest successful sync.
    # For git sources this is usually the commit SHA; for other connectors it
    # falls back to a deterministic content-addressed snapshot id.
    snapshot_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    snapshot_root_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Trust level of the current source index contract.
    index_mode: Mapped[SourceIndexMode] = mapped_column(
        Enum(SourceIndexMode, name="source_index_mode_enum"),
        default=SourceIndexMode.legacy,
        nullable=False,
    )

    # Owner-visible index health and coverage telemetry.
    index_health: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Webhook registration state — stored so we can revoke the hook on source delete
    webhook_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Per-source HMAC secret for provider webhook signature verification
    webhook_secret: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Deterministic file-tree inventory built at sync time.
    # Populated on every full sync; delta-patched on incremental syncs.
    # Schema:
    #   {
    #     "schema_version": 1,
    #     "meaningful_dirs": {
    #       "week3": ["week3/README.md", ...],
    #       "app/api": ["app/api/routes.py", ...],
    #       "_root": ["README.md", ...]
    #     },
    #     "total_files": N,
    #     "generated_at": "ISO timestamp",
    #     "is_partial": false,  # true = derived from chunks, not a real sync
    #     "snapshot_id": "abc123...",
    #     "snapshot_root_hash": "sha256..."
    #   }
    # Only stores policy-cleared file paths — never raw content, never secrets.
    # Null until the first sync completes.
    structure_index: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Embedding profile used for the currently stored chunk vectors on this source.
    # Query-time retrieval must use the same provider/model pair; vector spaces are
    # not interchangeable across embedding vendors or models.
    embedding_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    twin: Mapped["Twin"] = relationship("Twin", back_populates="sources")
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="source", cascade="all, delete-orphan"
    )
    connected_account: Mapped["ConnectedAccount | None"] = relationship(
        "ConnectedAccount", back_populates="sources"
    )

    def __repr__(self) -> str:
        return f"<Source id={self.id} type={self.source_type} status={self.status}>"
