"""
Workspace domain service.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspaces import WorkspaceCreateRequest, WorkspaceUpdateRequest


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.lower()).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:60] or "workspace"


async def list_workspaces(user: User, db: AsyncSession) -> list[Workspace]:
    result = await db.execute(
        select(Workspace).where(Workspace.owner_id == user.id).order_by(Workspace.created_at)
    )
    return list(result.scalars().all())


async def create_workspace(
    payload: WorkspaceCreateRequest,
    user: User,
    db: AsyncSession,
) -> Workspace:
    slug = payload.slug or _slugify(payload.name)
    slug = await _unique_slug(slug, db)

    workspace = Workspace(
        name=payload.name,
        slug=slug,
        description=payload.description,
        owner_id=user.id,
    )
    db.add(workspace)
    await db.flush()
    return workspace


async def get_workspace(
    workspace_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Workspace:
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    ws = result.scalar_one_or_none()
    if ws is None or ws.owner_id != user.id:
        raise NotFoundError(f"Workspace {workspace_id} not found")
    return ws


async def update_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdateRequest,
    user: User,
    db: AsyncSession,
) -> Workspace:
    ws = await get_workspace(workspace_id, user, db)
    if payload.name is not None:
        ws.name = payload.name
    if payload.description is not None:
        ws.description = payload.description
    db.add(ws)
    await db.flush()
    return ws


async def delete_workspace(
    workspace_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> None:
    ws = await get_workspace(workspace_id, user, db)
    await db.delete(ws)
    await db.flush()


async def _unique_slug(base: str, db: AsyncSession) -> str:
    """Find an unused slug, handling concurrent inserts via IntegrityError catch."""
    import random
    import string

    slug = base
    for _ in range(10):
        try:
            result = await db.execute(select(Workspace).where(Workspace.slug == slug))
            if result.scalar_one_or_none() is None:
                return slug
        except IntegrityError:
            # A concurrent insert grabbed this slug between our SELECT and INSERT.
            # Treat as taken and generate a new candidate.
            pass
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        slug = f"{base}-{suffix}"
    raise ConflictError("Could not generate a unique workspace slug")
