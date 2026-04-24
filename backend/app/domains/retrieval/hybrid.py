"""
Hybrid retrieval helpers: lexical candidate discovery + candidate merging.

Only two retrieval layers are needed for document-only use:
  1. Vector (pgvector cosine) — lives in router.py, profile-aware
  2. Lexical (PostgreSQL FTS) — fetch_lexical_chunk_candidates() here

File index, symbol index, and graph multihop were removed: they were
code-intelligence features with no value for document sources.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)

_STOPWORD_TOKENS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "your",
    "what", "where", "when", "which", "how", "does", "work", "walk", "through",
    "across", "covered", "projects", "project", "implemented", "implementation",
    "flow", "explain", "provide", "necessary",
}


def merge_candidate(candidates_by_id: dict[str, dict[str, Any]], candidate: dict[str, Any]) -> None:
    chunk_id = str(candidate["chunk_id"])
    existing = candidates_by_id.get(chunk_id)
    if existing is None:
        candidate["match_reasons"] = list(dict.fromkeys(candidate.get("match_reasons") or []))
        candidates_by_id[chunk_id] = candidate
        return

    if float(candidate.get("score") or 0.0) > float(existing.get("score") or 0.0):
        existing["score"] = float(candidate["score"])

    for reason in candidate.get("match_reasons") or []:
        if reason not in existing.setdefault("match_reasons", []):
            existing["match_reasons"].append(reason)


async def fetch_lexical_chunk_candidates(
    *,
    db: AsyncSession,
    doctwin_id: str,
    lexical_query: str,
    allow_code_snippets: bool,
    limit: int,
) -> list[dict[str, Any]]:
    if not lexical_query.strip():
        return []

    sql = text(
        """
        WITH lexical_query AS (
            SELECT websearch_to_tsquery('simple', :query) AS q
        )
        SELECT
            c.id,
            c.content,
            c.chunk_type,
            c.source_ref,
            LEAST(
                0.95,
                0.35 + ts_rank_cd(
                    setweight(to_tsvector('simple', COALESCE(c.source_ref, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(c.content, '')), 'B'),
                    lexical_query.q
                )
            ) AS score
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        CROSS JOIN lexical_query
        WHERE s.doctwin_id = :doctwin_id
          AND s.status = 'ready'
          AND c.chunk_type != 'memory_brief'
          AND lexical_query.q <> ''::tsquery
          AND (
            setweight(to_tsvector('simple', COALESCE(c.source_ref, '')), 'A') ||
            setweight(to_tsvector('simple', COALESCE(c.content, '')), 'B')
          ) @@ lexical_query.q
        ORDER BY score DESC
        LIMIT :limit
        """
    )

    try:
        result = await db.execute(
            sql,
            {
                "query": lexical_query,
                "doctwin_id": doctwin_id,
                "limit": limit,
            },
        )
    except Exception as exc:
        logger.warning("lexical_chunk_search_failed", doctwin_id=doctwin_id, error=str(exc))
        await db.rollback()
        return []

    rows = result.fetchall()
    if not rows:
        rows = await _fetch_chunk_candidates_by_substring(
            db=db,
            doctwin_id=doctwin_id,
            lexical_query=lexical_query,
            limit=limit,
        )
        if not rows:
            return []

    return [
        {
            "chunk_id": str(row.id),
            "content": row.content,
            "chunk_type": row.chunk_type,
            "source_ref": row.source_ref,
            "score": float(row.score),
            "match_reasons": ["lexical"],
        }
        for row in rows
    ]


def _tokenise_lexical_query(lexical_query: str) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(r"[a-zA-Z_][a-zA-Z0-9_./-]{1,}", lexical_query):
        token = raw.lower().strip(".,;:!?)]}")
        if len(token) < 3 or token in _STOPWORD_TOKENS or token in seen:
            continue
        seen.add(token)
        ordered.append(token)

    def priority(token: str) -> tuple[int, int]:
        if "/" in token or "." in token:
            return (0, -len(token))
        if re.search(r"week\d+", token):
            return (1, -len(token))
        if len(token) >= 10:
            return (2, -len(token))
        return (3, 0)

    return sorted(ordered, key=priority)


async def _fetch_chunk_candidates_by_substring(
    *,
    db: AsyncSession,
    doctwin_id: str,
    lexical_query: str,
    limit: int,
) -> list[Any]:
    tokens = _tokenise_lexical_query(lexical_query)[:16]
    if not tokens:
        return []

    clauses = []
    params: dict[str, Any] = {"doctwin_id": doctwin_id, "limit": limit}
    for index, token in enumerate(tokens):
        key = f"token_{index}"
        params[key] = f"%{token}%"
        clauses.append(
            f"(lower(coalesce(c.source_ref, '')) LIKE :{key} OR lower(coalesce(c.content, '')) LIKE :{key})"
        )
    sql = text(
        f"""
        SELECT
            c.id,
            c.content,
            c.chunk_type,
            c.source_ref,
            LEAST(
                0.9,
                0.32 + (
                    {' + '.join(f"CASE WHEN {clause} THEN 0.08 ELSE 0 END" for clause in clauses)}
                )
            ) AS score
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE s.doctwin_id = :doctwin_id
          AND s.status = 'ready'
          AND c.chunk_type != 'memory_brief'
          AND coalesce(c.source_ref, '') NOT LIKE '__memory__/%'
          AND ({' OR '.join(clauses)})
        ORDER BY score DESC, c.source_ref, c.id
        LIMIT :limit
        """
    )
    try:
        result = await db.execute(sql, params)
    except Exception as exc:
        logger.warning("lexical_chunk_substring_search_failed", doctwin_id=doctwin_id, error=str(exc))
        await db.rollback()
        return []
    return result.fetchall()
