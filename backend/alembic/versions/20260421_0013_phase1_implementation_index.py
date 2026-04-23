"""Phase 1 implementation index foundation.

Adds deterministic file and symbol index tables for the first implementation
index slice.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


indexed_file_kind_enum = postgresql.ENUM(
    "code",
    "documentation",
    "dependency_manifest",
    "config",
    "data",
    "unknown",
    name="indexed_file_kind_enum",
    create_type=False,
)

indexed_symbol_kind_enum = postgresql.ENUM(
    "function",
    "async_function",
    "class",
    "method",
    "async_method",
    "route",
    "data_model",
    "export",
    "constant",
    name="indexed_symbol_kind_enum",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'indexed_file_kind_enum') THEN
                CREATE TYPE indexed_file_kind_enum AS ENUM (
                    'code', 'documentation', 'dependency_manifest', 'config', 'data', 'unknown'
                );
            END IF;
        END$$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'indexed_symbol_kind_enum') THEN
                CREATE TYPE indexed_symbol_kind_enum AS ENUM (
                    'function', 'async_function', 'class', 'method', 'async_method',
                    'route', 'data_model', 'export', 'constant'
                );
            END IF;
        END$$;
        """
    )

    op.create_table(
        "indexed_files",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doctwin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", sa.String(length=200), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("file_kind", indexed_file_kind_enum, nullable=False),
        sa.Column("framework_role", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doctwin_id"], ["twins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "snapshot_id", "path", name="uq_indexed_files_source_snapshot_path"),
    )
    op.create_index("ix_indexed_files_source_hash", "indexed_files", ["source_id", "content_hash"], unique=False)
    op.create_index("ix_indexed_files_source_id", "indexed_files", ["source_id"], unique=False)
    op.create_index("ix_indexed_files_source_path", "indexed_files", ["source_id", "path"], unique=False)
    op.create_index("ix_indexed_files_doctwin_id", "indexed_files", ["doctwin_id"], unique=False)
    op.create_index("ix_indexed_files_doctwin_snapshot", "indexed_files", ["doctwin_id", "snapshot_id"], unique=False)

    op.create_table(
        "indexed_symbols",
        sa.Column("indexed_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doctwin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", sa.String(length=200), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("symbol_name", sa.String(length=255), nullable=False),
        sa.Column("qualified_name", sa.String(length=512), nullable=False),
        sa.Column("symbol_kind", indexed_symbol_kind_enum, nullable=False),
        sa.Column("parent_symbol", sa.String(length=512), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["indexed_file_id"], ["indexed_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doctwin_id"], ["twins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "indexed_file_id",
            "qualified_name",
            "symbol_kind",
            "start_line",
            "end_line",
            name="uq_indexed_symbols_file_symbol_span",
        ),
    )
    op.create_index("ix_indexed_symbols_indexed_file_id", "indexed_symbols", ["indexed_file_id"], unique=False)
    op.create_index("ix_indexed_symbols_source_id", "indexed_symbols", ["source_id"], unique=False)
    op.create_index("ix_indexed_symbols_source_path", "indexed_symbols", ["source_id", "path"], unique=False)
    op.create_index("ix_indexed_symbols_doctwin_id", "indexed_symbols", ["doctwin_id"], unique=False)
    op.create_index("ix_indexed_symbols_doctwin_kind", "indexed_symbols", ["doctwin_id", "symbol_kind"], unique=False)
    op.create_index("ix_indexed_symbols_doctwin_name", "indexed_symbols", ["doctwin_id", "symbol_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_indexed_symbols_doctwin_name", table_name="indexed_symbols")
    op.drop_index("ix_indexed_symbols_doctwin_kind", table_name="indexed_symbols")
    op.drop_index("ix_indexed_symbols_doctwin_id", table_name="indexed_symbols")
    op.drop_index("ix_indexed_symbols_source_path", table_name="indexed_symbols")
    op.drop_index("ix_indexed_symbols_source_id", table_name="indexed_symbols")
    op.drop_index("ix_indexed_symbols_indexed_file_id", table_name="indexed_symbols")
    op.drop_table("indexed_symbols")

    op.drop_index("ix_indexed_files_doctwin_snapshot", table_name="indexed_files")
    op.drop_index("ix_indexed_files_doctwin_id", table_name="indexed_files")
    op.drop_index("ix_indexed_files_source_path", table_name="indexed_files")
    op.drop_index("ix_indexed_files_source_id", table_name="indexed_files")
    op.drop_index("ix_indexed_files_source_hash", table_name="indexed_files")
    op.drop_table("indexed_files")

    op.execute("DROP TYPE IF EXISTS indexed_symbol_kind_enum")
    op.execute("DROP TYPE IF EXISTS indexed_file_kind_enum")
