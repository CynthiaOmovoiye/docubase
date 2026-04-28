"""
Admin API routes.

Internal/platform-level operations.

ALL routes require a valid authenticated superuser (is_superuser=True).
Any authenticated user who is not a superuser receives 403.
Any unauthenticated request receives 401.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_superuser
from app.core.db import get_db
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.domains.ops.doctwin_memory_queue import enqueue_memory_brief_for_twin
from app.domains.ops.platform_stats import fetch_platform_stats
from app.domains.retrieval.diagnostics import collect_twin_rag_index_stats, preview_twin_retrieval
from app.domains.users.service import create_operator_user
from app.models.twin import Twin
from app.models.user import User
from app.schemas.admin import (
    AdminCreateOperatorRequest,
    AdminIngestionLogsResponse,
    AdminPlatformStatsResponse,
    AdminRagChunkTypeRow,
    AdminRagEmbeddingProfileRow,
    AdminRagSourceRow,
    AdminTwinMaintenanceResponse,
    AdminTwinRagDiagnosticsResponse,
    AdminUserListResponse,
    AdminUserRoleUpdate,
    AdminUserRow,
)

router = APIRouter()
logger = get_logger(__name__)


async def _require_twin(doctwin_id: uuid.UUID, db: AsyncSession) -> None:
    row = await db.execute(select(Twin.id).where(Twin.id == doctwin_id))
    if row.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Twin not found")


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    current_user: User = Depends(get_superuser),
    db: AsyncSession = Depends(get_db),
    consumers_only: bool = Query(
        False,
        description="When true, return only consumer accounts (exclude platform operators).",
    ),
):
    """
    Registered accounts (max 500, newest first). Superuser only.

    Use ``consumers_only=true`` for the signups view — operators are system accounts and stay
    on the Admin users list only.
    """
    stmt = select(User).order_by(User.created_at.desc()).limit(500)
    if consumers_only:
        stmt = stmt.where(User.is_superuser.is_(False))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    logger.info(
        "admin_users_list",
        admin_user_id=str(current_user.id),
        count=len(rows),
        consumers_only=consumers_only,
    )
    return AdminUserListResponse(users=[AdminUserRow.model_validate(u) for u in rows])


@router.post(
    "/users/operators",
    response_model=AdminUserRow,
    status_code=status.HTTP_201_CREATED,
)
async def create_operator(
    payload: AdminCreateOperatorRequest,
    current_user: User = Depends(get_superuser),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new operator account (superuser).

    The email must not belong to an existing user. Does not auto-create a workspace.
    """
    user = await create_operator_user(payload, db)

    logger.info(
        "admin_operator_created",
        admin_user_id=str(current_user.id),
        target_user_id=str(user.id),
        email=user.email,
    )
    return AdminUserRow.model_validate(user)


@router.patch("/users/{user_id}", response_model=AdminUserRow)
async def update_user_superuser_flag(
    user_id: uuid.UUID,
    payload: AdminUserRoleUpdate,
    current_user: User = Depends(get_superuser),
    db: AsyncSession = Depends(get_db),
):
    """
    Promote or demote platform admin (`is_superuser`).

    Cannot remove your own superuser access (prevents lockout).
    """
    if user_id == current_user.id and not payload.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove your own superuser access",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    target.is_superuser = payload.is_superuser
    db.add(target)
    await db.flush()

    logger.info(
        "admin_user_superuser_updated",
        admin_user_id=str(current_user.id),
        target_user_id=str(user_id),
        is_superuser=payload.is_superuser,
    )
    return AdminUserRow.model_validate(target)


@router.get("/stats", response_model=AdminPlatformStatsResponse)
async def get_stats(
    current_user: User = Depends(get_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Platform-wide counts. Superuser only."""
    data = await fetch_platform_stats(db)
    logger.info(
        "admin_platform_stats",
        admin_user_id=str(current_user.id),
        **data,
    )
    return AdminPlatformStatsResponse.model_validate(data)


@router.get("/ingestion-logs", response_model=AdminIngestionLogsResponse)
async def get_ingestion_logs(
    current_user: User = Depends(get_superuser),
    db: AsyncSession = Depends(get_db),
):
    """Recent ingestion job logs. Superuser only (placeholder until persisted)."""
    _ = db  # reserved for future query
    logger.info("admin_ingestion_logs_view", admin_user_id=str(current_user.id))
    return AdminIngestionLogsResponse()


@router.get(
    "/twins/{doctwin_id}/rag-diagnostics",
    response_model=AdminTwinRagDiagnosticsResponse,
)
async def admin_twin_rag_diagnostics(
    doctwin_id: uuid.UUID,
    q: str | None = Query(
        default=None,
        max_length=2000,
        description="Optional user message; when set, runs retrieve_packet_for_twin and returns hits.",
    ),
    current_user: User = Depends(get_superuser),
    db: AsyncSession = Depends(get_db),
):
    """
    Inspect indexed sources, embedding coverage, and (optionally) retrieval for ``q``.

    Use when the knowledge brief or chat answers do not reflect uploaded documents.
    """
    await _require_twin(doctwin_id, db)
    stats = await collect_twin_rag_index_stats(str(doctwin_id), db)
    retrieval_preview = None
    if q and q.strip():
        retrieval_preview = await preview_twin_retrieval(
            doctwin_id=str(doctwin_id),
            query=q.strip(),
            db=db,
            top_k=12,
        )
    logger.info(
        "admin_rag_diagnostics",
        admin_user_id=str(current_user.id),
        doctwin_id=str(doctwin_id),
        preview=bool(retrieval_preview),
    )
    return AdminTwinRagDiagnosticsResponse(
        doctwin_id=str(doctwin_id),
        sources=[AdminRagSourceRow.model_validate(s) for s in stats["sources"]],
        chunk_types_ready_non_memory=[
            AdminRagChunkTypeRow.model_validate(r) for r in stats["chunk_types_ready_non_memory"]
        ],
        embedding_profiles_from_indexed_chunks=[
            AdminRagEmbeddingProfileRow.model_validate(p)
            for p in stats["embedding_profiles_from_indexed_chunks"]
        ],
        retrieval_preview=retrieval_preview,
    )


@router.post(
    "/twins/{doctwin_id}/memory/rebuild",
    response_model=AdminTwinMaintenanceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def admin_rebuild_doctwin_memory(
    doctwin_id: uuid.UUID,
    current_user: User = Depends(get_superuser),
    db: AsyncSession = Depends(get_db),
):
    """
    Enqueue memory extraction for any twin (no workspace ownership check).

    Use for operator recovery; owners should prefer POST /twins/{id}/memory/generate.
    """
    await _require_twin(doctwin_id, db)
    redis = get_redis()
    try:
        detail = await enqueue_memory_brief_for_twin(doctwin_id=doctwin_id, db=db, redis=redis)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not enqueue memory extraction: {exc}",
        ) from exc

    logger.info(
        "admin_doctwin_memory_rebuild",
        admin_user_id=str(current_user.id),
        doctwin_id=str(doctwin_id),
        **detail,
    )
    return AdminTwinMaintenanceResponse(doctwin_id=str(doctwin_id), action="memory_rebuild", detail=detail)


