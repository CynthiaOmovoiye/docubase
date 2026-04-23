"""Add embedding profile columns and processing source status.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE t.typname = 'source_status_enum'
                  AND e.enumlabel = 'processing'
            ) THEN
                ALTER TYPE source_status_enum ADD VALUE 'processing';
            END IF;
        END $$;
        """
    )

    op.add_column("sources", sa.Column("embedding_provider", sa.String(length=32), nullable=True))
    op.add_column("sources", sa.Column("embedding_model", sa.String(length=120), nullable=True))
    op.add_column("sources", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))

    op.add_column("graph_entities", sa.Column("embedding_provider", sa.String(length=32), nullable=True))
    op.add_column("graph_entities", sa.Column("embedding_model", sa.String(length=120), nullable=True))
    op.add_column("graph_entities", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("graph_entities", "embedding_dimensions")
    op.drop_column("graph_entities", "embedding_model")
    op.drop_column("graph_entities", "embedding_provider")

    op.drop_column("sources", "embedding_dimensions")
    op.drop_column("sources", "embedding_model")
    op.drop_column("sources", "embedding_provider")

    op.execute("ALTER TYPE source_status_enum RENAME TO source_status_enum_old")
    op.execute(
        """
        CREATE TYPE source_status_enum AS ENUM (
            'pending',
            'ingesting',
            'ready',
            'failed',
            'needs_resync'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE sources
        ALTER COLUMN status TYPE source_status_enum
        USING (
            CASE
                WHEN status::text = 'processing' THEN 'ingesting'
                ELSE status::text
            END
        )::source_status_enum
        """
    )
    op.execute("DROP TYPE source_status_enum_old")
