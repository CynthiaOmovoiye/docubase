import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.twin import Twin
    from app.models.workspace import Workspace


class ShareSurfaceType(enum.StrEnum):
    doctwin_page = "doctwin_page"           # /t/{slug} — single twin public page
    workspace_page = "workspace_page" # /w/{slug} — workspace general public page
    embed = "embed"                   # embeddable widget


class ShareSurface(Base, UUIDMixin, TimestampMixin):
    """
    A public-facing surface for a Twin or Workspace.

    One twin can have multiple share surfaces (e.g., a public page AND an embed).
    A workspace can have a workspace-level share surface.
    """

    __tablename__ = "share_surfaces"

    surface_type: Mapped[ShareSurfaceType] = mapped_column(
        Enum(ShareSurfaceType, name="share_surface_type_enum"), nullable=False
    )

    # Unique public slug/token for this surface
    public_slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # One of these will be set depending on surface type
    doctwin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("twins.id", ondelete="CASCADE"), nullable=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )

    # Embed-specific config (allowed origins, widget theme, etc.)
    embed_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    twin: Mapped["Twin | None"] = relationship("Twin", back_populates="share_surfaces")
    workspace: Mapped["Workspace | None"] = relationship("Workspace", back_populates="share_surfaces")
