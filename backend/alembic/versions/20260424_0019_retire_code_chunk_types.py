"""Retire code-intelligence chunk types from document-only pipeline.

Deletes existing chunks of types that are no longer produced by the extractor:
  architecture_summary, module_description, feature_description,
  dependency_signal, code_snippet, implementation_fact

These were produced by the old code-repository intelligence pipeline. The system
now exclusively ingests document sources (PDFs, Drive docs, markdown) which only
produce `documentation` chunks. Retaining these rows would pollute retrieval
results and waste embedding space.

The enum values are NOT removed from the PostgreSQL enum type because:
  1. PostgreSQL requires a full type rename + recreation to remove enum values.
  2. The rows are gone so they can never appear in results.
  3. The Python enum still lists them as "retired" to keep DB round-trips safe.

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_RETIRED_TYPES = (
    "architecture_summary",
    "module_description",
    "feature_description",
    "dependency_signal",
    "code_snippet",
    "implementation_fact",
)


def upgrade() -> None:
    placeholders = ", ".join(f"'{t}'" for t in _RETIRED_TYPES)
    op.execute(f"DELETE FROM chunks WHERE chunk_type IN ({placeholders})")


def downgrade() -> None:
    # Rows are gone; no practical way to restore them.
    pass
