"""Add implementation_fact to chunk_type_enum.

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE chunk_type_enum ADD VALUE IF NOT EXISTS 'implementation_fact'")


def downgrade() -> None:
    # PostgreSQL cannot drop individual enum values safely; no-op.
    pass
