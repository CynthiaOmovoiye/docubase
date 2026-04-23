import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.twin import Twin
    from app.models.user import User
    from app.models.sharing import ShareSurface
    from app.models.workspace_memory import WorkspaceMemoryArtifact


class Workspace(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500))

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="workspaces")
    twins: Mapped[list["Twin"]] = relationship(
        "Twin", back_populates="workspace", cascade="all, delete-orphan"
    )
    share_surfaces: Mapped[list["ShareSurface"]] = relationship(
        "ShareSurface", back_populates="workspace"
    )
    memory_artifacts: Mapped[list["WorkspaceMemoryArtifact"]] = relationship(
        "WorkspaceMemoryArtifact",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Workspace id={self.id} slug={self.slug}>"
