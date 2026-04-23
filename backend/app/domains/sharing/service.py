"""
Sharing domain service.

Handles creation, lookup, and revocation of ShareSurfaces.

Ownership chain:
  doctwin_page / embed → twin → workspace → workspace.owner_id == user.id
  workspace_page    → workspace → workspace.owner_id == user.id

Public slug uniqueness is enforced at the DB level (unique index).
We generate a URL-safe random slug and retry once on collision (extremely rare).
"""

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.sharing import ShareSurface, ShareSurfaceType
from app.models.twin import Twin
from app.models.workspace import Workspace

logger = get_logger(__name__)

# Slug length — 12 URL-safe bytes → 16-char base64url string
_SLUG_BYTES = 12
# Max retries for slug collision (astronomically unlikely but handled correctly)
_MAX_SLUG_RETRIES = 3


class NotFoundError(Exception):
    pass


class ForbiddenError(Exception):
    pass


class ConflictError(Exception):
    pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _generate_slug() -> str:
    return secrets.token_urlsafe(_SLUG_BYTES)


async def _assert_doctwin_owned_by(
    doctwin_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Twin:
    result = await db.execute(
        select(Twin)
        .options(selectinload(Twin.workspace))
        .where(Twin.id == doctwin_id)
    )
    twin = result.scalar_one_or_none()
    if twin is None:
        raise NotFoundError(f"Twin {doctwin_id} not found")
    if twin.workspace.owner_id != user_id:
        raise ForbiddenError("You do not own this twin's workspace")
    return twin


async def _assert_workspace_owned_by(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Workspace:
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        raise NotFoundError(f"Workspace {workspace_id} not found")
    if ws.owner_id != user_id:
        raise ForbiddenError("You do not own this workspace")
    return ws


async def _create_surface_with_retry(
    surface: ShareSurface,
    db: AsyncSession,
) -> ShareSurface:
    """
    Insert a ShareSurface with slug-collision retry.

    The unique constraint on public_slug is enforced by the DB.
    We retry up to _MAX_SLUG_RETRIES times on IntegrityError.
    """
    for attempt in range(_MAX_SLUG_RETRIES):
        try:
            db.add(surface)
            await db.flush()
            await db.refresh(surface)
            return surface
        except IntegrityError as exc:
            await db.rollback()
            if attempt + 1 == _MAX_SLUG_RETRIES:
                raise ConflictError("Could not generate a unique slug after retries") from exc
            surface.public_slug = _generate_slug()
    # Should not reach here
    raise ConflictError("Slug generation failed")


# ─── Public API ───────────────────────────────────────────────────────────────

async def create_doctwin_share_page(
    doctwin_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ShareSurface:
    """
    Create a public twin page share surface.

    Returns the ShareSurface with public_slug populated.
    """
    await _assert_doctwin_owned_by(doctwin_id, user_id, db)

    surface = ShareSurface(
        id=uuid.uuid4(),
        surface_type=ShareSurfaceType.doctwin_page,
        public_slug=_generate_slug(),
        is_active=True,
        doctwin_id=doctwin_id,
        workspace_id=None,
        embed_config={},
    )
    result = await _create_surface_with_retry(surface, db)

    logger.info(
        "share_surface_created",
        surface_id=str(result.id),
        surface_type="doctwin_page",
        doctwin_id=str(doctwin_id),
        slug=result.public_slug,
    )
    return result


async def create_embed_surface(
    doctwin_id: uuid.UUID,
    user_id: uuid.UUID,
    allowed_origins: list[str],
    db: AsyncSession,
) -> ShareSurface:
    """
    Create an embeddable widget surface for a twin.

    allowed_origins restricts which domains can host the embed.
    Empty list = no origin restriction (open embed — owner's choice).
    """
    await _assert_doctwin_owned_by(doctwin_id, user_id, db)

    embed_config = {
        "allowed_origins": allowed_origins,
        "widget_version": "1",
    }

    surface = ShareSurface(
        id=uuid.uuid4(),
        surface_type=ShareSurfaceType.embed,
        public_slug=_generate_slug(),
        is_active=True,
        doctwin_id=doctwin_id,
        workspace_id=None,
        embed_config=embed_config,
    )
    result = await _create_surface_with_retry(surface, db)

    logger.info(
        "share_surface_created",
        surface_id=str(result.id),
        surface_type="embed",
        doctwin_id=str(doctwin_id),
        slug=result.public_slug,
    )
    return result


async def create_workspace_share_page(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ShareSurface:
    """Create a workspace-level public share page."""
    await _assert_workspace_owned_by(workspace_id, user_id, db)

    surface = ShareSurface(
        id=uuid.uuid4(),
        surface_type=ShareSurfaceType.workspace_page,
        public_slug=_generate_slug(),
        is_active=True,
        doctwin_id=None,
        workspace_id=workspace_id,
        embed_config={},
    )
    result = await _create_surface_with_retry(surface, db)

    logger.info(
        "share_surface_created",
        surface_id=str(result.id),
        surface_type="workspace_page",
        workspace_id=str(workspace_id),
        slug=result.public_slug,
    )
    return result


async def revoke_share_surface(
    surface_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """
    Revoke (deactivate) a share surface.

    The surface is NOT deleted — it's marked inactive so existing
    links return 404 but audit history is preserved.
    Verifies ownership through the twin or workspace chain.
    """
    result = await db.execute(
        select(ShareSurface)
        .options(
            selectinload(ShareSurface.twin).selectinload(Twin.workspace),
            selectinload(ShareSurface.workspace),
        )
        .where(ShareSurface.id == surface_id)
    )
    surface = result.scalar_one_or_none()
    if surface is None:
        raise NotFoundError(f"ShareSurface {surface_id} not found")

    # Verify ownership through whichever anchor this surface has
    if surface.doctwin_id is not None:
        if surface.twin is None or surface.twin.workspace.owner_id != user_id:
            raise ForbiddenError("You do not own this share surface")
    elif surface.workspace_id is not None:
        if surface.workspace is None or surface.workspace.owner_id != user_id:
            raise ForbiddenError("You do not own this share surface")
    else:
        raise ForbiddenError("Share surface has no ownership anchor")

    surface.is_active = False
    await db.flush()

    logger.info(
        "share_surface_revoked",
        surface_id=str(surface_id),
    )


async def get_active_surface_by_slug(
    public_slug: str,
    db: AsyncSession,
) -> ShareSurface:
    """
    Load an active share surface by its public slug.

    Returns the surface with twin/workspace loaded for rendering.
    Raises NotFoundError if not found or inactive.
    """
    result = await db.execute(
        select(ShareSurface)
        .options(
            selectinload(ShareSurface.twin),
            selectinload(ShareSurface.workspace),
        )
        .where(
            ShareSurface.public_slug == public_slug,
            ShareSurface.is_active.is_(True),
        )
    )
    surface = result.scalar_one_or_none()
    if surface is None:
        raise NotFoundError(f"No active share surface found for slug: {public_slug}")
    return surface


async def list_surfaces_for_twin(
    doctwin_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[ShareSurface]:
    """List all share surfaces for a twin. Verifies ownership."""
    result_twin = await db.execute(
        select(Twin)
        .options(selectinload(Twin.workspace))
        .where(Twin.id == doctwin_id)
    )
    twin = result_twin.scalar_one_or_none()
    if twin is None:
        raise NotFoundError(f"Twin {doctwin_id} not found")
    if twin.workspace.owner_id != user_id:
        raise ForbiddenError("You do not own this twin's workspace")

    result = await db.execute(
        select(ShareSurface)
        .where(ShareSurface.doctwin_id == doctwin_id, ShareSurface.is_active.is_(True))
        .order_by(ShareSurface.created_at.desc())
    )
    return list(result.scalars().all())


async def list_surfaces_for_workspace(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[ShareSurface]:
    """List all active share surfaces for a workspace. Verifies ownership."""
    await _assert_workspace_owned_by(workspace_id, user_id, db)

    result = await db.execute(
        select(ShareSurface)
        .where(
            ShareSurface.workspace_id == workspace_id,
            ShareSurface.is_active.is_(True),
        )
        .order_by(ShareSurface.created_at.desc())
    )
    return list(result.scalars().all())
