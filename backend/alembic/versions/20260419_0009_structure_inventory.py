"""Add structure_index JSONB column to sources table.

Stores a deterministic per-source file-tree inventory populated at sync time.
Used for structure-aware workspace routing and guaranteed-ref retrieval.

Schema stored in the column:
{
  "schema_version": 1,
  "meaningful_dirs": {
    "week3": ["week3/README.md", ...],
    "app/api": ["app/api/routes.py", ...],
    "_root": ["README.md", ...]
  },
  "total_files": N,
  "generated_at": "ISO timestamp",
  "is_partial": false
}

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("structure_index", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sources", "structure_index")
