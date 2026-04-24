"""Add visitor_id for resumable public chat sessions.

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("visitor_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_chat_sessions_visitor_id",
        "chat_sessions",
        ["visitor_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_visitor_id", table_name="chat_sessions")
    op.drop_column("chat_sessions", "visitor_id")
