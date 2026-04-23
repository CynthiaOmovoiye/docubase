"""Fix graph_entities.embedding dimension to match configured EMBEDDING_DIMENSIONS.

Migration 0007 hardcoded vector(1536). This migration drops and re-adds the
column using the dimension from the environment variable, defaulting to 1536
so the migration is safe even without EMBEDDING_DIMENSIONS set.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-18
"""

from __future__ import annotations

import os

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _embed_dim() -> int:
    return int(os.environ.get("EMBEDDING_DIMENSIONS", "1536"))


def upgrade() -> None:
    dim = _embed_dim()
    op.execute("ALTER TABLE graph_entities DROP COLUMN IF EXISTS embedding")
    op.execute(f"ALTER TABLE graph_entities ADD COLUMN embedding vector({dim})")


def downgrade() -> None:
    op.execute("ALTER TABLE graph_entities DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE graph_entities ADD COLUMN embedding vector(1536)")
