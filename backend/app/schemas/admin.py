"""Admin API response models (Phase 7)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.users import UserRegisterRequest


class AdminCreateOperatorRequest(UserRegisterRequest):
    """Provision a new platform operator account. Email must not exist."""

    pass


class AdminUserRow(BaseModel):
    """Public-safe user row for operator lists (no password hash)."""

    id: uuid.UUID
    email: str
    display_name: str | None
    is_active: bool
    is_verified: bool
    is_superuser: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserListResponse(BaseModel):
    users: list[AdminUserRow]


class AdminUserRoleUpdate(BaseModel):
    is_superuser: bool


class AdminPlatformStatsResponse(BaseModel):
    users: int
    workspaces: int
    twins: int
    sources_total: int
    sources_by_status: dict[str, int] = Field(default_factory=dict)


class AdminTwinMaintenanceResponse(BaseModel):
    doctwin_id: str
    action: str
    detail: dict = Field(default_factory=dict)


class AdminIngestionLogsResponse(BaseModel):
    """Placeholder until ingestion job history is persisted."""

    items: list[dict] = Field(default_factory=list)
    note: str = "Ingestion job history is not persisted yet; use worker logs."


class AdminRagSourceRow(BaseModel):
    """Per-source indexing and embedding coverage for a twin."""

    source_id: str
    name: str
    status: str
    source_type: str
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    chunk_count: int = 0
    chunks_with_embedding: int = 0
    chunks_without_embedding: int = 0


class AdminRagChunkTypeRow(BaseModel):
    chunk_type: str
    count: int
    with_embedding: int


class AdminRagEmbeddingProfileRow(BaseModel):
    provider: str
    model: str
    dimensions: int


class AdminRagRetrievalHit(BaseModel):
    chunk_id: str
    score: float
    chunk_type: str
    source_ref: str
    source_id: str
    match_reasons: list[str] = Field(default_factory=list)
    content_preview: str = ""


class AdminTwinRagDiagnosticsResponse(BaseModel):
    """
    Superuser-only snapshot: sources, embedding coverage, chunk types,
    and optional dry-run retrieval for a query string.
    """

    doctwin_id: str
    sources: list[AdminRagSourceRow]
    chunk_types_ready_non_memory: list[AdminRagChunkTypeRow]
    embedding_profiles_from_indexed_chunks: list[AdminRagEmbeddingProfileRow]
    retrieval_preview: dict | None = Field(
        default=None,
        description="Present when query parameter q was non-empty.",
    )
