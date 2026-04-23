"""Phase 4 memory artifacts and workspace synthesis.

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE chunk_type_enum ADD VALUE IF NOT EXISTS 'feature_summary'")
    op.execute("ALTER TYPE chunk_type_enum ADD VALUE IF NOT EXISTS 'auth_flow'")
    op.execute("ALTER TYPE chunk_type_enum ADD VALUE IF NOT EXISTS 'onboarding_map'")

    artifact_type_enum = postgresql.ENUM(
        "workspace_synthesis",
        name="workspace_memory_artifact_type_enum",
        create_type=False,
    )
    artifact_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "workspace_memory_artifacts",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", artifact_type_enum, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "artifact_type",
            name="uq_workspace_memory_artifacts_workspace_type",
        ),
    )
    op.create_index(
        "ix_workspace_memory_artifacts_workspace_id",
        "workspace_memory_artifacts",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_memory_artifacts_workspace_status",
        "workspace_memory_artifacts",
        ["workspace_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_memory_artifacts_workspace_status", table_name="workspace_memory_artifacts")
    op.drop_index("ix_workspace_memory_artifacts_workspace_id", table_name="workspace_memory_artifacts")
    op.drop_table("workspace_memory_artifacts")
    artifact_type_enum = postgresql.ENUM(
        "workspace_synthesis",
        name="workspace_memory_artifact_type_enum",
        create_type=False,
    )
    artifact_type_enum.drop(op.get_bind(), checkfirst=True)
