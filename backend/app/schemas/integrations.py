"""
Pydantic schemas for the integrations API.

Security note: ConnectedAccountResponse explicitly excludes all token fields.
Tokens are never returned to clients — not even in encrypted form.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConnectedAccountResponse(BaseModel):
    """
    Safe representation of a connected OAuth account.

    Tokens are never included — this is intentional and non-negotiable.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    provider_username: str | None
    scopes: str | None
    is_active: bool
    created_at: datetime


class OAuthInitResponse(BaseModel):
    """Response from GET /integrations/{provider}/connect."""

    auth_url: str


class DriveFileItem(BaseModel):
    """A single file or folder returned from the Google Drive browser endpoint."""

    id: str
    name: str
    mime_type: str
    modified_time: str | None = None
    is_folder: bool
