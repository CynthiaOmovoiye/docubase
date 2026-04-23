"""
ConnectedAccount ORM model.

Represents an OAuth-linked provider account (GitHub, GitLab, Google Drive)
belonging to a user. Encrypted tokens are stored here — never plaintext.

Security:
- access_token_encrypted and refresh_token_encrypted are Fernet-encrypted
  before write and decrypted on demand via app.core.crypto.
- The unique constraint on (user_id, provider, provider_account_id) prevents
  a user from inadvertently linking the same provider account twice.
- is_active=False is used for soft-disconnect so we keep an audit trail
  without leaving valid tokens accessible.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.source import Source


class ConnectedAccount(Base, UUIDMixin, TimestampMixin):
    """
    An OAuth-connected provider account owned by a user.

    One user may have multiple connected accounts (e.g., two GitHub orgs),
    but the (user_id, provider, provider_account_id) triple must be unique.
    """

    __tablename__ = "connected_accounts"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "provider_account_id",
            name="uq_connected_accounts_user_provider_account",
        ),
    )

    # Owner
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Provider identity
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_account_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_username: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Encrypted tokens — never stored or logged in plaintext
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Token lifecycle — nullable because GitHub classic tokens don't expire
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Space-separated granted scopes for audit / UI display
    scopes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Soft-deactivation on disconnect
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="connected_accounts")
    sources: Mapped[list["Source"]] = relationship(
        "Source", back_populates="connected_account"
    )

    def __repr__(self) -> str:
        return (
            f"<ConnectedAccount id={self.id} provider={self.provider} "
            f"account={self.provider_account_id} active={self.is_active}>"
        )
