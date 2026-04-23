"""Phase 1 deterministic relationships, git activity index, and embedding cache."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


indexed_relationship_type_enum = postgresql.ENUM(
    "contains",
    "depends_on",
    "uses",
    "produces",
    "extends",
    "implements",
    name="indexed_relationship_type_enum",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'indexed_relationship_type_enum') THEN
                CREATE TYPE indexed_relationship_type_enum AS ENUM (
                    'contains', 'depends_on', 'uses', 'produces', 'extends', 'implements'
                );
            END IF;
        END$$;
        """
    )

    op.create_table(
        "indexed_relationships",
        sa.Column("indexed_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("twin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", sa.String(length=200), nullable=False),
        sa.Column("source_ref", sa.String(length=512), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("target_ref", sa.String(length=512), nullable=False),
        sa.Column("target_kind", sa.String(length=64), nullable=False),
        sa.Column("relationship_type", indexed_relationship_type_enum, nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["indexed_file_id"], ["indexed_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["twin_id"], ["twins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "indexed_file_id",
            "source_ref",
            "target_ref",
            "relationship_type",
            name="uq_indexed_relationships_edge",
        ),
    )
    op.create_index("ix_indexed_relationships_indexed_file_id", "indexed_relationships", ["indexed_file_id"], unique=False)
    op.create_index("ix_indexed_relationships_source", "indexed_relationships", ["source_id", "relationship_type"], unique=False)
    op.create_index("ix_indexed_relationships_source_id", "indexed_relationships", ["source_id"], unique=False)
    op.create_index("ix_indexed_relationships_target", "indexed_relationships", ["source_id", "target_ref"], unique=False)
    op.create_index("ix_indexed_relationships_twin", "indexed_relationships", ["twin_id", "relationship_type"], unique=False)
    op.create_index("ix_indexed_relationships_twin_id", "indexed_relationships", ["twin_id"], unique=False)

    op.create_table(
        "git_activities",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("twin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", sa.String(length=200), nullable=False),
        sa.Column("activity_type", sa.String(length=32), nullable=False),
        sa.Column("activity_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.String(length=64), nullable=True),
        sa.Column("branch_name", sa.String(length=255), nullable=True),
        sa.Column("path_refs", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("labels", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("additions", sa.Integer(), nullable=False),
        sa.Column("deletions", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["twin_id"], ["twins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "snapshot_id",
            "activity_type",
            "activity_key",
            name="uq_git_activities_source_snapshot_key",
        ),
    )
    op.create_index("ix_git_activities_snapshot", "git_activities", ["snapshot_id"], unique=False)
    op.create_index("ix_git_activities_source_id", "git_activities", ["source_id"], unique=False)
    op.create_index("ix_git_activities_source_time", "git_activities", ["source_id", "occurred_at"], unique=False)
    op.create_index("ix_git_activities_twin_id", "git_activities", ["twin_id"], unique=False)
    op.create_index("ix_git_activities_twin_type", "git_activities", ["twin_id", "activity_type"], unique=False)

    op.create_table(
        "embedding_cache_entries",
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "text_hash",
            "provider",
            "model",
            "dimensions",
            "task",
            name="uq_embedding_cache_profile_text",
        ),
    )
    op.create_index("ix_embedding_cache_profile", "embedding_cache_entries", ["provider", "model", "dimensions", "task"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_embedding_cache_profile", table_name="embedding_cache_entries")
    op.drop_table("embedding_cache_entries")

    op.drop_index("ix_git_activities_twin_type", table_name="git_activities")
    op.drop_index("ix_git_activities_twin_id", table_name="git_activities")
    op.drop_index("ix_git_activities_source_time", table_name="git_activities")
    op.drop_index("ix_git_activities_source_id", table_name="git_activities")
    op.drop_index("ix_git_activities_snapshot", table_name="git_activities")
    op.drop_table("git_activities")

    op.drop_index("ix_indexed_relationships_twin_id", table_name="indexed_relationships")
    op.drop_index("ix_indexed_relationships_twin", table_name="indexed_relationships")
    op.drop_index("ix_indexed_relationships_target", table_name="indexed_relationships")
    op.drop_index("ix_indexed_relationships_source_id", table_name="indexed_relationships")
    op.drop_index("ix_indexed_relationships_source", table_name="indexed_relationships")
    op.drop_index("ix_indexed_relationships_indexed_file_id", table_name="indexed_relationships")
    op.drop_table("indexed_relationships")

    op.execute("DROP TYPE IF EXISTS indexed_relationship_type_enum")
