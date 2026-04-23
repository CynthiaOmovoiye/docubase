"""Add connected_accounts table and integration columns on sources

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── connected_accounts ────────────────────────────────────────────────────
    op.create_table(
        "connected_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_account_id", sa.String(200), nullable=False),
        sa.Column("provider_username", sa.String(200), nullable=True),
        sa.Column("access_token_encrypted", sa.Text, nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text, nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.String(500), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "provider_account_id",
            name="uq_connected_accounts_user_provider_account",
        ),
    )
    op.create_index(
        "ix_connected_accounts_user_id", "connected_accounts", ["user_id"]
    )

    # ── sources — new integration columns ─────────────────────────────────────
    op.add_column(
        "sources",
        sa.Column(
            "connected_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("connected_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sources_connected_account_id",
        "sources",
        ["connected_account_id"],
    )
    op.add_column(
        "sources",
        sa.Column("last_commit_sha", sa.String(40), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("last_page_token", sa.Text, nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("webhook_id", sa.String(200), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("webhook_secret", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    # Remove new source columns first (FK to connected_accounts)
    op.drop_index("ix_sources_connected_account_id", table_name="sources")
    op.drop_column("sources", "connected_account_id")
    op.drop_column("sources", "last_commit_sha")
    op.drop_column("sources", "last_page_token")
    op.drop_column("sources", "webhook_id")
    op.drop_column("sources", "webhook_secret")

    # Drop connected_accounts table
    op.drop_index("ix_connected_accounts_user_id", table_name="connected_accounts")
    op.drop_table("connected_accounts")
