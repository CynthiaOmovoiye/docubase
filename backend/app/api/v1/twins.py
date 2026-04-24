"""
Twin endpoints.

GET    /twins/?workspace_id=       — list twins in a workspace
POST   /twins/                     — create a twin
GET    /twins/{id}                 — get a twin
PATCH  /twins/{id}                 — update name/description/active
DELETE /twins/{id}                 — delete twin and all sources
GET    /twins/{id}/config          — get policy/display config
PATCH  /twins/{id}/config          — update policy/display config
POST   /twins/{id}/memory/generate — enqueue memory extraction job (202)
GET    /twins/{id}/memory/brief    — fetch generated Memory Brief
GET    /twins/{id}/evidence-health — Phase 0 twin-level index / readiness rollup
"""

import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.redis import get_redis
from app.domains.memory.queue_state import (
    memory_brief_job_id,
    memory_brief_pending_key,
)
from app.domains.twins.service import (
    create_twin,
    delete_twin,
    get_doctwin_config,
    get_doctwin_evidence_health,
    get_twin,
    list_twins,
    update_doctwin_config,
    update_twin,
)
from app.domains.retrieval.router import retrieve_packet_for_twin
from app.models.chunk import Chunk
from app.models.source import Source
from app.models.twin import TwinConfig
from app.models.user import User
from app.schemas.twins import (
    MemoryBriefResponse,
    TwinConfigResponse,
    TwinConfigUpdateRequest,
    TwinCreateRequest,
    TwinEvidenceHealthResponse,
    TwinResponse,
    TwinUpdateRequest,
)

router = APIRouter()


@router.get("/", response_model=list[TwinResponse])
async def list_my_twins(
    workspace_id: uuid.UUID = Query(..., description="Filter twins by workspace"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await list_twins(workspace_id, current_user, db)


@router.post("/", response_model=TwinResponse, status_code=status.HTTP_201_CREATED)
async def create_new_twin(
    payload: TwinCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_twin(payload, current_user, db)


@router.get(
    "/{doctwin_id}/evidence-health",
    response_model=TwinEvidenceHealthResponse,
    summary="Twin evidence health (Phase 0)",
)
async def get_doctwin_evidence_health_endpoint(
    doctwin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregate index coverage and source readiness for this twin.

    Intended for owners and internal tooling — not for anonymous share surfaces.
    """
    payload = await get_doctwin_evidence_health(doctwin_id, current_user, db)
    return TwinEvidenceHealthResponse.model_validate(payload)


@router.get("/{doctwin_id}", response_model=TwinResponse)
async def get_one_twin(
    doctwin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_twin(doctwin_id, current_user, db)


@router.patch("/{doctwin_id}", response_model=TwinResponse)
async def update_one_twin(
    doctwin_id: uuid.UUID,
    payload: TwinUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_twin(doctwin_id, payload, current_user, db)


@router.delete("/{doctwin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one_twin(
    doctwin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await delete_twin(doctwin_id, current_user, db)


@router.get("/{doctwin_id}/config", response_model=TwinConfigResponse)
async def get_config(
    doctwin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_doctwin_config(doctwin_id, current_user, db)


@router.patch("/{doctwin_id}/config", response_model=TwinConfigResponse)
async def update_config(
    doctwin_id: uuid.UUID,
    payload: TwinConfigUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_doctwin_config(doctwin_id, payload, current_user, db)


@router.post("/{doctwin_id}/memory/generate", status_code=status.HTTP_202_ACCEPTED)
async def trigger_memory_generation(
    doctwin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Enqueue a memory extraction job for this twin.

    Ownership is verified before enqueueing. Returns 202 immediately —
    the actual extraction runs asynchronously in the ARQ worker.
    Poll GET /twins/{id}/memory/brief to check status.
    """
    # Verify ownership via twin config (twin must belong to user's workspace)
    await get_twin(doctwin_id, current_user, db)  # raises 403/404 if not owned

    # If the distributed lock is already held, extraction is in progress —
    # don't re-queue or overwrite the status; just acknowledge.
    # Return "generating" (not a custom "already_running" status) so the
    # frontend treats it identically to a freshly queued job and continues
    # to poll GET /memory/brief — it doesn't need to know the distinction.
    redis = get_redis()
    from app.domains.ops.doctwin_memory_queue import enqueue_memory_brief_for_twin

    try:
        return await enqueue_memory_brief_for_twin(doctwin_id=doctwin_id, db=db, redis=redis)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not enqueue memory extraction: {exc}",
        ) from exc


@router.get("/{doctwin_id}/memory/brief", response_model=MemoryBriefResponse)
async def get_memory_brief(
    doctwin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryBriefResponse:
    """
    Return the current Memory Brief for a twin.

    Returns the brief text, status, and generation timestamp.
    Returns 404 if no memory extraction has been run for this twin.
    """
    # Verify ownership
    await get_twin(doctwin_id, current_user, db)  # raises 403/404 if not owned

    result = await db.execute(
        select(TwinConfig).where(TwinConfig.doctwin_id == doctwin_id)
    )
    config = result.scalar_one_or_none()

    if config is None or config.memory_brief_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No memory brief has been generated for this twin yet.",
        )

    reported_status = config.memory_brief_status

    # Derive the authoritative status from live Redis signals rather than
    # relying solely on what the DB recorded. This prevents two failure modes:
    #
    #   1. False "failed": POST /generate sets DB→"generating" and enqueues the
    #      job. If GET /brief is polled in the window before the worker picks up
    #      the job (no lock yet), naive stale detection flips DB→"failed" even
    #      though the job is about to start.
    #
    #   2. Stuck "generating": the worker crashed after acquiring the lock but
    #      before the finally block released it (or the lock TTL hasn't expired).
    #      In this case DB stays "generating" forever.
    #
    # Resolution order:
    #   - If lock held OR ARQ in-progress key exists OR job is in the ARQ queue
    #     → status is definitely "generating", fix the DB if it says otherwise.
    #   - If DB says "generating" AND none of the above → worker crashed/timed
    #     out without cleaning up → flip to "failed".
    #   - Any other DB status → trust the DB (job finished normally).
    job_id = memory_brief_job_id(str(doctwin_id))
    redis = get_redis()

    lock_held = await redis.exists(f"memory_lock:{doctwin_id}")
    job_in_progress = await redis.exists(f"arq:in-progress:{job_id}")
    job_queued = await redis.zscore("arq:queue", job_id)
    pending_flag = await redis.exists(memory_brief_pending_key(str(doctwin_id)))
    # Only treat pending as "in flight" for non-success DB rows; avoids sticking
    # on `ready` if Redis cleanup missed the flag.
    pending_counts = pending_flag and reported_status in ("pending", "generating", "failed")
    is_active = bool(
        lock_held or job_in_progress or job_queued is not None or pending_counts
    )

    if is_active:
        # Job is genuinely running or queued — always report "generating"
        # and repair the DB if a previous failure left it in a bad state.
        if reported_status != "generating":
            await db.execute(
                update(TwinConfig)
                .where(TwinConfig.doctwin_id == doctwin_id)
                .values(memory_brief_status="generating")
            )
            await db.commit()
        reported_status = "generating"
    elif reported_status == "generating":
        # DB says generating but no lock, no in-progress key, not in queue →
        # the worker crashed or timed out without cleaning up. Mark as failed.
        reported_status = "failed"
        await db.execute(
            update(TwinConfig)
            .where(TwinConfig.doctwin_id == doctwin_id)
            .values(memory_brief_status="failed")
        )
        await db.commit()

    return MemoryBriefResponse(
        doctwin_id=doctwin_id,
        status=reported_status,
        generated_at=config.memory_brief_generated_at,
        brief=config.memory_brief,
    )


@router.get("/{doctwin_id}/debug/chunks")
async def debug_chunks(
    doctwin_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Owner-only: inspect what chunks are stored for this twin.

    Returns chunk count by type, embedding coverage, source breakdown,
    and a sample of stored content — useful for diagnosing why retrieval
    or brief generation is producing unexpected results.
    """
    await get_twin(doctwin_id, current_user, db)

    rows = await db.execute(
        text(
            """
            SELECT
                c.chunk_type,
                c.source_ref,
                c.content,
                c.embedding IS NOT NULL AS has_embedding,
                s.name AS source_name,
                s.status AS source_status,
                s.embedding_provider,
                s.embedding_model,
                s.embedding_dimensions
            FROM chunks c
            JOIN sources s ON s.id = c.source_id
            WHERE s.doctwin_id = :doctwin_id
            ORDER BY s.name, c.chunk_type
            """
        ),
        {"doctwin_id": str(doctwin_id)},
    )
    all_rows = rows.fetchall()

    chunk_type_counts: Counter = Counter()
    embedding_by_type: Counter = Counter()
    sources: dict[str, dict] = {}
    samples: list[dict] = []

    for row in all_rows:
        ctype = str(row.chunk_type)
        chunk_type_counts[ctype] += 1
        if row.has_embedding:
            embedding_by_type[ctype] += 1

        src_key = str(row.source_name or row.source_ref or "unknown")
        if src_key not in sources:
            sources[src_key] = {
                "name": src_key,
                "status": str(row.source_status or ""),
                "embedding_provider": row.embedding_provider,
                "embedding_model": row.embedding_model,
                "embedding_dimensions": row.embedding_dimensions,
                "chunk_count": 0,
                "chunks_with_embeddings": 0,
            }
        sources[src_key]["chunk_count"] += 1
        if row.has_embedding:
            sources[src_key]["chunks_with_embeddings"] += 1

        if len(samples) < 5 and not str(row.source_ref or "").startswith("__memory__/"):
            samples.append({
                "chunk_type": ctype,
                "source_ref": row.source_ref,
                "has_embedding": row.has_embedding,
                "content_len": len(row.content or ""),
                "content_preview": (row.content or "")[:300],
            })

    return {
        "doctwin_id": str(doctwin_id),
        "total_chunks": len(all_rows),
        "chunk_types": dict(chunk_type_counts),
        "chunks_with_embeddings": dict(embedding_by_type),
        "sources": list(sources.values()),
        "content_samples": samples,
    }
