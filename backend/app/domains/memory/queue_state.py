"""
Redis coordination for memory-brief ARQ jobs.

ARQ refuses to enqueue a job when `arq:job:{job_id}` or `arq:result:{job_id}`
still exists (see arq.connections.ArqRedis.enqueue_job). After a run finishes,
the result key often remains, so POST /memory/generate must clear stale keys
before enqueueing again — otherwise the DB is set to "generating" but no job
runs, and GET /memory/brief falsely marks the twin as failed.
"""

from __future__ import annotations

from arq.constants import default_queue_name, job_key_prefix, result_key_prefix

# Longer than WorkerSettings.job_timeout so polling stays "generating" until cleanup.
PENDING_TTL_SECONDS = 720


def memory_brief_job_id(twin_id: str) -> str:
    return f"memory_brief_{twin_id}"


def memory_brief_pending_key(twin_id: str) -> str:
    return f"memory_brief_pending:{twin_id}"


async def clear_memory_brief_arq_job(redis, twin_id: str) -> None:
    """Remove stale ARQ job/result rows and queued score so enqueue_job can run."""
    jid = memory_brief_job_id(twin_id)
    await redis.delete(job_key_prefix + jid, result_key_prefix + jid)
    await redis.zrem(default_queue_name, jid)
