"""
Sharing API routes.

Create and manage public share surfaces for twins and workspaces.
Generate embed codes.

Auth rules:
  - Create/revoke/list routes — authenticated owner only.
    The service layer verifies twin/workspace ownership before creating or
    revoking a surface (surface.twin.workspace.owner_id == current_user.id).
  - GET /public/{slug} — intentionally unauthenticated (public page renderer).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.domains.sharing import service as sharing_svc
from app.models.user import User
from app.schemas.sharing import (
    CreateEmbedSurfaceRequest,
    PublicSurfaceInfoResponse,
    ShareSurfaceResponse,
)

router = APIRouter()


@router.post(
    "/twin/{doctwin_id}/page",
    status_code=status.HTTP_201_CREATED,
    response_model=ShareSurfaceResponse,
)
async def create_doctwin_share_page(
    doctwin_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a public share page for a twin. Returns the public slug and URL.
    Caller must own the twin's workspace.
    """
    try:
        surface = await sharing_svc.create_doctwin_share_page(doctwin_id, current_user.id, db)
    except sharing_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sharing_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except sharing_svc.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    await db.commit()
    await db.refresh(surface)
    return ShareSurfaceResponse.from_surface(surface, _base_url(request))


@router.post(
    "/twin/{doctwin_id}/embed",
    status_code=status.HTTP_201_CREATED,
    response_model=ShareSurfaceResponse,
)
async def create_embed_surface(
    doctwin_id: uuid.UUID,
    body: CreateEmbedSurfaceRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create an embeddable widget config for a twin.
    Returns embed token and snippet.
    Caller must own the twin's workspace.
    """
    try:
        surface = await sharing_svc.create_embed_surface(
            doctwin_id, current_user.id, body.allowed_origins, db
        )
    except sharing_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sharing_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except sharing_svc.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    await db.commit()
    await db.refresh(surface)
    return ShareSurfaceResponse.from_surface(surface, _base_url(request))


@router.post(
    "/workspace/{workspace_id}/page",
    status_code=status.HTTP_201_CREATED,
    response_model=ShareSurfaceResponse,
)
async def create_workspace_share_page(
    workspace_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a workspace-level public share page.
    Caller must own the workspace.
    """
    try:
        surface = await sharing_svc.create_workspace_share_page(workspace_id, current_user.id, db)
    except sharing_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sharing_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except sharing_svc.ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    await db.commit()
    await db.refresh(surface)
    return ShareSurfaceResponse.from_surface(surface, _base_url(request))


@router.get(
    "/twin/{doctwin_id}",
    response_model=list[ShareSurfaceResponse],
)
async def list_doctwin_surfaces(
    doctwin_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all share surfaces for a twin."""
    try:
        surfaces = await sharing_svc.list_surfaces_for_twin(doctwin_id, current_user.id, db)
    except sharing_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sharing_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    base = _base_url(request)
    return [ShareSurfaceResponse.from_surface(s, base) for s in surfaces]


@router.get(
    "/workspace/{workspace_id}",
    response_model=list[ShareSurfaceResponse],
)
async def list_workspace_surfaces(
    workspace_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all share surfaces for a workspace."""
    try:
        surfaces = await sharing_svc.list_surfaces_for_workspace(
            workspace_id,
            current_user.id,
            db,
        )
    except sharing_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sharing_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    base = _base_url(request)
    return [ShareSurfaceResponse.from_surface(s, base) for s in surfaces]


@router.delete("/{surface_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_surface(
    surface_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke/deactivate a public share surface.
    Caller must own the workspace that the surface belongs to.
    """
    try:
        await sharing_svc.revoke_share_surface(surface_id, current_user.id, db)
    except sharing_svc.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except sharing_svc.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    await db.commit()


# ─── Public (no auth) ─────────────────────────────────────────────────────────
# No auth required. Rate limiting MUST be applied here when this endpoint
# is placed behind a public gateway.

@router.get("/public/{public_slug}", response_model=PublicSurfaceInfoResponse)
async def get_public_surface_info(
    public_slug: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint — no auth required.
    Returns the twin/workspace display info for rendering a share page.
    Must NOT return owner-only fields (custom_context, etc.).
    """
    try:
        surface = await sharing_svc.get_active_surface_by_slug(public_slug, db)
    except sharing_svc.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share surface not found or inactive",
        )

    # Build a safe public response — no owner fields
    doctwin_name = None
    doctwin_description = None
    workspace_name = None
    display_name = None
    accent_color = None

    if surface.twin is not None:
        doctwin_name = surface.twin.name
        doctwin_description = surface.twin.description
        # Load twin config for display fields
        from sqlalchemy import select

        from app.models.twin import TwinConfig
        config_result = await db.execute(
            select(TwinConfig).where(TwinConfig.doctwin_id == surface.twin.id)
        )
        config = config_result.scalar_one_or_none()
        if config:
            display_name = config.display_name
            accent_color = config.accent_color

    if surface.workspace is not None:
        workspace_name = surface.workspace.name

    return PublicSurfaceInfoResponse(
        surface_type=surface.surface_type,
        public_slug=surface.public_slug,
        doctwin_name=doctwin_name,
        doctwin_description=doctwin_description,
        workspace_name=workspace_name,
        display_name=display_name,
        accent_color=accent_color,
        is_active=surface.is_active,
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _base_url(request: Request) -> str:
    """
    Extract the application base URL from the request for building public URLs.

    In production this should come from a configured FRONTEND_URL env var.
    Falling back to the request origin keeps development convenient.
    """
    from app.core.config import get_settings
    settings = get_settings()
    frontend_url = getattr(settings, "frontend_url", None)
    if frontend_url:
        return frontend_url.rstrip("/")
    # Dev fallback
    return str(request.base_url).rstrip("/")
