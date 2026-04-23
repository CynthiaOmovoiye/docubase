"""
Sources domain service.

Handles CRUD for Sources attached to Twins.

Ownership is enforced by verifying the full chain:
  source → twin → workspace → workspace.owner_id == user.id

This service never exposes raw source content or connection secrets.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.source import Source, SourceIndexMode, SourceStatus, SourceType
from app.models.twin import Twin

logger = get_logger(__name__)


class NotFoundError(Exception):
    pass


class ForbiddenError(Exception):
    pass


class ValidationError(Exception):
    pass


async def assert_doctwin_owned_by(
    doctwin_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Twin:
    """
    Load a Twin and verify the authenticated user owns its workspace.

    Raises NotFoundError if the twin doesn't exist.
    Raises ForbiddenError if the user doesn't own the workspace.
    """
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


async def assert_source_owned_by(
    source_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Source:
    """
    Load a Source and verify the authenticated user owns the twin's workspace.

    Raises NotFoundError, ForbiddenError.
    """
    result = await db.execute(
        select(Source)
        .options(
            selectinload(Source.twin).selectinload(Twin.workspace)
        )
        .where(Source.id == source_id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise NotFoundError(f"Source {source_id} not found")
    if source.twin.workspace.owner_id != user_id:
        raise ForbiddenError("You do not own this source's twin")
    return source


async def list_sources(
    doctwin_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[Source]:
    """List all sources attached to a twin. Verifies ownership."""
    await assert_doctwin_owned_by(doctwin_id, user_id, db)

    result = await db.execute(
        select(Source)
        .where(
            Source.doctwin_id == doctwin_id,
            Source.name != "__memory__",
        )
        .order_by(Source.created_at)
    )
    return list(result.scalars().all())


async def list_legacy_backfill_candidates(
    doctwin_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[Source]:
    """
    Return legacy-index sources that are eligible for a backfill re-sync.
    """
    await assert_doctwin_owned_by(doctwin_id, user_id, db)
    result = await db.execute(
        select(Source)
        .where(
            Source.doctwin_id == doctwin_id,
            Source.name != "__memory__",
        )
        .order_by(Source.created_at)
    )
    sources = list(result.scalars().all())
    return [source for source in sources if _is_backfill_candidate(source)]


async def attach_source(
    doctwin_id: uuid.UUID,
    user_id: uuid.UUID,
    source_type: SourceType,
    name: str,
    connection_config: dict,
    db: AsyncSession,
    connected_account_id: uuid.UUID | None = None,
) -> Source:
    """
    Attach a new source to a twin.

    Validates input, creates the Source record, and returns it.
    The caller is responsible for enqueuing the background ingestion job.
    """
    await assert_doctwin_owned_by(doctwin_id, user_id, db)
    _validate_connection_config(source_type, connection_config)

    source = Source(
        id=uuid.uuid4(),
        doctwin_id=doctwin_id,
        source_type=source_type,
        name=name,
        status=SourceStatus.pending,
        connection_config=_sanitize_connection_config(connection_config),
        connected_account_id=connected_account_id,
    )
    db.add(source)
    await db.flush()
    await db.refresh(source)

    logger.info(
        "source_attached",
        source_id=str(source.id),
        source_type=source_type.value,
        doctwin_id=str(doctwin_id),
    )
    return source


async def get_source(
    source_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Source:
    """Get a source by ID. Verifies ownership."""
    return await assert_source_owned_by(source_id, user_id, db)


async def detach_source(
    source_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """
    Detach and delete a source.

    Cascade deletes all associated chunks.
    """
    source = await assert_source_owned_by(source_id, user_id, db)
    await db.delete(source)
    await db.flush()

    logger.info(
        "source_detached",
        source_id=str(source_id),
        doctwin_id=str(source.doctwin_id),
    )


async def update_source_status(
    source_id: str,
    status: SourceStatus,
    last_error: str | None,
    db: AsyncSession,
) -> None:
    """
    Update source ingestion status.

    Called by background ingestion jobs — no ownership check here
    since jobs run as the system, not as a user.
    """
    result = await db.execute(
        select(Source).where(Source.id == uuid.UUID(source_id))
    )
    source = result.scalar_one_or_none()
    if source is None:
        logger.warning("update_source_status_not_found", source_id=source_id)
        return

    source.status = status
    source.last_error = last_error
    await db.flush()


async def mark_sources_pending_for_backfill(
    source_ids: list[str],
    db: AsyncSession,
) -> int:
    """
    Mark a set of sources as pending so they can be re-ingested for backfill.
    """
    updated = 0
    for raw_source_id in source_ids:
        result = await db.execute(
            select(Source).where(Source.id == uuid.UUID(raw_source_id))
        )
        source = result.scalar_one_or_none()
        if source is None:
            continue
        source.status = SourceStatus.pending
        source.last_error = None
        updated += 1
    await db.flush()
    return updated


async def mark_source_ingesting(source_id: str, db: AsyncSession) -> None:
    await update_source_status(source_id, SourceStatus.ingesting, None, db)


async def mark_source_processing(source_id: str, db: AsyncSession) -> None:
    await update_source_status(source_id, SourceStatus.processing, None, db)


async def mark_source_ready(source_id: str, db: AsyncSession) -> None:
    await update_source_status(source_id, SourceStatus.ready, None, db)


async def mark_source_failed(source_id: str, error: str, db: AsyncSession) -> None:
    await update_source_status(source_id, SourceStatus.failed, error[:2000], db)


async def mark_processing_sources_ready(doctwin_id: str, db: AsyncSession) -> int:
    result = await db.execute(
        select(Source).where(
            Source.doctwin_id == uuid.UUID(doctwin_id),
            Source.status == SourceStatus.processing,
            Source.name != "__memory__",
        )
    )
    sources = list(result.scalars().all())
    for source in sources:
        source.status = SourceStatus.ready
        source.last_error = None
    await db.flush()
    return len(sources)


async def mark_processing_sources_failed(
    doctwin_id: str,
    error: str,
    db: AsyncSession,
) -> int:
    result = await db.execute(
        select(Source).where(
            Source.doctwin_id == uuid.UUID(doctwin_id),
            Source.status == SourceStatus.processing,
            Source.name != "__memory__",
        )
    )
    sources = list(result.scalars().all())
    for source in sources:
        source.status = SourceStatus.failed
        source.last_error = error[:2000]
    await db.flush()
    return len(sources)


# ─── Validation helpers ───────────────────────────────────────────────────────

def _validate_connection_config(source_type: SourceType, config: dict) -> None:
    """
    Validate that a connection_config has the required fields for its type.

    Raises ValidationError on invalid input.
    Does NOT validate secrets — only structure.
    """
    if source_type == SourceType.pdf:
        if not config.get("file_path"):
            raise ValidationError("pdf source requires 'file_path'")

    elif source_type == SourceType.markdown:
        # Markdown can be pasted directly (content) or uploaded as a file (file_path)
        if not config.get("content") and not config.get("file_path"):
            raise ValidationError("markdown source requires 'content' or 'file_path'")

    elif source_type == SourceType.google_drive:
        if not config.get("folder_id") and not config.get("file_id"):
            raise ValidationError(
                "google_drive source requires 'folder_id' (for a folder) "
                "or 'file_id' (for a single file)"
            )

    elif source_type == SourceType.url:
        if not config.get("url"):
            raise ValidationError("url source requires 'url'")

    elif source_type == SourceType.manual and not config.get("content"):
        raise ValidationError("manual source requires 'content'")

def _sanitize_connection_config(config: dict) -> dict:
    """
    Remove any accidental secret values from a connection_config before storage.

    The connection_config should contain references to secrets (e.g., env var names),
    not the secrets themselves. We strip common secret key patterns defensively.
    """
    banned_keys = {
        "password", "secret", "token", "api_key", "access_token",
        "private_key", "client_secret", "auth_token",
    }
    sanitized = {}
    for key, value in config.items():
        if any(banned in key.lower() for banned in banned_keys):
            # Log a warning but don't fail — just omit the sensitive key
            logger.warning(
                "connection_config_secret_key_stripped",
                key=key,
            )
            continue
        sanitized[key] = value
    return sanitized


def _is_backfill_candidate(source: Any) -> bool:
    index_mode = getattr(source, "index_mode", None)
    status = getattr(source, "status", None)
    if index_mode != SourceIndexMode.legacy and str(index_mode) != SourceIndexMode.legacy.value:
        return False
    return status in {
        SourceStatus.ready,
        SourceStatus.failed,
        SourceStatus.needs_resync,
    }
