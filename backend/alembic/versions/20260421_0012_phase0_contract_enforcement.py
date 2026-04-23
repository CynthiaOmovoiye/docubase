"""Phase 0 strict evidence contract enforcement.

Adds:
- stricter backfill for chunk span and segment metadata
- DB-level lineage contract checks for file-backed and connector-segment chunks
- supporting indexes for snapshot/segment hydration lookups
"""

from __future__ import annotations

from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE chunks AS c
        SET
            start_line = COALESCE(
                c.start_line,
                NULLIF(c.metadata->>'start_line', '')::int,
                NULLIF(c.metadata->>'line_start', '')::int,
                1
            ),
            end_line = COALESCE(
                c.end_line,
                NULLIF(c.metadata->>'end_line', '')::int,
                NULLIF(c.metadata->>'line_end', '')::int,
                GREATEST(1, array_length(regexp_split_to_array(c.content, E'\\n'), 1))
            )
        WHERE c.lineage IN ('file_backed', 'connector_segment')
          AND (c.start_line IS NULL OR c.end_line IS NULL)
        """
    )

    op.execute(
        """
        UPDATE chunks AS c
        SET segment_id = CONCAT(
            c.source_ref,
            ':',
            c.start_line,
            '-',
            c.end_line,
            ':',
            c.chunk_type::text
        )
        WHERE c.lineage IN ('file_backed', 'connector_segment')
          AND c.source_ref IS NOT NULL
          AND c.segment_id IS NULL
          AND c.start_line IS NOT NULL
          AND c.end_line IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE chunks AS c
        SET snapshot_id = COALESCE(
            c.snapshot_id,
            s.snapshot_id,
            CASE
                WHEN s.snapshot_root_hash IS NOT NULL THEN CONCAT('hash:', s.snapshot_root_hash)
                ELSE NULL
            END
        )
        FROM sources AS s
        WHERE c.source_id = s.id
          AND c.lineage IN ('file_backed', 'connector_segment')
          AND c.snapshot_id IS NULL
        """
    )

    op.execute(
        """
        UPDATE chunks
        SET content_hash = encode(digest(content, 'sha256'), 'hex')
        WHERE lineage IN ('file_backed', 'connector_segment')
          AND content_hash IS NULL
        """
    )

    op.create_index(
        "ix_chunks_source_snapshot_segment",
        "chunks",
        ["source_id", "snapshot_id", "segment_id"],
        unique=False,
    )
    op.create_index(
        "ix_chunks_lineage_snapshot",
        "chunks",
        ["lineage", "snapshot_id"],
        unique=False,
    )

    op.create_check_constraint(
        "ck_chunks_file_backed_contract",
        "chunks",
        """
        lineage != 'file_backed'
        OR (
            source_ref IS NOT NULL
            AND snapshot_id IS NOT NULL
            AND segment_id IS NOT NULL
            AND content_hash IS NOT NULL
            AND start_line IS NOT NULL
            AND end_line IS NOT NULL
            AND start_line <= end_line
        )
        """,
    )
    op.create_check_constraint(
        "ck_chunks_connector_segment_contract",
        "chunks",
        """
        lineage != 'connector_segment'
        OR (
            source_ref IS NOT NULL
            AND snapshot_id IS NOT NULL
            AND segment_id IS NOT NULL
            AND content_hash IS NOT NULL
            AND start_line IS NOT NULL
            AND end_line IS NOT NULL
            AND start_line <= end_line
        )
        """,
    )


def downgrade() -> None:
    op.drop_constraint("ck_chunks_connector_segment_contract", "chunks", type_="check")
    op.drop_constraint("ck_chunks_file_backed_contract", "chunks", type_="check")
    op.drop_index("ix_chunks_lineage_snapshot", table_name="chunks")
    op.drop_index("ix_chunks_source_snapshot_segment", table_name="chunks")
