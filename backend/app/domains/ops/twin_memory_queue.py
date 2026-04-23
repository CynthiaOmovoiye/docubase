"""
Enqueue memory brief regeneration for a twin (Phase 7 / twin maintenance).

Callers must enforce authorization (owner or superuser).
"""

from __future__ import annotations

import uuid

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domains.memory.queue_state import (
    PENDING_TTL_SECONDS,
    clear_memory_brief_arq_job,
    memory_brief_job_id,
    memory_brief_pending_key,
)
from app.models.twin import TwinConfig

logger = get_logger(__name__)


async def enqueue_memory_brief_for_twin(
    *,
    twin_id: uuid.UUID,
    db: AsyncSession,
    redis,
) -> dict:
    """
    Match twin owner POST /twins/{id}/memory/generate semantics.

    Returns {"status": "generating"|"queued", "twin_id": str}.
    """
    twin_id_str = str(twin_id)
    lock_key = f"memory_lock:{twin_id}"
    if await redis.exists(lock_key):
        return {"status": "generating", "twin_id": twin_id_str}

    job_id = memory_brief_job_id(twin_id_str)
    await clear_memory_brief_arq_job(redis, twin_id_str)

    await db.execute(
        update(TwinConfig)
        .where(TwinConfig.twin_id == twin_id)
        .values(memory_brief_status="generating")
    )
    await db.commit()

    settings = get_settings()
    redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await redis_pool.enqueue_job(
            "generate_memory_brief",
            twin_id_str,
            _job_id=job_id,
        )
    finally:
        await redis_pool.aclose()

    await redis.setex(memory_brief_pending_key(twin_id_str), PENDING_TTL_SECONDS, "1")
    return {"status": "queued", "twin_id": twin_id_str}
