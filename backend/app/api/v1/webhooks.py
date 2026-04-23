"""
Webhook handlers for provider push notifications.

Google Drive: X-Goog-Channel-Token (shared secret compared directly via compare_digest)

Security principles:
  - Signature verification happens BEFORE reading/trusting any payload field.
  - Per-source webhook_secret means a compromised secret for one source cannot
    forge events for another.
  - Unverifiable requests receive 401 immediately with no payload processing.
  - Enqueue is fire-and-forget — we return 200 to the provider quickly and let
    the ingestion worker handle the actual sync.
"""

from __future__ import annotations

import hmac

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.source import Source

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post("/google_drive", status_code=status.HTTP_200_OK)
async def google_drive_webhook(
    x_goog_channel_token: str | None = Header(default=None),
    x_goog_channel_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Receive Google Drive push channel notifications.

    Verifies X-Goog-Channel-Token against the per-source webhook_secret.
    On a valid notification, enqueues the source for re-ingestion.
    """
    if not x_goog_channel_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Goog-Channel-Token header",
        )

    if not x_goog_channel_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Goog-Channel-Id header",
        )

    source = await _find_source_by_webhook_id(x_goog_channel_id, db)
    if source is None:
        logger.warning("gdrive_webhook_source_not_found", channel_id=x_goog_channel_id)
        return {"status": "not_found"}

    if not source.webhook_secret:
        logger.error("gdrive_webhook_no_secret", source_id=str(source.id))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook secret not configured for this source",
        )

    if not verify_google_drive_token(x_goog_channel_token, source.webhook_secret):
        logger.warning(
            "gdrive_webhook_invalid_token",
            source_id=str(source.id),
            channel_id=x_goog_channel_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid channel token",
        )

    await _enqueue_ingestion(str(source.id))
    logger.info(
        "gdrive_webhook_ingestion_enqueued",
        source_id=str(source.id),
        channel_id=x_goog_channel_id,
    )

    return {"status": "queued", "source_id": str(source.id)}


def verify_google_drive_token(
    channel_token: str,
    secret: str,
) -> bool:
    """
    Verify Google Drive's X-Goog-Channel-Token header.

    The token is a plain secret string we set when registering the watch channel.
    Uses compare_digest to prevent timing attacks.
    """
    return hmac.compare_digest(secret, channel_token)


async def _find_source_by_webhook_id(
    webhook_id: str,
    db: AsyncSession,
) -> Source | None:
    """Find a Source by its provider-assigned webhook_id."""
    result = await db.execute(
        select(Source).where(Source.webhook_id == webhook_id)
    )
    return result.scalars().first()


async def _enqueue_ingestion(source_id: str) -> None:
    """
    Enqueue an ingestion job via ARQ.

    Fire-and-forget — we return quickly to the provider and let the worker
    handle the sync. If enqueueing fails, we log the error; the source can
    be re-synced manually via the /sources/{id}/sync endpoint.
    """
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        from app.core.config import get_settings

        settings = get_settings()
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await redis.enqueue_job("ingest_source", source_id)
        await redis.aclose()
    except Exception as exc:
        from app.core.logging import get_logger

        _logger = get_logger(__name__)
        _logger.error("webhook_ingestion_enqueue_failed", source_id=source_id, error=str(exc))
