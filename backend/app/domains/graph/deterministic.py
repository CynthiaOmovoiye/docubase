"""
Deterministic knowledge-graph seed (simplified).

Repo-intelligence indexing (implementation facts, indexed files/symbols) was
removed from docbase. Memory extraction still calls this entry point; it now
returns an empty graph so the LLM graph pass can run on chunks alone.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.graph.extractor import GraphExtractionResult


async def build_deterministic_graph(
    doctwin_id: str,
    db: AsyncSession,
) -> GraphExtractionResult:
    del doctwin_id, db
    return GraphExtractionResult(entities=[], relationships=[])


def merge_graph_extractions(
    deterministic: GraphExtractionResult,
    llm: GraphExtractionResult,
) -> GraphExtractionResult:
    """Prefer LLM graph; fold in any deterministic entities/edges without duplicates."""
    entities = list(deterministic.entities)
    seen_names = {e.name.strip().lower() for e in entities}
    for e in llm.entities:
        key = e.name.strip().lower()
        if key not in seen_names:
            seen_names.add(key)
            entities.append(e)

    rels = list(deterministic.relationships)
    seen_rels = {
        (r.source.strip().lower(), r.target.strip().lower(), r.relationship_type)
        for r in rels
    }
    for r in llm.relationships:
        key = (r.source.strip().lower(), r.target.strip().lower(), r.relationship_type)
        if key not in seen_rels:
            seen_rels.add(key)
            rels.append(r)
    return GraphExtractionResult(entities=entities, relationships=rels)
