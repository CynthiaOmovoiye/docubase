"""Enqueue ARQ jobs from API and admin paths (single import surface)."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


async def enqueue_ingest_source_job(source_id: str, request_id: str | None = None) -> None:
    """
    Enqueue `ingest_source` for a source id.

    `request_id` is an optional correlation token from the originating HTTP
    request. When provided it is passed into the job payload so every log
    event the worker emits carries the same ID — making it possible to
    reconstruct the full journey from API call → background job in a single
    log query.

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
            await redis.enqueue_job("ingest_source", source_id, request_id=request_id)
        finally:
            await redis.aclose()
    except Exception as exc:
        logger.error(
            "ingestion_enqueue_failed",
            source_id=source_id,
            request_id=request_id,
            error=str(exc),
        )
