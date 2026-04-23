"""Initial schema — all core tables

Revision ID: 0001
Revises:
Create Date: 2026-04-15 00:01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

# revision identifiers
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String, nullable=False),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── workspaces ─────────────────────────────────────────────────────────────
    op.create_table(
        "workspaces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=True)

    # ── twins ──────────────────────────────────────────────────────────────────
    op.create_table(
        "twins",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_twins_slug", "twins", ["slug"])
    op.create_index("ix_twins_workspace_slug", "twins", ["workspace_id", "slug"], unique=True)

    # ── twin_configs ───────────────────────────────────────────────────────────
    op.create_table(
        "twin_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("twin_id", UUID(as_uuid=True), sa.ForeignKey("twins.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("allow_code_snippets", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("display_name", sa.String(120), nullable=True),
        sa.Column("accent_color", sa.String(7), nullable=True),
        sa.Column("custom_context", sa.Text, nullable=True),
        sa.Column("extra", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── sources (PostgreSQL ENUM types are emitted once by create_table) ─────
    op.create_table(
        "sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "source_type",
            ENUM(
                "github_repo",
                "gitlab_repo",
                "pdf",
                "markdown",
                "url",
                "manual",
                name="source_type_enum",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            ENUM(
                "pending",
                "ingesting",
                "ready",
                "failed",
                "needs_resync",
                name="source_status_enum",
                create_type=True,
            ),
            nullable=False,
            server_default=sa.text("'pending'::source_status_enum"),
        ),
        sa.Column("twin_id", UUID(as_uuid=True), sa.ForeignKey("twins.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_config", JSONB, nullable=False, server_default="{}"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── chunks ─────────────────────────────────────────────────────────────────
    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "chunk_type",
            ENUM(
                "architecture_summary",
                "module_description",
                "feature_description",
                "dependency_signal",
                "documentation",
                "code_snippet",
                "career_summary",
                "experience_entry",
                "project_description",
                "skill_profile",
                "manual_note",
                name="chunk_type_enum",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", sa.Text, nullable=True),  # Stored as vector(1536); type overridden below
        sa.Column("source_ref", sa.String(500), nullable=True),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Override the embedding column to use pgvector type
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536)")
    op.execute("CREATE INDEX ix_chunks_source_id ON chunks (source_id)")
    op.execute("CREATE INDEX ix_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")

    # ── chat_sessions ──────────────────────────────────────────────────────────
    op.create_table(
        "chat_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("twin_id", UUID(as_uuid=True), sa.ForeignKey("twins.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── messages ───────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "role",
            ENUM("user", "assistant", "system", name="message_role_enum", create_type=True),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("routed_twin_id", UUID(as_uuid=True), nullable=True),
        sa.Column("context_chunk_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── share_surfaces ─────────────────────────────────────────────────────────
    op.create_table(
        "share_surfaces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "surface_type",
            ENUM(
                "twin_page",
                "workspace_page",
                "embed",
                name="share_surface_type_enum",
                create_type=True,
            ),
            nullable=False,
        ),
        sa.Column("public_slug", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("twin_id", UUID(as_uuid=True), sa.ForeignKey("twins.id", ondelete="CASCADE"), nullable=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True),
        sa.Column("embed_config", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_share_surfaces_public_slug", "share_surfaces", ["public_slug"], unique=True)


def downgrade() -> None:
    op.drop_table("share_surfaces")
    op.drop_table("messages")
    op.drop_table("chat_sessions")
    op.drop_table("chunks")
    op.drop_table("sources")
    op.drop_table("twin_configs")
    op.drop_table("twins")
    op.drop_table("workspaces")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS share_surface_type_enum")
    op.execute("DROP TYPE IF EXISTS message_role_enum")
    op.execute("DROP TYPE IF EXISTS chunk_type_enum")
    op.execute("DROP TYPE IF EXISTS source_status_enum")
    op.execute("DROP TYPE IF EXISTS source_type_enum")
    op.execute("DROP EXTENSION IF EXISTS vector")
