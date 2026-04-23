"""
Sharing schemas.

Public surface responses never include owner-only fields like custom_context.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.sharing import ShareSurfaceType


class CreateTwinSharePageRequest(BaseModel):
    """No additional fields needed — twin_id comes from the path."""
    pass


class CreateEmbedSurfaceRequest(BaseModel):
    allowed_origins: list[str] = Field(
        default_factory=list,
        description="List of allowed hostnames for the embed widget (empty = unrestricted)",
        max_length=20,
    )


class CreateWorkspaceSharePageRequest(BaseModel):
    """No additional fields needed — workspace_id comes from the path."""
    pass


class ShareSurfaceResponse(BaseModel):
    """Returned to authenticated owners."""
    id: uuid.UUID
    surface_type: ShareSurfaceType
    public_slug: str
    is_active: bool
    twin_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    embed_config: dict
    created_at: datetime
    # Convenience URL hint
    public_url: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_surface(cls, surface: object, base_url: str = "") -> "ShareSurfaceResponse":
        from app.models.sharing import ShareSurface
        s = surface  # type: ShareSurface
        if s.surface_type == ShareSurfaceType.twin_page:
            url = f"{base_url}/t/{s.public_slug}"
        elif s.surface_type == ShareSurfaceType.workspace_page:
            url = f"{base_url}/w/{s.public_slug}"
        else:
            url = f"{base_url}/embed/{s.public_slug}"
        return cls(
            id=s.id,
            surface_type=s.surface_type,
            public_slug=s.public_slug,
            is_active=s.is_active,
            twin_id=s.twin_id,
            workspace_id=s.workspace_id,
            embed_config=s.embed_config,
            created_at=s.created_at,
            public_url=url,
        )


class PublicSurfaceInfoResponse(BaseModel):
    """
    Returned to anonymous visitors of a share surface.

    Never includes custom_context or any owner-private config.
    """
    surface_type: ShareSurfaceType
    public_slug: str
    twin_name: str | None = None
    twin_description: str | None = None
    workspace_name: str | None = None
    display_name: str | None = None
    accent_color: str | None = None
    is_active: bool
