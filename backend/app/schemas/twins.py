"""
Twin and TwinConfig schemas.
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TwinCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    workspace_id: uuid.UUID

    @field_validator("slug", mode="before")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.lower().strip()
        if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", v):
            raise ValueError(
                "Slug must contain only lowercase letters, numbers, and hyphens"
            )
        return v


class TwinUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    is_active: bool | None = None


class TwinConfigUpdateRequest(BaseModel):
    allow_code_snippets: bool | None = None
    is_public: bool | None = None
    display_name: str | None = Field(default=None, max_length=120)
    accent_color: str | None = Field(default=None, max_length=7)
    custom_context: str | None = Field(default=None, max_length=2000)

    @field_validator("accent_color")
    @classmethod
    def validate_hex_color(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^#[0-9a-fA-F]{6}$", v):
            raise ValueError("accent_color must be a valid hex color (e.g. #6366F1)")
        return v


class TwinConfigResponse(BaseModel):
    """Full config — returned to authenticated owners only."""
    id: uuid.UUID
    doctwin_id: uuid.UUID
    allow_code_snippets: bool
    is_public: bool
    display_name: str | None
    accent_color: str | None
    custom_context: str | None  # owner-only — never return on public surfaces
    updated_at: datetime
    # Engineering Memory fields — owner-only
    memory_brief_status: str | None = None
    memory_brief_generated_at: datetime | None = None
    memory_brief: str | None = None  # full brief text — NOT on public surfaces

    model_config = {"from_attributes": True}


class PublicTwinConfigResponse(BaseModel):
    """
    Minimal config safe to return on public share surfaces.

    Deliberately excludes:
    - custom_context  (owner may embed sensitive operational notes)
    - allow_code_snippets  (internal policy flag)
    - memory_brief  (may contain architectural detail not approved for public)
    - memory_brief_status / memory_brief_generated_at
    """
    display_name: str | None
    accent_color: str | None
    is_public: bool

    model_config = {"from_attributes": True}


class MemoryBriefResponse(BaseModel):
    """
    Response for the GET /twins/{doctwin_id}/memory/brief endpoint.

    Returned to authenticated owners only. Contains the generated brief
    and its generation metadata. `brief` may be None when status is not ready.
    """
    doctwin_id: uuid.UUID
    status: str | None
    generated_at: datetime | None
    brief: str | None

    model_config = {"from_attributes": True}


class TwinResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    is_active: bool
    workspace_id: uuid.UUID
    config: TwinConfigResponse | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TwinEvidenceHealthResponse(BaseModel):
    """
    Phase 0 — twin-level rollup of source index_health + memory brief status.

    Used by dashboards and debugging to see whether evidence is strong enough
    for high-authority answers before blaming retrieval or the model.
    """

    doctwin_id: uuid.UUID
    source_count: int
    ready_source_count: int
    non_ready_source_count: int
    legacy_source_count: int
    strict_source_count: int
    min_parser_coverage_ratio: float | None = None
    min_strict_coverage_ratio: float | None = None
    canonical_mirror_ready_count: int = 0
    canonical_mirror_file_count: int = 0
    implementation_fact_count: int = 0
    any_strict_evidence_not_ready: bool
    memory_brief_status: str | None = None
