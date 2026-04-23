"""Engineering memory layer — new chunk types and TwinConfig memory brief columns.

Adds:
  - Five new values to chunk_type_enum:
      change_entry, risk_note, decision_record, hotspot, memory_brief
    These are LLM-generated chunk types produced by the memory extraction job.
    Stored with source_ref = "__memory__/{twin_id}" to distinguish them from
    file-derived chunks and enable targeted deletion on re-extraction.

  - Three new columns on twin_configs:
      memory_brief          TEXT       — the generated Memory Brief markdown
      memory_brief_generated_at  TIMESTAMPTZ — when the brief was last generated
      memory_brief_status   VARCHAR(20) — lifecycle: pending|generating|ready|failed

NOTE: PostgreSQL ENUM values cannot be dropped without full type recreation.
The downgrade() function only reverses the twin_configs columns. If a full
rollback is required, all rows using these chunk types must be deleted first,
then the enum type must be recreated manually.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ──────────────────────────────────────────────────────

revision: str = "0006"
down_revision: str = "0005"
branch_labels = None
depends_on = None


# ── Upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:
    # ── 1. New chunk type enum values ─────────────────────────────────────────
    # Each ALTER TYPE must be a separate statement.
    # IF NOT EXISTS prevents failure on repeated migration runs.
    op.execute("ALTER TYPE chunk_type_enum ADD VALUE IF NOT EXISTS 'change_entry'")
    op.execute("ALTER TYPE chunk_type_enum ADD VALUE IF NOT EXISTS 'risk_note'")
    op.execute("ALTER TYPE chunk_type_enum ADD VALUE IF NOT EXISTS 'decision_record'")
    op.execute("ALTER TYPE chunk_type_enum ADD VALUE IF NOT EXISTS 'hotspot'")
    op.execute("ALTER TYPE chunk_type_enum ADD VALUE IF NOT EXISTS 'memory_brief'")

    # ── 2. Memory Brief columns on twin_configs ───────────────────────────────
    op.add_column(
        "twin_configs",
        sa.Column("memory_brief", sa.Text, nullable=True),
    )
    op.add_column(
        "twin_configs",
        sa.Column(
            "memory_brief_generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "twin_configs",
        sa.Column("memory_brief_status", sa.String(20), nullable=True),
    )


# ── Downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    # Remove the three twin_configs columns.
    op.drop_column("twin_configs", "memory_brief_status")
    op.drop_column("twin_configs", "memory_brief_generated_at")
    op.drop_column("twin_configs", "memory_brief")

    # NOTE: The five chunk_type_enum values (change_entry, risk_note,
    # decision_record, hotspot, memory_brief) are NOT removed here.
    # PostgreSQL does not support dropping individual enum values without
    # recreating the entire type. To fully reverse this migration:
    #   1. DELETE FROM chunks WHERE chunk_type IN ('change_entry', 'risk_note',
    #      'decision_record', 'hotspot', 'memory_brief');
    #   2. ALTER TYPE chunk_type_enum RENAME TO chunk_type_enum_old;
    #   3. CREATE TYPE chunk_type_enum AS ENUM (<original values only>);
    #   4. ALTER TABLE chunks ALTER COLUMN chunk_type TYPE chunk_type_enum
    #      USING chunk_type::text::chunk_type_enum;
    #   5. DROP TYPE chunk_type_enum_old;
