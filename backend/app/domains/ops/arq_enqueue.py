"""Enqueue ARQ jobs from API and admin paths (single import surface)."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


async def enqueue_ingest_source_job(source_id: str) -> None:
    """
    Enqueue `ingest_source` for a source id.

    Fire-and-forget: short-lived Redis pool. Logs on failure; does not raise
    so callers can still commit DB state when appropriate.
    """
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        from app.core.config import get_settings

        settings = get_settings()
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            await redis.enqueue_job("ingest_source", source_id)
        finally:
            await redis.aclose()
    except Exception as exc:
        logger.error("ingestion_enqueue_failed", source_id=source_id, error=str(exc))
