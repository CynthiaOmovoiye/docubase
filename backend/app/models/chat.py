import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.twin import Twin


class MessageRole(enum.StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ChatSession(Base, UUIDMixin, TimestampMixin):
    """
    A conversation session.

    Can be anchored to a specific Twin (single-twin chat)
    or to a Workspace (cross-twin chat where routing happens automatically).
    """

    __tablename__ = "chat_sessions"

    # A session belongs to a workspace. Twin is optional (null = workspace-level chat).
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    doctwin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("twins.id", ondelete="SET NULL"), nullable=True
    )

    # Anonymous sessions allowed (public share pages). user_id is null for those.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Opaque public visitor key (no PII). When set, the visitor can list/resume sessions
    # by presenting the same id; ephemeral public chats leave this null.
    visitor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Relationships
    twin: Mapped["Twin | None"] = relationship("Twin", back_populates="chat_sessions")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan",
        order_by="Message.created_at"
    )


class Message(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role_enum"), nullable=False
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Which twin/source actually answered (for workspace-level routing transparency)
    routed_doctwin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Chunk IDs used as context for this response (for auditability)
    context_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # Relationships
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
