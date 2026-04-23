"""
Source schemas.

AttachSourceRequest is what the owner sends when connecting a new knowledge source.
SourceResponse is what the API returns — never includes raw secrets or content.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.source import SourceIndexMode, SourceStatus, SourceType


class AttachSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_type: SourceType
    # Connection config is type-specific. Validated at the service layer.
    # Examples:
    #   github_repo: {"repo_url": "owner/repo", "branch": "main"}
    #   pdf:         {"file_path": "/uploads/resume.pdf"}
    #   manual:      {"content": "This project does X..."}
    connection_config: dict[str, Any] = Field(default_factory=dict)
    # Optional — links the source to a ConnectedAccount for OAuth-backed types.
    # Required for github_repo, gitlab_repo, and google_drive so the ingestion
    # job can resolve the access token at sync time.
    connected_account_id: uuid.UUID | None = None

    @field_validator("connection_config")
    @classmethod
    def validate_config_not_empty_for_some_types(cls, v: dict) -> dict:
        # Coerce None values to empty dict
        return v or {}


class SourceResponse(BaseModel):
    """
    Safe source representation.

    Never includes raw file content or secrets.
    connection_config is stripped of sensitive fields before being returned.
    """
    id: uuid.UUID
    twin_id: uuid.UUID
    name: str
    source_type: SourceType
    status: SourceStatus
    last_error: str | None
    snapshot_id: str | None
    snapshot_root_hash: str | None
    index_mode: SourceIndexMode
    index_health: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    # Sanitised connection config — only non-sensitive fields
    connection_summary: dict[str, Any]

    model_config = {"from_attributes": True}

    @classmethod
    def from_source(cls, source: Any) -> "SourceResponse":
        """Build from ORM Source, stripping sensitive config keys."""
        safe_keys = {"repo_url", "branch", "url", "file_name", "source_type"}
        summary = {
            k: v for k, v in source.connection_config.items()
            if k in safe_keys
        }
        health = _enrich_index_health(source)
        return cls(
            id=source.id,
            twin_id=source.twin_id,
            name=source.name,
            source_type=source.source_type,
            status=source.status,
            last_error=source.last_error,
            snapshot_id=source.snapshot_id,
            snapshot_root_hash=source.snapshot_root_hash,
            index_mode=source.index_mode,
            index_health=health,
            created_at=source.created_at,
            updated_at=source.updated_at,
            connection_summary=summary,
        )


class TriggerSyncResponse(BaseModel):
    source_id: uuid.UUID
    message: str


class BackfillLegacySourcesResponse(BaseModel):
    twin_id: uuid.UUID
    queued_sources: int
    source_ids: list[uuid.UUID]
    message: str


def _enrich_index_health(source: Any) -> dict[str, Any]:
    health = dict(source.index_health or {})

    implementation = dict(health.get("implementation_index") or {})
    if implementation:
        parser_coverage_ratio = float(implementation.get("parser_coverage_ratio") or 0.0)
        implementation["parser_coverage_percent"] = round(parser_coverage_ratio * 100, 1)
    health["implementation_index"] = implementation

    freshness = dict(health.get("freshness") or {})
    last_indexed_at = _parse_iso_datetime(
        freshness.get("last_indexed_at")
        or (source.updated_at.isoformat() if source.status == SourceStatus.ready else None)
    )
    stale_after_hours = int(freshness.get("stale_after_hours") or 24)
    age_hours: float | None = None
    age_minutes: int | None = None
    is_stale = False
    label = "Unknown"
    reason: str | None = None

    if source.status in {SourceStatus.ingesting, SourceStatus.processing, SourceStatus.pending}:
        label = "Updating"
    elif source.status == SourceStatus.needs_resync:
        label = "Stale"
        is_stale = True
        reason = "Source is queued for re-sync."
    elif source.status == SourceStatus.failed:
        label = "Stale"
        is_stale = True
        reason = source.last_error or "Latest sync failed."
    elif last_indexed_at is not None:
        delta = datetime.now(UTC) - last_indexed_at
        age_hours = round(delta.total_seconds() / 3600, 2)
        age_minutes = max(0, int(delta.total_seconds() // 60))
        is_stale = age_hours >= stale_after_hours
        label = "Stale" if is_stale else "Fresh"
        if is_stale:
            reason = f"Last indexed {age_hours:.1f}h ago."

    freshness.update(
        {
            "last_indexed_at": last_indexed_at.isoformat() if last_indexed_at else None,
            "stale_after_hours": stale_after_hours,
            "age_hours": age_hours,
            "age_minutes": age_minutes,
            "is_stale": is_stale,
            "label": label,
            "reason": reason,
        }
    )
    health["freshness"] = freshness
    return health


def _parse_iso_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    normalized = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
