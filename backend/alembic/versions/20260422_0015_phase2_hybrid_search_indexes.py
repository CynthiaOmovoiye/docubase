"""Phase 2 hybrid lexical search indexes.

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-22
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chunks_lexical_fts
        ON chunks
        USING gin (
            (
                setweight(to_tsvector('simple', COALESCE(source_ref, '')), 'A') ||
                setweight(to_tsvector('simple', COALESCE(content, '')), 'B')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_indexed_files_lexical_fts
        ON indexed_files
        USING gin (
            (
                setweight(to_tsvector('simple', COALESCE(path, '')), 'A') ||
                setweight(to_tsvector('simple', COALESCE(framework_role, '')), 'B')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_indexed_symbols_lexical_fts
        ON indexed_symbols
        USING gin (
            (
                setweight(to_tsvector('simple', COALESCE(symbol_name, '')), 'A') ||
                setweight(to_tsvector('simple', COALESCE(qualified_name, '')), 'A') ||
                setweight(to_tsvector('simple', COALESCE(signature, '')), 'B')
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_indexed_symbols_lexical_fts")
    op.execute("DROP INDEX IF EXISTS ix_indexed_files_lexical_fts")
    op.execute("DROP INDEX IF EXISTS ix_chunks_lexical_fts")
