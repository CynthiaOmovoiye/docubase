"""Knowledge graph tables — graph_entities and graph_relationships.

Adds:
  - graph_entities table: named components extracted from the codebase
      (modules, technologies, services, concepts, data models)
    Each entity is embedded for similarity search and linked to a twin.

  - graph_relationships table: typed edges between entities
      (uses, depends_on, calls, contains, implements, extends, produces, consumes)

Both tables cascade-delete when their twin is deleted.
The embedding column uses pgvector's vector(1536) type (matches chunks.embedding).

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-18
"""

from __future__ import annotations

from alembic import op

# ── Revision identifiers ──────────────────────────────────────────────────────
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE graph_entities (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            twin_id         UUID NOT NULL REFERENCES twins(id) ON DELETE CASCADE,
            name            VARCHAR(512) NOT NULL,
            entity_type     VARCHAR(64)  NOT NULL,
            description     TEXT,
            source_refs     TEXT[]       DEFAULT '{}',
            embedding       vector(1536),
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX ix_graph_entities_twin_id ON graph_entities(twin_id)"
    )

    op.execute("""
        CREATE TABLE graph_relationships (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            twin_id             UUID NOT NULL REFERENCES twins(id) ON DELETE CASCADE,
            source_entity_id    UUID NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
            target_entity_id    UUID NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
            relationship_type   VARCHAR(64) NOT NULL,
            description         TEXT,
            weight              FLOAT NOT NULL DEFAULT 1.0,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX ix_graph_relationships_twin_id ON graph_relationships(twin_id)"
    )
    op.execute(
        "CREATE INDEX ix_graph_relationships_source ON graph_relationships(source_entity_id)"
    )
    op.execute(
        "CREATE INDEX ix_graph_relationships_target ON graph_relationships(target_entity_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS graph_relationships")
    op.execute("DROP TABLE IF EXISTS graph_entities")
