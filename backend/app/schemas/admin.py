"""Admin API response models (Phase 7)."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
