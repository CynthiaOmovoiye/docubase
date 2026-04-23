"""Change chunks.embedding from vector(1536) to vector(1024)

This migration resizes the pgvector column to match Jina AI's
jina-embeddings-v3 output (1024 dimensions).

OpenAI text-embedding-3-small produced 1536-dim vectors.
Jina jina-embeddings-v3 produces up to 1024-dim vectors.

IMPORTANT: After running this migration ALL existing chunks must be
re-ingested — the old 1536-dim vectors are truncated/invalid and will
never produce correct similarity scores against new 1024-dim query vectors.
Re-sync every source via the UI (Re-sync button) or:
    POST /api/v1/sources/{source_id}/sync

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-17
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the ivfflat index — it's tied to the old dimension count.
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding")

    # NULL out all existing embeddings before resizing the column.
    # pgvector cannot cast vector(1536) → vector(1024) (different dimensions).
    # The old vectors were produced by LocalStubEmbedder (random hash-based,
    # no semantic meaning), so clearing them loses nothing of value.
    # All sources must be re-synced after this migration to get real embeddings.
    op.execute("UPDATE chunks SET embedding = NULL")

    # Now resize safely — all rows have NULL embedding so no cast is needed.
    op.execute(
        "ALTER TABLE chunks "
        "ALTER COLUMN embedding TYPE vector(1024) "
        "USING embedding::vector(1024)"
    )

    # Recreate the ivfflat index for the new dimension.
    # lists=100 is appropriate for up to ~1M vectors; tune upward as data grows.
    op.execute(
        "CREATE INDEX ix_chunks_embedding "
        "ON chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding")
    op.execute(
        "ALTER TABLE chunks "
        "ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
    op.execute(
        "CREATE INDEX ix_chunks_embedding "
        "ON chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
