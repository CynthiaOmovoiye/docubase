"""
Workspace schemas.
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-")


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("slug", mode="before")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        if v is None:
            return v
        slug = _slugify(v)
        if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", slug):
            raise ValueError(
                "Slug must contain only lowercase letters, numbers, and hyphens, "
                "and must start and end with a letter or number"
            )
        return slug


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    # owner_id intentionally omitted — the authenticated caller already knows
    # their own ID via /users/me and exposing it in API responses is unnecessary.
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
