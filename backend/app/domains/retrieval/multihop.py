"""
Multi-hop retrieval using the knowledge graph.

Standard vector search finds chunks that are semantically close to the query.
Multi-hop retrieval goes further: it finds entities in the knowledge graph that
match the query, then traverses the graph to discover connected entities, and
pulls in chunks from all those connected components.

This surfaces chunks that vector similarity alone would miss — for example, if
you ask "what happens when a message is sent?", vector search finds ChatService.
Multi-hop then traverses ChatService → RetrieverRouter → Embedder → pgvector,
and pulls in chunks from all of those modules even if the query didn't mention them.

Usage:
    additional = await multihop_retrieve(query, doctwin_id, db, allow_code_snippets)

The returned chunks supplement (not replace) the vector search results.
Callers should merge and deduplicate by chunk_id.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domains.graph.service import find_entities_for_query, traverse_graph
from app.models.chunk import Chunk, ChunkType
from app.models.graph import GraphEntity, GraphRelationship
from app.models.source import Source, SourceStatus

logger = get_logger(__name__)

_GRAPH_CHUNK_SCORE = 0.50  # mid-range score for graph-sourced chunks


async def multihop_retrieve(
    query: str,
    doctwin_id: str,
    db: AsyncSession,
    allow_code_snippets: bool,
    max_additional_chunks: int = 4,
) -> list[dict]:
    chunks, _graph_edges = await multihop_retrieve_with_graph(
        query=query,
        doctwin_id=doctwin_id,
        db=db,
        allow_code_snippets=allow_code_snippets,
        max_additional_chunks=max_additional_chunks,
    )
    return chunks


async def multihop_retrieve_with_graph(
    query: str,
    doctwin_id: str,
    db: AsyncSession,
    allow_code_snippets: bool,
    max_additional_chunks: int = 4,
) -> tuple[list[dict], list[dict[str, str]]]:
    """
    Graph-guided retrieval to supplement vector search.

    Steps:
      1. Embed the query and find the top-3 matching graph entities
      2. BFS traverse the graph up to 2 hops from those seeds
      3. Collect source_refs from all visited entities
      4. Fetch chunks whose source_ref matches one of those refs
      5. Return up to max_additional_chunks chunks

    Returns (chunks, graph_edges).
    Returns ([], []) if the knowledge graph is not built or no entities match.
    All DB errors are caught; callers receive an empty list on failure.
    """
    seed_entities = await find_entities_for_query(query, doctwin_id, db, top_k=3)
    if not seed_entities:
        logger.debug("multihop_no_seed_entities", doctwin_id=doctwin_id)
        return [], []

    all_entities, all_relationships = await traverse_graph(
        seed_entities, doctwin_id, db, max_depth=2, max_nodes=15
    )

    source_refs: set[str] = set()
    for entity in all_entities:
        for ref in entity.source_refs or []:
            if ref:
                source_refs.add(ref)

    if not source_refs:
        return [], _format_graph_edges(all_entities, all_relationships)

    stmt = (
        select(Chunk.id, Chunk.content, Chunk.chunk_type, Chunk.source_ref)
        .join(Source, Chunk.source_id == Source.id)
        .where(
            Source.doctwin_id == uuid.UUID(doctwin_id),
            Source.status == SourceStatus.ready,
            Chunk.source_ref.in_(list(source_refs)),
        )
        .limit(max_additional_chunks * 3)  # over-fetch; caller deduplicates
    )
    if not allow_code_snippets:
        stmt = stmt.where(Chunk.chunk_type != ChunkType.code_snippet)

    try:
        result = await db.execute(stmt)
        rows = result.fetchall()
    except Exception as exc:
        logger.warning("multihop_chunk_fetch_failed", doctwin_id=doctwin_id, error=str(exc))
        await db.rollback()
        return [], _format_graph_edges(all_entities, all_relationships)

    chunks = [
        {
            "chunk_id": str(row.id),
            "content": row.content,
            "chunk_type": str(row.chunk_type.value if hasattr(row.chunk_type, "value") else row.chunk_type),
            "source_ref": row.source_ref,
            "score": _GRAPH_CHUNK_SCORE,
            "via_graph": True,
        }
        for row in rows[:max_additional_chunks]
    ]

    logger.info(
        "multihop_complete",
        doctwin_id=doctwin_id,
        seed_entities=len(seed_entities),
        traversed_entities=len(all_entities),
        source_refs=len(source_refs),
        chunks_found=len(chunks),
    )
    return chunks, _format_graph_edges(all_entities, all_relationships)


def _format_graph_edges(
    entities: list[GraphEntity],
    relationships: list[GraphRelationship],
) -> list[dict[str, str]]:
    entity_map = {entity.id: entity.name for entity in entities}
    edges: list[dict[str, str]] = []
    for relationship in relationships:
        source_name = entity_map.get(relationship.source_entity_id)
        target_name = entity_map.get(relationship.target_entity_id)
        if not source_name or not target_name:
            continue
        edges.append(
            {
                "source": source_name,
                "target": target_name,
                "relationship_type": relationship.relationship_type,
            }
        )
    return edges
