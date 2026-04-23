"""
LLM-based entity and relationship extraction for the knowledge graph.

Reads typed chunks from the twin's knowledge base and produces:
  - Entities: modules, technologies, services, concepts, data models
  - Relationships: how entities connect (uses, depends_on, calls, etc.)

Design:
  - Processes chunks in batches of 30 to stay within context limits
  - Uses module_description, documentation, dependency_signal, hotspot, decision_record chunks
    as primary signal — these are the highest-density knowledge chunks
  - Merges entity duplicates across batches by lowercased name
  - Never raises — errors return empty result per batch
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

from app.core.logging import get_logger
from app.domains.answering.llm_provider import get_llm_provider

logger = get_logger(__name__)

_USEFUL_CHUNK_TYPES = {
    "module_description",
    "documentation",
    "dependency_signal",
    "architecture_summary",
    "hotspot",
    "decision_record",
}

_BATCH_SIZE = 30
_MAX_CONTENT_PER_CHUNK = 600
# Cap total chunks fed to the graph extractor. Without a cap, large repos
# with 500+ chunks run 15-20 sequential LLM calls (batch size 30), which
# takes 4-5 minutes before the memory extraction passes even start.
# 150 chunks = 5 batches = ~30-60 seconds, which is sufficient signal
# for a useful graph without dominating the total extraction time.
_MAX_GRAPH_CHUNKS = 150


class ExtractedEntity(BaseModel):
    name: str
    entity_type: str  # module | technology | service | concept | data_model
    description: str
    source_refs: list[str] = []


class ExtractedRelationship(BaseModel):
    source: str
    target: str
    relationship_type: str  # uses | depends_on | calls | contains | implements | extends | produces | consumes
    description: str


class GraphExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = []
    relationships: list[ExtractedRelationship] = []


_EXTRACTION_SYSTEM = """\
You are a senior staff engineer extracting a structured knowledge graph from a software codebase.

You will receive knowledge chunks extracted from the codebase. Extract:

ENTITIES — meaningful, stable components. Types:
  module      — a file, class, or directory with a clear responsibility
  technology  — a framework, library, or language (FastAPI, pgvector, ARQ, React)
  service     — an external API, database, or infrastructure (Redis, PostgreSQL, Cohere)
  concept     — an architectural pattern or domain concept (Twin, Policy Filtering, Memory Layer)
  data_model  — a key data structure (Chunk, TwinConfig, MemoryBrief, Source)

RELATIONSHIPS — how entities connect. Types:
  uses        — A uses technology/service B
  depends_on  — module A imports or depends on module B
  calls       — module A calls external service/API B
  contains    — directory A contains module B
  implements  — module A implements concept B
  extends     — class A extends/inherits B
  produces    — module A produces data_model B
  consumes    — module A consumes data_model B

Return ONLY a JSON object:
{
  "entities": [
    {"name": "...", "entity_type": "...", "description": "...", "source_refs": ["path/to/file"]},
    ...
  ],
  "relationships": [
    {"source": "entity name", "target": "entity name", "relationship_type": "...", "description": "..."},
    ...
  ]
}

Hard rules:
  - Only extract entities clearly evidenced in the chunks. Never invent.
  - Entity names must be stable identifiers: module paths, class names, technology names.
  - 5–20 entities per batch. 5–30 relationships per batch.
  - source_refs must be actual file paths from the chunks.
  - Both source and target in a relationship must be entity names you also listed in entities[].
  - Return ONLY the JSON. No markdown fences, no commentary.
"""


async def extract_graph_from_chunks(
    chunks: list[dict],
    doctwin_id: str,
    trace_id: str | None = None,
) -> GraphExtractionResult:
    """
    Extract entities and relationships from a twin's chunks.

    Processes in batches of _BATCH_SIZE, merging results across batches.
    Prefers high-signal chunk types (module_description, hotspot, etc.) but
    falls back to all chunks if none of those types are present.

    Returns an empty result on any error.
    """
    if not chunks:
        return GraphExtractionResult()

    filtered = [c for c in chunks if c.get("chunk_type") in _USEFUL_CHUNK_TYPES]
    if not filtered:
        filtered = chunks

    # Cap input to avoid excessive LLM batches on large repos.
    # Prioritise by chunk type (module_description first) so the most
    # useful signal is always included within the cap.
    if len(filtered) > _MAX_GRAPH_CHUNKS:
        priority_order = [
            "module_description", "dependency_signal", "documentation",
            "hotspot", "decision_record", "architecture_summary",
        ]
        priority_map = {t: i for i, t in enumerate(priority_order)}
        filtered = sorted(filtered, key=lambda c: priority_map.get(c.get("chunk_type", ""), 99))
        filtered = filtered[:_MAX_GRAPH_CHUNKS]

    all_entities: dict[str, ExtractedEntity] = {}
    all_relationships: list[ExtractedRelationship] = []
    seen_rel_keys: set[tuple] = set()

    batch_count = 0
    for i in range(0, len(filtered), _BATCH_SIZE):
        batch = filtered[i : i + _BATCH_SIZE]
        result = await _extract_batch(batch, doctwin_id, trace_id)
        batch_count += 1

        for entity in result.entities:
            key = entity.name.lower()
            if key not in all_entities:
                all_entities[key] = entity
            else:
                existing = all_entities[key]
                merged_refs = list(set(existing.source_refs + entity.source_refs))
                all_entities[key] = existing.model_copy(update={"source_refs": merged_refs})

        for rel in result.relationships:
            rel_key = (rel.source.lower(), rel.target.lower(), rel.relationship_type)
            if rel_key not in seen_rel_keys:
                seen_rel_keys.add(rel_key)
                all_relationships.append(rel)

    # Drop relationships whose endpoints aren't in the entity set
    entity_names = set(all_entities.keys())
    valid_relationships = [
        r for r in all_relationships
        if r.source.lower() in entity_names and r.target.lower() in entity_names
    ]

    logger.info(
        "graph_extraction_complete",
        doctwin_id=doctwin_id,
        batches=batch_count,
        entities=len(all_entities),
        relationships=len(valid_relationships),
    )

    return GraphExtractionResult(
        entities=list(all_entities.values()),
        relationships=valid_relationships,
    )


async def _extract_batch(
    chunks: list[dict],
    doctwin_id: str,
    trace_id: str | None,
) -> GraphExtractionResult:
    parts = []
    for c in chunks:
        ref = c.get("source_ref", "")
        ctype = c.get("chunk_type", "")
        content = c.get("content", "")[:_MAX_CONTENT_PER_CHUNK]
        parts.append(f"[{ctype}] {ref}\n{content}")

    context = "\n\n---\n\n".join(parts)
    provider = get_llm_provider()

    try:
        response = await provider.complete(
            system_prompt=_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": context}],
            max_tokens=3000,
            temperature=0.1,
            trace_id=trace_id,
            generation_name="graph_entity_extraction",
        )
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", response.content.strip(), flags=re.MULTILINE
        )
        data = json.loads(cleaned)
        return GraphExtractionResult.model_validate(data)
    except Exception as exc:
        logger.warning("graph_batch_extraction_failed", doctwin_id=doctwin_id, error=str(exc))
        return GraphExtractionResult()
