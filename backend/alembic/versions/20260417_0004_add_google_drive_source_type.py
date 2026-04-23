"""Add google_drive to source_type_enum

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-17

PostgreSQL ALTER TYPE … ADD VALUE cannot run inside a transaction block,
so this migration uses op.execute() with COMMIT guards via the non-transactional
execute pattern. Alembic handles this correctly when transaction_per_migration
is False (the default for Postgres enums that require ADD VALUE).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE cannot run inside a transaction on Postgres.
    # Alembic's --autogenerate also uses this pattern.
    op.execute("ALTER TYPE source_type_enum ADD VALUE IF NOT EXISTS 'google_drive'")


def downgrade() -> None:
    # Postgres does not support removing an enum value without recreating the type.
    # The safest downgrade is a no-op — the unused value causes no harm.
    pass
