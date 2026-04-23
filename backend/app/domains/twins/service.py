"""
Twin domain service.

Create, read, update, delete twins and their configs.
All operations are scoped to the owning workspace/user.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.domains.evaluation.twin_evidence_health import build_twin_evidence_health_summary
from app.models.source import Source
from app.models.twin import Twin, TwinConfig
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.twins import (
    TwinConfigUpdateRequest,
    TwinCreateRequest,
    TwinUpdateRequest,
)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.lower()).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    return re.sub(r"-+", "-", slug).strip("-")[:60] or "twin"


async def _get_workspace_for_user(
    workspace_id: uuid.UUID, user: User, db: AsyncSession
) -> Workspace:
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    ws = result.scalar_one_or_none()
    if ws is None or ws.owner_id != user.id:
        raise NotFoundError(f"Workspace {workspace_id} not found")
    return ws


async def list_twins(workspace_id: uuid.UUID, user: User, db: AsyncSession) -> list[Twin]:
    await _get_workspace_for_user(workspace_id, user, db)
    result = await db.execute(
        select(Twin)
        .where(Twin.workspace_id == workspace_id)
        .options(selectinload(Twin.config))
        .order_by(Twin.created_at)
    )
    return list(result.scalars().all())


async def create_twin(
    payload: TwinCreateRequest,
    user: User,
    db: AsyncSession,
) -> Twin:
    await _get_workspace_for_user(payload.workspace_id, user, db)

    slug = payload.slug or _slugify(payload.name)
    slug = await _unique_twin_slug(slug, payload.workspace_id, db)

    twin = Twin(
        name=payload.name,
        slug=slug,
        description=payload.description,
        workspace_id=payload.workspace_id,
    )
    db.add(twin)
    await db.flush()

    # Every twin gets a default config on creation
    config = TwinConfig(twin_id=twin.id)
    db.add(config)
    await db.flush()

    # Reload with config relationship
    result = await db.execute(
        select(Twin).where(Twin.id == twin.id).options(selectinload(Twin.config))
    )
    return result.scalar_one()


async def get_twin_evidence_health(
    twin_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> dict:
    """
    Aggregate index_health across all sources on the twin (Phase 0).

    Returns a plain dict matching TwinEvidenceHealthResponse.
    """
    twin = await get_twin(twin_id, user, db)
    result = await db.execute(select(Source).where(Source.twin_id == twin_id))
    sources = list(result.scalars().all())
    mb_status = twin.config.memory_brief_status if twin.config else None
    summary = build_twin_evidence_health_summary(
        sources=sources,
        memory_brief_status=mb_status,
    )
    return {"twin_id": twin.id, **summary}


async def get_twin(twin_id: uuid.UUID, user: User, db: AsyncSession) -> Twin:
    result = await db.execute(
        select(Twin)
        .where(Twin.id == twin_id)
        .options(selectinload(Twin.config))
    )
    twin = result.scalar_one_or_none()
    if twin is None:
        raise NotFoundError(f"Twin {twin_id} not found")

    # Verify ownership via workspace
    await _get_workspace_for_user(twin.workspace_id, user, db)
    return twin


async def update_twin(
    twin_id: uuid.UUID,
    payload: TwinUpdateRequest,
    user: User,
    db: AsyncSession,
) -> Twin:
    twin = await get_twin(twin_id, user, db)
    if payload.name is not None:
        twin.name = payload.name
    if payload.description is not None:
        twin.description = payload.description
    if payload.is_active is not None:
        twin.is_active = payload.is_active
    db.add(twin)
    await db.flush()
    # Re-query to get fresh column values (updated_at is server-side onupdate)
    # and reload the config relationship, which Pydantic serialization will access.
    result = await db.execute(
        select(Twin).where(Twin.id == twin.id).options(selectinload(Twin.config))
    )
    return result.scalar_one()


async def delete_twin(twin_id: uuid.UUID, user: User, db: AsyncSession) -> None:
    twin = await get_twin(twin_id, user, db)
    await db.delete(twin)
    await db.flush()


async def get_twin_config(twin_id: uuid.UUID, user: User, db: AsyncSession) -> TwinConfig:
    twin = await get_twin(twin_id, user, db)
    if twin.config is None:
        raise NotFoundError(f"Config for twin {twin_id} not found")
    return twin.config


async def update_twin_config(
    twin_id: uuid.UUID,
    payload: TwinConfigUpdateRequest,
    user: User,
    db: AsyncSession,
) -> TwinConfig:
    config = await get_twin_config(twin_id, user, db)

    if payload.allow_code_snippets is not None:
        config.allow_code_snippets = payload.allow_code_snippets
    if payload.is_public is not None:
        config.is_public = payload.is_public
    if payload.display_name is not None:
        config.display_name = payload.display_name
    if payload.accent_color is not None:
        config.accent_color = payload.accent_color
    if payload.custom_context is not None:
        config.custom_context = payload.custom_context

    db.add(config)
    await db.flush()
    # Refresh to populate server-generated columns (updated_at, etc.) before
    # returning — without this, Pydantic serialization outside the async context
    # triggers SQLAlchemy lazy-loading, which raises MissingGreenlet.
    await db.refresh(config)
    return config


async def _unique_twin_slug(
    base: str, workspace_id: uuid.UUID, db: AsyncSession
) -> str:
    import random, string
    slug = base
    for _ in range(10):
        result = await db.execute(
            select(Twin).where(Twin.slug == slug, Twin.workspace_id == workspace_id)
        )
        if result.scalar_one_or_none() is None:
            return slug
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        slug = f"{base}-{suffix}"
    raise ConflictError("Could not generate a unique twin slug")
