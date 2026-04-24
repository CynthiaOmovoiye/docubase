"""
Chat schemas.

Request/response models for chat sessions and messages.
"""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.chat import MessageRole


class CreateSessionResponse(BaseModel):
    session_id: uuid.UUID
    workspace_id: uuid.UUID
    doctwin_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_session(cls, session: object) -> "CreateSessionResponse":
        return cls(
            session_id=session.id,  # type: ignore[attr-defined]
            workspace_id=session.workspace_id,  # type: ignore[attr-defined]
            doctwin_id=session.doctwin_id,  # type: ignore[attr-defined]
            created_at=session.created_at,  # type: ignore[attr-defined]
        )


_VISITOR_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")


class CreatePublicSessionRequest(BaseModel):
    """Optional body for anonymous public share sessions."""

    visitor_id: str | None = Field(
        default=None,
        description=(
            "Opaque random id (no personal data). When set, new sessions are tied to this id "
            "so they can be listed and resumed later. Use 8–64 URL-safe characters."
        ),
    )

    @field_validator("visitor_id", mode="before")
    @classmethod
    def strip_visitor(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    @field_validator("visitor_id")
    @classmethod
    def validate_visitor(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _VISITOR_ID_RE.match(v):
            raise ValueError("visitor_id must be 8–64 characters: letters, digits, hyphen, underscore")
        return v


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    include_answer_diagnostics: bool = Field(
        default=False,
        description=(
            "When true, the response includes a structured answer_diagnostics payload "
            "(authority level, degraded reasons, per-stage signals) for owners and debugging."
        ),
    )


class MessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: MessageRole
    content: str
    routed_doctwin_id: uuid.UUID | None
    created_at: datetime
    answer_diagnostics: dict | None = Field(
        default=None,
        description="Phase 0 — present only when include_answer_diagnostics was true on the request.",
    )

    model_config = {"from_attributes": True}

    @classmethod
    def from_message(
        cls,
        message: object,
        *,
        answer_diagnostics: dict | None = None,
    ) -> "MessageResponse":
        return cls(
            id=message.id,  # type: ignore[attr-defined]
            session_id=message.session_id,  # type: ignore[attr-defined]
            role=message.role,  # type: ignore[attr-defined]
            content=message.content,  # type: ignore[attr-defined]
            routed_doctwin_id=message.routed_doctwin_id,  # type: ignore[attr-defined]
            created_at=message.created_at,  # type: ignore[attr-defined]
            answer_diagnostics=answer_diagnostics,
        )


class HistoryResponse(BaseModel):
    session_id: uuid.UUID
    messages: list[MessageResponse]


class ChatSessionSummary(BaseModel):
    """Lightweight session summary for the session history list."""
    session_id: uuid.UUID
    created_at: datetime
    last_message_at: datetime | None
    message_count: int
    preview: str | None  # first user message, truncated to 120 chars
