"""
Cross-encoder reranking for retrieved chunks.

After pgvector retrieves a candidate set (2–3× over-fetch), this module
re-scores each (query, chunk) pair using a cross-encoder model that reads
both together — producing much higher relevance precision than cosine
similarity alone.

Provider hierarchy:
  1. Cohere Rerank API   — if COHERE_API_KEY is set (recommended)
  2. No-op fallback      — returns candidates[:top_k] in vector order

Usage:
    from app.domains.retrieval.reranker import rerank_chunks, reranker_available

    if reranker_available():
        chunks = await rerank_chunks(query, candidates, top_k)
    else:
        chunks = candidates[:top_k]
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_COHERE_MODEL = "rerank-english-v3.0"


def reranker_available() -> bool:
    """Return True if a reranker is configured and usable."""
    return bool(get_settings().cohere_api_key)


async def rerank_chunks(
    query: str,
    candidates: list[dict],
    top_k: int,
) -> list[dict]:
    """
    Rerank candidates and return the top_k most relevant.

    Each candidate dict must have a 'content' key.
    The returned chunks have their 'score' field updated with the rerank score.

    Falls back to candidates[:top_k] (original vector order) on any error
    or when no reranker is configured.
    """
    if not candidates:
        return []

    settings = get_settings()

    if settings.cohere_api_key:
        return await _cohere_rerank(query, candidates, top_k, settings.cohere_api_key)

    return candidates[:top_k]


async def _cohere_rerank(
    query: str,
    candidates: list[dict],
    top_k: int,
    api_key: str,
) -> list[dict]:
    try:
        import cohere

        # cohere v5+ uses ClientV2; v4 uses Client. Try v5 first.
        try:
            co = cohere.AsyncClientV2(api_key=api_key)
        except AttributeError:
            co = cohere.AsyncClient(api_key=api_key)  # type: ignore[attr-defined]

        response = await co.rerank(
            model=_COHERE_MODEL,
            query=query,
            documents=[c["content"] for c in candidates],
            top_n=min(top_k, len(candidates)),
        )

        reranked: list[dict] = []
        for result in response.results:
            chunk = candidates[result.index].copy()
            chunk["score"] = float(result.relevance_score)
            chunk["rerank_score"] = float(result.relevance_score)
            reranked.append(chunk)

        logger.info(
            "rerank_complete",
            provider="cohere",
            candidates_in=len(candidates),
            candidates_out=len(reranked),
            top_score=round(reranked[0]["score"], 3) if reranked else 0,
        )
        return reranked

    except Exception as exc:
        logger.warning("rerank_failed_using_vector_order", error=str(exc))
        return candidates[:top_k]
