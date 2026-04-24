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
    doctwin_id: uuid.UUID,
    db: AsyncSession,
    redis,
) -> dict:
    """
    Match twin owner POST /twins/{id}/memory/generate semantics.

    Returns {"status": "generating"|"queued", "doctwin_id": str}.
    """
    doctwin_id_str = str(doctwin_id)
    lock_key = f"memory_lock:{doctwin_id}"
    if await redis.exists(lock_key):
        return {"status": "generating", "doctwin_id": doctwin_id_str}

    job_id = memory_brief_job_id(doctwin_id_str)
    await clear_memory_brief_arq_job(redis, doctwin_id_str)

    await db.execute(
        update(TwinConfig)
        .where(TwinConfig.doctwin_id == doctwin_id)
        .values(memory_brief_status="generating")
    )
    await db.commit()

    settings = get_settings()
    redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await redis_pool.enqueue_job(
            "generate_memory_brief",
            doctwin_id_str,
            _job_id=job_id,
        )
    finally:
        await redis_pool.aclose()

    await redis.setex(memory_brief_pending_key(doctwin_id_str), PENDING_TTL_SECONDS, "1")
    return {"status": "queued", "doctwin_id": doctwin_id_str}
