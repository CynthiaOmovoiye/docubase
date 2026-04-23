"""
Knowledge graph service — build, query, and traverse the entity graph for a twin.

Public API:
  rebuild_graph()            — idempotent: delete + re-insert entities and relationships
  find_entities_for_query()  — find entities matching a query via embedding similarity
  traverse_graph()           — BFS from seed entities, returning all visited nodes + edges
  format_graph_context()     — render traversal results as a context string for LLM prompts
  get_graph_summary()        — full graph summary for memory brief generation

Design:
  - Graph is rebuilt from scratch on every memory extraction run (idempotent)
  - Entities are embedded for similarity search at query time
  - Traversal is bidirectional (follows edges in both directions)
  - All DB errors are caught and logged; callers receive empty results on failure
"""

from __future__ import annotations

import uuid
from collections import deque

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domains.embedding.embedder import (
    EmbeddingProfile,
    embed_batch_with_failover,
    embed_text_with_profile,
    get_primary_embedding_profile,
    resolve_embedding_profile,
)
from app.domains.graph.extractor import GraphExtractionResult
from app.models.graph import GraphEntity, GraphRelationship

logger = get_logger(__name__)

_ENTITY_SIMILARITY_THRESHOLD = 0.15


async def rebuild_graph(
    doctwin_id: str,
    extraction: GraphExtractionResult,
    db: AsyncSession,
) -> None:
    """
    Idempotent graph rebuild: delete existing entities/relationships for the twin,
    then insert the fresh extraction result.

    Embeds each entity's (name + description) for later similarity search.
    Relationships are only inserted when both endpoint entities are present.
    """
    doctwin_uuid = uuid.UUID(doctwin_id)

    await db.execute(
        delete(GraphRelationship).where(GraphRelationship.doctwin_id == doctwin_uuid)
    )
    await db.execute(delete(GraphEntity).where(GraphEntity.doctwin_id == doctwin_uuid))
    await db.flush()

    if not extraction.entities:
        await db.commit()
        return

    entity_rows: dict[str, GraphEntity] = {}
    embed_texts = [
        f"{entity.name}: {entity.description}"
        for entity in extraction.entities
    ]
    batch_result = await embed_batch_with_failover(embed_texts, task="document", db=db)

    for entity, embedding in zip(extraction.entities, batch_result.embeddings, strict=False):

        row = GraphEntity(
            doctwin_id=doctwin_uuid,
            name=entity.name,
            entity_type=entity.entity_type,
            description=entity.description,
            source_refs=entity.source_refs or [],
            embedding=embedding,
            embedding_provider=batch_result.profile.provider,
            embedding_model=batch_result.profile.model,
            embedding_dimensions=batch_result.profile.dimensions,
        )
        db.add(row)
        entity_rows[entity.name.lower()] = row

    await db.flush()

    for rel in extraction.relationships:
        src = entity_rows.get(rel.source.lower())
        tgt = entity_rows.get(rel.target.lower())
        if src is None or tgt is None:
            continue

        db.add(
            GraphRelationship(
                doctwin_id=doctwin_uuid,
                source_entity_id=src.id,
                target_entity_id=tgt.id,
                relationship_type=rel.relationship_type,
                description=rel.description,
                weight=1.0,
            )
        )

    await db.commit()
    logger.info(
        "graph_rebuilt",
        doctwin_id=doctwin_id,
        entities=len(entity_rows),
        relationships=len(extraction.relationships),
    )


async def find_entities_for_query(
    query: str,
    doctwin_id: str,
    db: AsyncSession,
    top_k: int = 5,
) -> list[GraphEntity]:
    """
    Find entities most relevant to a query using embedding cosine similarity.
    Returns [] if the graph has no entities or embedding fails.
    """
    profiles = await _load_graph_profiles(doctwin_id, db)
    if not profiles:
        return []

    candidates: dict[uuid.UUID, GraphEntity] = {}
    candidate_scores: dict[uuid.UUID, float] = {}
    primary_profile = get_primary_embedding_profile()

    sql = text("""
        SELECT id, name, entity_type, description, source_refs,
               1 - (embedding <=> :embedding ::vector) AS score
        FROM graph_entities
        WHERE doctwin_id = :doctwin_id
          AND embedding IS NOT NULL
          AND COALESCE(embedding_provider, :legacy_provider) = :provider
          AND COALESCE(embedding_model, :legacy_model) = :model
          AND COALESCE(embedding_dimensions, :legacy_dimensions) = :dimensions
          AND 1 - (embedding <=> :embedding ::vector) >= :threshold
        ORDER BY embedding <=> :embedding ::vector
        LIMIT :top_k
    """)

    for profile in profiles:
        try:
            query_embedding = await embed_text_with_profile(query, profile, task="query", db=db)
        except Exception as exc:
            logger.warning(
                "graph_query_embed_failed",
                doctwin_id=doctwin_id,
                provider=profile.provider,
                model=profile.model,
                error=str(exc),
            )
            continue

        emb_literal = "[" + ",".join(f"{v:.8f}" for v in query_embedding) + "]"
        try:
            result = await db.execute(
                sql,
                {
                    "doctwin_id": str(doctwin_id),
                    "embedding": emb_literal,
                    "threshold": _ENTITY_SIMILARITY_THRESHOLD,
                    "top_k": top_k,
                    "provider": profile.provider,
                    "model": profile.model,
                    "dimensions": profile.dimensions,
                    "legacy_provider": primary_profile.provider,
                    "legacy_model": primary_profile.model,
                    "legacy_dimensions": primary_profile.dimensions,
                },
            )
            rows = result.fetchall()
        except Exception as exc:
            logger.warning("graph_entity_search_failed", doctwin_id=doctwin_id, error=str(exc))
            await db.rollback()
            continue

        for row in rows:
            score = float(row.score)
            if row.id in candidate_scores and candidate_scores[row.id] >= score:
                continue
            candidate_scores[row.id] = score
            candidates[row.id] = GraphEntity(
                id=row.id,
                doctwin_id=uuid.UUID(doctwin_id),
                name=row.name,
                entity_type=row.entity_type,
                description=row.description,
                source_refs=row.source_refs or [],
                embedding_provider=profile.provider,
                embedding_model=profile.model,
                embedding_dimensions=profile.dimensions,
            )

    ranked_ids = sorted(candidate_scores, key=lambda entity_id: candidate_scores[entity_id], reverse=True)
    return [candidates[entity_id] for entity_id in ranked_ids[:top_k]]


async def traverse_graph(
    seed_entities: list[GraphEntity],
    doctwin_id: str,
    db: AsyncSession,
    max_depth: int = 2,
    max_nodes: int = 20,
) -> tuple[list[GraphEntity], list[GraphRelationship]]:
    """
    BFS from seed_entities, following relationships bidirectionally up to max_depth hops.

    Returns (all_entities_visited, all_relationships_traversed).
    Both lists are deduplicated by ID.
    """
    if not seed_entities:
        return [], []

    visited_ids: set[uuid.UUID] = {e.id for e in seed_entities}
    queue: deque[tuple[GraphEntity, int]] = deque((e, 0) for e in seed_entities)
    all_entities: list[GraphEntity] = list(seed_entities)
    all_relationships: list[GraphRelationship] = []
    seen_rel_ids: set[uuid.UUID] = set()

    while queue and len(all_entities) < max_nodes:
        entity, depth = queue.popleft()
        if depth >= max_depth:
            continue

        sql = text("""
            WITH neighbors AS (
                SELECT
                    r.id        AS rel_id,
                    r.source_entity_id,
                    r.target_entity_id,
                    r.relationship_type,
                    r.description,
                    CASE
                        WHEN r.source_entity_id = :entity_id THEN r.target_entity_id
                        ELSE r.source_entity_id
                    END AS neighbor_id
                FROM graph_relationships r
                WHERE r.doctwin_id = :doctwin_id
                  AND (r.source_entity_id = :entity_id OR r.target_entity_id = :entity_id)
            )
            SELECT
                n.rel_id,
                n.source_entity_id,
                n.target_entity_id,
                n.relationship_type,
                n.description,
                e.id          AS neighbor_id,
                e.name        AS neighbor_name,
                e.entity_type AS neighbor_type,
                e.description AS neighbor_desc,
                e.source_refs AS neighbor_refs
            FROM neighbors n
            JOIN graph_entities e ON e.id = n.neighbor_id
        """)

        try:
            result = await db.execute(sql, {
                "entity_id": str(entity.id),
                "doctwin_id": str(doctwin_id),
            })
            rows = result.fetchall()
        except Exception as exc:
            logger.warning("graph_traversal_step_failed", doctwin_id=doctwin_id, error=str(exc))
            await db.rollback()
            break

        for row in rows:
            if row.rel_id not in seen_rel_ids:
                seen_rel_ids.add(row.rel_id)
                all_relationships.append(
                    GraphRelationship(
                        id=row.rel_id,
                        doctwin_id=uuid.UUID(doctwin_id),
                        source_entity_id=row.source_entity_id,
                        target_entity_id=row.target_entity_id,
                        relationship_type=row.relationship_type,
                        description=row.description,
                    )
                )

            neighbor_id = row.neighbor_id
            if neighbor_id not in visited_ids and len(all_entities) < max_nodes:
                neighbor = GraphEntity(
                    id=neighbor_id,
                    doctwin_id=uuid.UUID(doctwin_id),
                    name=row.neighbor_name,
                    entity_type=row.neighbor_type,
                    description=row.neighbor_desc,
                    source_refs=row.neighbor_refs or [],
                )
                visited_ids.add(neighbor_id)
                all_entities.append(neighbor)
                queue.append((neighbor, depth + 1))

    return all_entities, all_relationships


async def _load_graph_profiles(
    doctwin_id: str,
    db: AsyncSession,
) -> list[EmbeddingProfile]:
    result = await db.execute(
        select(
            GraphEntity.embedding_provider,
            GraphEntity.embedding_model,
            GraphEntity.embedding_dimensions,
        )
        .where(
            GraphEntity.doctwin_id == uuid.UUID(doctwin_id),
            GraphEntity.embedding.is_not(None),
        )
        .distinct()
    )

    profiles: list[EmbeddingProfile] = []
    seen: set[tuple[str, str, int]] = set()
    primary = get_primary_embedding_profile()
    for row in result.fetchall():
        profile = resolve_embedding_profile(
            row.embedding_provider or primary.provider,
            row.embedding_model or primary.model,
            row.embedding_dimensions or primary.dimensions,
            use_default_model=True,
        )
        key = (profile.provider, profile.model, profile.dimensions)
        if key in seen:
            continue
        seen.add(key)
        profiles.append(profile)

    return profiles


def format_graph_context(
    entities: list[GraphEntity],
    relationships: list[GraphRelationship],
    entity_map: dict | None = None,
) -> str:
    """
    Render graph traversal results as a context string for LLM prompts.

    entity_map: optional dict[entity_id → GraphEntity] for relationship label lookup.
    """
    if not entities:
        return ""

    lines = ["### Entities\n"]
    for e in entities:
        lines.append(f"- **{e.name}** ({e.entity_type}): {e.description}")

    if relationships and entity_map:
        lines.append("\n### Relationships\n")
        for r in relationships[:40]:
            src = entity_map.get(r.source_entity_id)
            tgt = entity_map.get(r.target_entity_id)
            if src and tgt:
                desc = f": {r.description}" if r.description else ""
                lines.append(
                    f"- {src.name} —[{r.relationship_type}]→ {tgt.name}{desc}"
                )

    return "\n".join(lines)


async def get_graph_summary(doctwin_id: str, db: AsyncSession) -> str:
    """
    Return the full graph as a formatted context string for memory brief generation.
    Returns "" if the graph is empty.
    """
    entity_result = await db.execute(
        select(GraphEntity).where(GraphEntity.doctwin_id == uuid.UUID(doctwin_id))
    )
    entities = list(entity_result.scalars().all())

    if not entities:
        return ""

    rel_result = await db.execute(
        select(GraphRelationship).where(GraphRelationship.doctwin_id == uuid.UUID(doctwin_id))
    )
    relationships = list(rel_result.scalars().all())

    entity_map = {e.id: e for e in entities}
    return format_graph_context(entities, relationships, entity_map)
