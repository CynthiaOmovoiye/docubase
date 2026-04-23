from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.workspace import Workspace


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class WorkspaceMemoryArtifactType(enum.StrEnum):
    workspace_synthesis = "workspace_synthesis"


class WorkspaceMemoryArtifact(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspace_memory_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "artifact_type",
            name="uq_workspace_memory_artifacts_workspace_type",
        ),
        Index("ix_workspace_memory_artifacts_workspace_status", "workspace_id", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_type: Mapped[WorkspaceMemoryArtifactType] = mapped_column(
        Enum(
            WorkspaceMemoryArtifactType,
            name="workspace_memory_artifact_type_enum",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="memory_artifacts")
