"""Phase 0 repo-intelligence trust layer.

Adds:
- chunk lineage and strict evidence contract columns
- source snapshot identity and index health fields
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    chunk_lineage_enum = postgresql.ENUM(
        "file_backed",
        "connector_segment",
        "synthetic_profile",
        "memory_derived",
        name="chunk_lineage_enum",
        create_type=False,
    )
    source_index_mode_enum = postgresql.ENUM(
        "legacy",
        "strict",
        name="source_index_mode_enum",
        create_type=False,
    )

    chunk_lineage_enum.create(op.get_bind(), checkfirst=True)
    source_index_mode_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "sources",
        sa.Column("snapshot_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("snapshot_root_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column(
            "index_mode",
            source_index_mode_enum,
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "index_health",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.add_column(
        "chunks",
        sa.Column(
            "lineage",
            chunk_lineage_enum,
            nullable=False,
            server_default="file_backed",
        ),
    )
    op.add_column(
        "chunks",
        sa.Column("snapshot_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("segment_id", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("start_line", sa.Integer(), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("end_line", sa.Integer(), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )

    op.execute(
        """
        UPDATE chunks
        SET lineage = CASE
            WHEN source_ref LIKE '__memory__/%' THEN 'memory_derived'::chunk_lineage_enum
            WHEN chunk_type::text IN ('change_entry', 'risk_note', 'decision_record', 'hotspot', 'memory_brief')
                THEN 'memory_derived'::chunk_lineage_enum
            WHEN chunk_type::text IN ('career_summary', 'experience_entry', 'project_description', 'skill_profile', 'manual_note')
                THEN 'synthetic_profile'::chunk_lineage_enum
            ELSE 'file_backed'::chunk_lineage_enum
        END
        """
    )

    op.execute(
        """
        UPDATE sources
        SET snapshot_id = COALESCE(snapshot_id, last_commit_sha, last_page_token)
        WHERE snapshot_id IS NULL
        """
    )

    op.execute(
        """
        UPDATE chunks AS c
        SET
            snapshot_id = COALESCE(c.snapshot_id, s.snapshot_id),
            segment_id = COALESCE(c.segment_id, c.source_ref),
            start_line = COALESCE(
                c.start_line,
                NULLIF(c.metadata->>'start_line', '')::int,
                NULLIF(c.metadata->>'line_start', '')::int
            ),
            end_line = COALESCE(
                c.end_line,
                NULLIF(c.metadata->>'end_line', '')::int,
                NULLIF(c.metadata->>'line_end', '')::int
            ),
            content_hash = COALESCE(c.content_hash, encode(digest(c.content, 'sha256'), 'hex'))
        FROM sources AS s
        WHERE c.source_id = s.id
        """
    )

    op.alter_column("sources", "index_mode", server_default=None)
    op.alter_column("sources", "index_health", server_default=None)
    op.alter_column("chunks", "lineage", server_default=None)


def downgrade() -> None:
    op.drop_column("chunks", "content_hash")
    op.drop_column("chunks", "end_line")
    op.drop_column("chunks", "start_line")
    op.drop_column("chunks", "segment_id")
    op.drop_column("chunks", "snapshot_id")
    op.drop_column("chunks", "lineage")

    op.drop_column("sources", "index_health")
    op.drop_column("sources", "index_mode")
    op.drop_column("sources", "snapshot_root_hash")
    op.drop_column("sources", "snapshot_id")

    chunk_lineage_enum = postgresql.ENUM(name="chunk_lineage_enum")
    source_index_mode_enum = postgresql.ENUM(name="source_index_mode_enum")
    chunk_lineage_enum.drop(op.get_bind(), checkfirst=True)
    source_index_mode_enum.drop(op.get_bind(), checkfirst=True)
