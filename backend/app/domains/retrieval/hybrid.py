"""
Hybrid retrieval helpers for lexical, file, and symbol candidate discovery.

The vector path remains in router.py because it is profile-aware. This module
adds the deterministic search layers Phase 2 needs for better code intelligence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domains.retrieval.packets import EvidenceFileRef, EvidenceSymbolRef

logger = get_logger(__name__)
_STOPWORD_TOKENS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "your",
    "what", "where", "when", "which", "how", "does", "work", "walk", "through",
    "across", "covered", "projects", "project", "implemented", "implementation",
    "flow", "explain", "provide", "necessary",
}
_DOMAIN_PRIORITY_TOKENS = {
    "auth",
    "authentication",
    "authorization",
    "login",
    "logout",
    "register",
    "signup",
    "signin",
    "refresh",
    "token",
    "session",
    "jwt",
    "current_user",
    "guard",
    "middleware",
    "dashboard",
    "load",
    "planning",
    "remaining",
    "progress",
}


@dataclass(slots=True)
class HybridMatches:
    chunks: list[dict[str, Any]]
    files: list[EvidenceFileRef]
    symbols: list[EvidenceSymbolRef]


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

    code_filter = "" if allow_code_snippets else "AND c.chunk_type != 'code_snippet'"
    sql = text(
        f"""
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
          AND lexical_query.q <> ''::tsquery
          AND (
            setweight(to_tsvector('simple', COALESCE(c.source_ref, '')), 'A') ||
            setweight(to_tsvector('simple', COALESCE(c.content, '')), 'B')
          ) @@ lexical_query.q
          {code_filter}
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
            allow_code_snippets=allow_code_snippets,
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


async def fetch_file_candidates(
    *,
    db: AsyncSession,
    doctwin_id: str,
    lexical_query: str,
    allow_code_snippets: bool,
    limit: int,
) -> HybridMatches:
    if not lexical_query.strip():
        return HybridMatches(chunks=[], files=[], symbols=[])

    sql = text(
        """
        WITH lexical_query AS (
            SELECT websearch_to_tsquery('simple', :query) AS q
        )
        SELECT
            f.source_id,
            f.doctwin_id,
            f.snapshot_id,
            f.path,
            LEAST(
                0.9,
                0.4 + ts_rank_cd(
                    setweight(to_tsvector('simple', COALESCE(f.path, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(f.framework_role, '')), 'B'),
                    lexical_query.q
                )
            ) AS score
        FROM indexed_files f
        CROSS JOIN lexical_query
        WHERE f.doctwin_id = :doctwin_id
          AND lexical_query.q <> ''::tsquery
          AND (
            setweight(to_tsvector('simple', COALESCE(f.path, '')), 'A') ||
            setweight(to_tsvector('simple', COALESCE(f.framework_role, '')), 'B')
          ) @@ lexical_query.q
        ORDER BY score DESC, f.path
        LIMIT :limit
        """
    )

    try:
        result = await db.execute(
            sql,
            {"query": lexical_query, "doctwin_id": doctwin_id, "limit": limit},
        )
        rows = result.fetchall()
    except Exception as exc:
        logger.warning("file_candidate_search_failed", doctwin_id=doctwin_id, error=str(exc))
        await db.rollback()
        return HybridMatches(chunks=[], files=[], symbols=[])

    if not rows:
        rows = await _fetch_file_candidates_by_substring(
            db=db,
            doctwin_id=doctwin_id,
            lexical_query=lexical_query,
            limit=limit,
        )
        if not rows:
            return HybridMatches(chunks=[], files=[], symbols=[])

    file_matches = [
        EvidenceFileRef(
            path=row.path,
            doctwin_id=str(row.doctwin_id),
            source_id=str(row.source_id),
            snapshot_id=row.snapshot_id,
            reasons=["file"],
        )
        for row in rows
    ]
    chunks = await _fetch_chunks_for_paths(
        db=db,
        doctwin_id=doctwin_id,
        path_entries=[(row.path, float(row.score), "file") for row in rows],
        allow_code_snippets=allow_code_snippets,
        limit_per_path=2,
    )
    return HybridMatches(chunks=chunks, files=file_matches, symbols=[])


async def fetch_symbol_candidates(
    *,
    db: AsyncSession,
    doctwin_id: str,
    lexical_query: str,
    allow_code_snippets: bool,
    limit: int,
) -> HybridMatches:
    if not lexical_query.strip():
        return HybridMatches(chunks=[], files=[], symbols=[])

    sql = text(
        """
        WITH lexical_query AS (
            SELECT websearch_to_tsquery('simple', :query) AS q
        )
        SELECT
            s.source_id,
            s.doctwin_id,
            s.snapshot_id,
            s.path,
            s.symbol_name,
            s.qualified_name,
            s.symbol_kind,
            s.start_line,
            s.end_line,
            LEAST(
                0.95,
                0.45 + ts_rank_cd(
                    setweight(to_tsvector('simple', COALESCE(s.symbol_name, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(s.qualified_name, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(s.signature, '')), 'B'),
                    lexical_query.q
                )
            ) AS score
        FROM indexed_symbols s
        CROSS JOIN lexical_query
        WHERE s.doctwin_id = :doctwin_id
          AND lexical_query.q <> ''::tsquery
          AND (
            setweight(to_tsvector('simple', COALESCE(s.symbol_name, '')), 'A') ||
            setweight(to_tsvector('simple', COALESCE(s.qualified_name, '')), 'A') ||
            setweight(to_tsvector('simple', COALESCE(s.signature, '')), 'B')
          ) @@ lexical_query.q
        ORDER BY score DESC, s.path, s.start_line
        LIMIT :limit
        """
    )

    try:
        result = await db.execute(
            sql,
            {"query": lexical_query, "doctwin_id": doctwin_id, "limit": limit},
        )
        rows = result.fetchall()
    except Exception as exc:
        logger.warning("symbol_candidate_search_failed", doctwin_id=doctwin_id, error=str(exc))
        await db.rollback()
        return HybridMatches(chunks=[], files=[], symbols=[])

    if not rows:
        rows = await _fetch_symbol_candidates_by_substring(
            db=db,
            doctwin_id=doctwin_id,
            lexical_query=lexical_query,
            limit=limit,
        )
        if not rows:
            return HybridMatches(chunks=[], files=[], symbols=[])

    symbol_matches = [
        EvidenceSymbolRef(
            symbol_name=row.symbol_name,
            qualified_name=row.qualified_name,
            symbol_kind=str(row.symbol_kind.value if hasattr(row.symbol_kind, "value") else row.symbol_kind),
            path=row.path,
            doctwin_id=str(row.doctwin_id),
            source_id=str(row.source_id),
            snapshot_id=row.snapshot_id,
            reasons=["symbol"],
        )
        for row in rows
    ]

    chunks = await _fetch_chunks_for_symbol_rows(
        db=db,
        doctwin_id=doctwin_id,
        symbol_rows=rows,
        allow_code_snippets=allow_code_snippets,
    )
    return HybridMatches(chunks=chunks, files=[], symbols=symbol_matches)


async def _fetch_chunks_for_paths(
    *,
    db: AsyncSession,
    doctwin_id: str,
    path_entries: list[tuple[str, float, str]],
    allow_code_snippets: bool,
    limit_per_path: int,
) -> list[dict[str, Any]]:
    if not path_entries:
        return []

    unique_paths = [path for path, _score, _reason in path_entries]
    score_map = {path: score for path, score, _reason in path_entries}
    reason_map = {path: reason for path, _score, reason in path_entries}
    code_filter = "" if allow_code_snippets else "AND c.chunk_type != 'code_snippet'"
    sql = text(
        f"""
        SELECT
            c.id,
            c.content,
            c.chunk_type,
            c.source_ref
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE s.doctwin_id = :doctwin_id
          AND s.status = 'ready'
          AND c.source_ref = ANY(:paths)
          {code_filter}
        ORDER BY
          CASE c.chunk_type
            WHEN 'code_snippet' THEN 0
            WHEN 'module_description' THEN 1
            WHEN 'feature_description' THEN 2
            WHEN 'documentation' THEN 3
            ELSE 4
          END,
          c.start_line NULLS LAST
        """
    )
    try:
        result = await db.execute(sql, {"doctwin_id": doctwin_id, "paths": unique_paths})
    except Exception as exc:
        logger.warning("file_chunk_fetch_failed", doctwin_id=doctwin_id, error=str(exc))
        await db.rollback()
        return []

    grouped: dict[str, list[Any]] = {}
    for row in result.fetchall():
        grouped.setdefault(str(row.source_ref), []).append(row)

    chunks: list[dict[str, Any]] = []
    for path in unique_paths:
        for row in grouped.get(path, [])[:limit_per_path]:
            chunks.append(
                {
                    "chunk_id": str(row.id),
                    "content": row.content,
                    "chunk_type": row.chunk_type,
                    "source_ref": row.source_ref,
                    "score": score_map.get(path, 0.4),
                    "match_reasons": [reason_map.get(path, "file")],
                }
            )
    return chunks


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
        if token in _DOMAIN_PRIORITY_TOKENS:
            return (1, -len(token))
        if re.search(r"week\d+", token):
            return (2, -len(token))
        if len(token) >= 10:
            return (3, -len(token))
        return (4, 0)

    return sorted(ordered, key=priority)


async def _fetch_file_candidates_by_substring(
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
            f"(lower(f.path) LIKE :{key} OR lower(coalesce(f.framework_role, '')) LIKE :{key})"
        )
    sql = text(
        f"""
        SELECT
            f.source_id,
            f.doctwin_id,
            f.snapshot_id,
            f.path,
            LEAST(
                0.88,
                0.34 + (
                    {' + '.join(f"CASE WHEN {clause} THEN 0.12 ELSE 0 END" for clause in clauses)}
                )
            ) AS score
        FROM indexed_files f
        WHERE f.doctwin_id = :doctwin_id
          AND ({' OR '.join(clauses)})
        ORDER BY score DESC, f.path
        LIMIT :limit
        """
    )
    try:
        result = await db.execute(sql, params)
    except Exception as exc:
        logger.warning("file_candidate_substring_search_failed", doctwin_id=doctwin_id, error=str(exc))
        await db.rollback()
        return []
    return result.fetchall()


async def _fetch_chunk_candidates_by_substring(
    *,
    db: AsyncSession,
    doctwin_id: str,
    lexical_query: str,
    allow_code_snippets: bool,
    limit: int,
) -> list[Any]:
    tokens = _tokenise_lexical_query(lexical_query)[:16]
    if not tokens:
        return []

    code_filter = "" if allow_code_snippets else "AND c.chunk_type != 'code_snippet'"
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
          AND coalesce(c.source_ref, '') NOT LIKE '__memory__/%'
          {code_filter}
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


async def _fetch_symbol_candidates_by_substring(
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
            " OR ".join(
                [
                    f"lower(s.symbol_name) LIKE :{key}",
                    f"lower(coalesce(s.qualified_name, '')) LIKE :{key}",
                    f"lower(s.path) LIKE :{key}",
                    f"lower(coalesce(s.signature, '')) LIKE :{key}",
                ]
            )
        )
    sql = text(
        f"""
        SELECT
            s.source_id,
            s.doctwin_id,
            s.snapshot_id,
            s.path,
            s.symbol_name,
            s.qualified_name,
            s.symbol_kind,
            s.start_line,
            s.end_line,
            LEAST(
                0.92,
                0.38 + (
                    {' + '.join(f"CASE WHEN ({clause}) THEN 0.1 ELSE 0 END" for clause in clauses)}
                )
            ) AS score
        FROM indexed_symbols s
        WHERE s.doctwin_id = :doctwin_id
          AND ({' OR '.join(f'({clause})' for clause in clauses)})
        ORDER BY score DESC, s.path, s.start_line
        LIMIT :limit
        """
    )
    try:
        result = await db.execute(sql, params)
    except Exception as exc:
        logger.warning("symbol_candidate_substring_search_failed", doctwin_id=doctwin_id, error=str(exc))
        await db.rollback()
        return []
    return result.fetchall()


async def _fetch_chunks_for_symbol_rows(
    *,
    db: AsyncSession,
    doctwin_id: str,
    symbol_rows: list[Any],
    allow_code_snippets: bool,
) -> list[dict[str, Any]]:
    if not symbol_rows:
        return []

    code_filter = "" if allow_code_snippets else "AND c.chunk_type != 'code_snippet'"
    chunks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in symbol_rows:
        sql = text(
            f"""
            SELECT
                c.id,
                c.content,
                c.chunk_type,
                c.source_ref,
                c.start_line,
                c.end_line
            FROM chunks c
            JOIN sources s ON s.id = c.source_id
            WHERE s.doctwin_id = :doctwin_id
              AND s.status = 'ready'
              AND c.source_ref = :path
              AND (
                    c.start_line IS NULL
                 OR c.end_line IS NULL
                 OR (c.start_line <= :end_line AND c.end_line >= :start_line)
              )
              {code_filter}
            ORDER BY
              CASE
                WHEN c.start_line IS NOT NULL AND c.end_line IS NOT NULL
                 AND c.start_line <= :end_line AND c.end_line >= :start_line THEN 0
                ELSE 1
              END,
              CASE c.chunk_type
                WHEN 'code_snippet' THEN 0
                WHEN 'module_description' THEN 1
                WHEN 'feature_description' THEN 2
                WHEN 'documentation' THEN 3
                ELSE 4
              END,
              c.start_line NULLS LAST
            LIMIT 2
            """
        )
        try:
            result = await db.execute(
                sql,
                {
                    "doctwin_id": doctwin_id,
                    "path": row.path,
                    "start_line": row.start_line,
                    "end_line": row.end_line,
                },
            )
        except Exception as exc:
            logger.warning("symbol_chunk_fetch_failed", doctwin_id=doctwin_id, path=row.path, error=str(exc))
            await db.rollback()
            continue

        for chunk_row in result.fetchall():
            chunk_id = str(chunk_row.id)
            if chunk_id in seen_ids:
                continue
            seen_ids.add(chunk_id)
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "content": chunk_row.content,
                    "chunk_type": chunk_row.chunk_type,
                    "source_ref": chunk_row.source_ref,
                    "score": float(row.score),
                    "match_reasons": [f"symbol:{row.qualified_name}"],
                }
            )

    return chunks
