"""
Operator diagnostics for RAG: indexed chunks, embeddings, and retrieval previews.

Used by the admin API and structured logs — not exposed to end users.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domains.retrieval.router import (
    _load_doctwin_allow_code_snippets,
    _load_doctwin_embedding_profiles,
    retrieve_packet_for_twin,
)
from app.models.chunk import Chunk
from app.models.source import Source, SourceStatus

logger = get_logger(__name__)


async def collect_twin_rag_index_stats(doctwin_id: str, db: AsyncSession) -> dict[str, Any]:
    """
    Per-source chunk counts, embedding coverage, and aggregate chunk-type breakdown.

    Aligns with chat retrieval: ``Source.status == ready`` is what hybrid search uses.
    """
    did = uuid.UUID(doctwin_id)

    per_source = await db.execute(
        select(
            Source.id,
            Source.name,
            Source.status,
            Source.source_type,
            Source.embedding_provider,
            Source.embedding_model,
            Source.embedding_dimensions,
            func.count(Chunk.id).label("chunk_count"),
            func.coalesce(
                func.sum(case((Chunk.embedding.is_not(None), 1), else_=0)),
                0,
            ).label("chunks_with_embedding"),
            func.coalesce(
                func.sum(case((Chunk.embedding.is_(None), 1), else_=0)),
                0,
            ).label("chunks_without_embedding"),
        )
        .outerjoin(Chunk, Chunk.source_id == Source.id)
        .where(Source.doctwin_id == did)
        .group_by(
            Source.id,
            Source.name,
            Source.status,
            Source.source_type,
            Source.embedding_provider,
            Source.embedding_model,
            Source.embedding_dimensions,
        )
        .order_by(Source.name.asc())
    )
    sources: list[dict[str, Any]] = []
    for row in per_source.fetchall():
        sources.append(
            {
                "source_id": str(row.id),
                "name": row.name,
                "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                "source_type": (
                    row.source_type.value
                    if hasattr(row.source_type, "value")
                    else str(row.source_type)
                ),
                "embedding_provider": row.embedding_provider,
                "embedding_model": row.embedding_model,
                "embedding_dimensions": row.embedding_dimensions,
                "chunk_count": int(row.chunk_count or 0),
                "chunks_with_embedding": int(row.chunks_with_embedding or 0),
                "chunks_without_embedding": int(row.chunks_without_embedding or 0),
            }
        )

    # Chunk types for evidence eligible for retrieval (ready sources, not synthetic memory)
    type_rows = await db.execute(
        select(
            Chunk.chunk_type,
            func.count(Chunk.id).label("n"),
            func.coalesce(
                func.sum(case((Chunk.embedding.is_not(None), 1), else_=0)),
                0,
            ).label("with_emb"),
        )
        .join(Source, Source.id == Chunk.source_id)
        .where(
            Source.doctwin_id == did,
            Source.status == SourceStatus.ready,
            Source.name != "__memory__",
        )
        .group_by(Chunk.chunk_type)
    )
    chunk_types = [
        {
            "chunk_type": str(
                r.chunk_type.value if hasattr(r.chunk_type, "value") else r.chunk_type
            ),
            "count": int(r.n or 0),
            "with_embedding": int(r.with_emb or 0),
        }
        for r in type_rows.fetchall()
    ]

    profiles = await _load_doctwin_embedding_profiles(doctwin_id, db)
    embedding_profiles = [
        {"provider": p.provider, "model": p.model, "dimensions": p.dimensions} for p in profiles
    ]

    logger.info(
        "rag_index_stats_collected",
        doctwin_id=doctwin_id,
        sources=len(sources),
        embedding_profiles=len(embedding_profiles),
    )

    return {
        "sources": sources,
        "chunk_types_ready_non_memory": chunk_types,
        "embedding_profiles_from_indexed_chunks": embedding_profiles,
    }


async def preview_twin_retrieval(
    *,
    doctwin_id: str,
    query: str,
    db: AsyncSession,
    top_k: int = 12,
) -> dict[str, Any]:
    """Run the same retrieval path as chat and return a serializable preview."""
    allow_code = await _load_doctwin_allow_code_snippets(doctwin_id, db)
    packet = await retrieve_packet_for_twin(
        query=query,
        doctwin_id=doctwin_id,
        allow_code_snippets=allow_code,
        db=db,
        top_k=top_k,
    )
    hits: list[dict[str, Any]] = []
    for c in packet.chunks:
        hits.append(
            {
                "chunk_id": str(c.get("chunk_id") or ""),
                "score": round(float(c.get("score") or 0.0), 6),
                "chunk_type": str(c.get("chunk_type") or ""),
                "source_ref": (c.get("source_ref") or "")[:200],
                "source_id": str(c.get("source_id") or ""),
                "match_reasons": list(c.get("match_reasons") or []),
                "content_preview": (c.get("content") or "")[:400],
            }
        )
    return {
        "query": query,
        "search_query": packet.search_query,
        "lexical_query": packet.lexical_query,
        "intent": packet.intent,
        "mode": packet.mode.value if hasattr(packet.mode, "value") else str(packet.mode),
        "searched_layers": list(packet.searched_layers),
        "missing_evidence": list(packet.missing_evidence),
        "hits": hits,
    }
