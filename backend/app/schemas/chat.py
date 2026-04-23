"""
Chat schemas.

Request/response models for chat sessions and messages.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.chat import MessageRole


class CreateSessionResponse(BaseModel):
    session_id: uuid.UUID
    workspace_id: uuid.UUID
    twin_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_session(cls, session: object) -> "CreateSessionResponse":
        return cls(
            session_id=session.id,  # type: ignore[attr-defined]
            workspace_id=session.workspace_id,  # type: ignore[attr-defined]
            twin_id=session.twin_id,  # type: ignore[attr-defined]
            created_at=session.created_at,  # type: ignore[attr-defined]
        )


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
    routed_twin_id: uuid.UUID | None
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
            routed_twin_id=message.routed_twin_id,  # type: ignore[attr-defined]
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
