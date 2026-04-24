"""
Chunk model.

A Chunk is a processed, policy-filtered unit of knowledge derived from a Source.
It is what gets indexed and retrieved — NOT raw source content.

Key principle: raw source files are never stored in this table.
Only derived, safe knowledge representations are stored here.
"""

import enum
import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.source import Source

settings = get_settings()


class ChunkType(enum.StrEnum):
    """
    What kind of knowledge this chunk represents.

    Deterministic (produced by extractors.py from document sources):
      documentation, career_summary, experience_entry, project_description,
      skill_profile, manual_note

    LLM-generated (produced by domains/memory/extractor.py — post-ingestion):
      change_entry, risk_note, decision_record, hotspot, memory_brief,
      feature_summary, auth_flow, onboarding_map
      These chunks always have source_ref = "__memory__/{doctwin_id}" to
      distinguish them from file-derived chunks and allow targeted deletion.

    Retired (kept in enum so existing DB rows don't break; no longer produced):
      architecture_summary, module_description, feature_description,
      dependency_signal, code_snippet, implementation_fact
    """
    # ── Active deterministic chunk types ────────────────────────────────────
    documentation = "documentation"
    career_summary = "career_summary"
    experience_entry = "experience_entry"
    project_description = "project_description"
    skill_profile = "skill_profile"
    manual_note = "manual_note"

    # ── Retired code-intelligence types (no longer produced) ─────────────────
    architecture_summary = "architecture_summary"
    module_description = "module_description"
    feature_description = "feature_description"
    dependency_signal = "dependency_signal"
    code_snippet = "code_snippet"
    implementation_fact = "implementation_fact"

    # ── LLM-generated memory chunk types ────────────────────────────────────
    change_entry = "change_entry"       # Answers "what changed recently?"
    risk_note = "risk_note"             # Answers "what's risky or fragile?"
    decision_record = "decision_record" # Answers "why was X built this way?"
    hotspot = "hotspot"                 # Flags a specific complex/risky file or module
    memory_brief = "memory_brief"       # Full twin-level summary for RAG retrieval
    feature_summary = "feature_summary" # Evidence-backed feature or capability summary
    auth_flow = "auth_flow"             # Evidence-backed authentication/authorization summary
    onboarding_map = "onboarding_map"   # Evidence-backed newcomer reading map


class ChunkLineage(enum.StrEnum):
    """
    Evidence lineage for a chunk.

    This lets the platform apply different invariants to different evidence
    classes instead of assuming every chunk is a repo-file slice.
    """

    file_backed = "file_backed"
    connector_segment = "connector_segment"
    synthetic_profile = "synthetic_profile"
    memory_derived = "memory_derived"


class Chunk(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint(
            """
            lineage != 'file_backed'
            OR (
                source_ref IS NOT NULL
                AND snapshot_id IS NOT NULL
                AND segment_id IS NOT NULL
                AND content_hash IS NOT NULL
                AND start_line IS NOT NULL
                AND end_line IS NOT NULL
                AND start_line <= end_line
            )
            """,
            name="ck_chunks_file_backed_contract",
        ),
        CheckConstraint(
            """
            lineage != 'connector_segment'
            OR (
                source_ref IS NOT NULL
                AND snapshot_id IS NOT NULL
                AND segment_id IS NOT NULL
                AND content_hash IS NOT NULL
                AND start_line IS NOT NULL
                AND end_line IS NOT NULL
                AND start_line <= end_line
            )
            """,
            name="ck_chunks_connector_segment_contract",
        ),
        Index("ix_chunks_source_snapshot_segment", "source_id", "snapshot_id", "segment_id"),
        Index("ix_chunks_lineage_snapshot", "lineage", "snapshot_id"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )

    chunk_type: Mapped[ChunkType] = mapped_column(
        Enum(ChunkType, name="chunk_type_enum"), nullable=False
    )

    lineage: Mapped[ChunkLineage] = mapped_column(
        Enum(ChunkLineage, name="chunk_lineage_enum"),
        nullable=False,
        default=ChunkLineage.file_backed,
    )

    # The safe, derived text content of this chunk
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Vector embedding for semantic search
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=True
    )

    # Human-readable reference (e.g., "src/auth/service.py", "README.md")
    source_ref: Mapped[str | None] = mapped_column(String(500))

    # Snapshot identity this chunk belongs to (commit SHA, revision id, or
    # deterministic content-addressed snapshot fallback).
    snapshot_id: Mapped[str | None] = mapped_column(String(200))

    # Stable segment identity within the source snapshot.
    # For file-backed chunks this is typically path + line range.
    segment_id: Mapped[str | None] = mapped_column(String(500))

    # Exact span for file-backed or line-addressable connector evidence.
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)

    # Hash of the stored chunk content, used for integrity checks and caching.
    content_hash: Mapped[str | None] = mapped_column(String(64))

    # Token count for context window management
    token_count: Mapped[int | None] = mapped_column(Integer)

    # Arbitrary metadata (e.g., module name, section heading, line range).
    # Python name must not be `metadata` — reserved on DeclarativeBase for Table.metadata.
    chunk_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )

    # Relationships
    source: Mapped["Source"] = relationship("Source", back_populates="chunks")
