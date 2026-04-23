"""
Evidence hydration for retrieved chunks (simplified).

Docbase answers from stored chunk text and metadata. Optional refresh from
Google Drive or local file paths is kept for strict file-backed chunks; there
is no source mirror or Git provider refetch.
"""

from __future__ import annotations

import re
import uuid
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.google_drive.connector import _fetch_file_content as drive_fetch_file_content
from app.connectors.google_drive.connector import _make_client as drive_make_client
from app.connectors.pdf.connector import PDFConnector
from app.core.logging import get_logger
from app.domains.integrations.service import resolve_access_token
from app.domains.knowledge.evidence import build_segment_id, hash_text
from app.domains.knowledge.extractors import extract_chunks
from app.models.chunk import Chunk, ChunkLineage, ChunkType
from app.models.source import Source, SourceIndexMode, SourceType

logger = get_logger(__name__)

_MAX_HYDRATION_DURATION_MS = 300.0
_MAX_HYDRATED_CHUNKS = 8
_DRIVE_PATH_ID_RE = re.compile(r"\[([a-zA-Z0-9_\-]{10,100})\]\s*$")


async def hydrate_retrieved_chunks(
    chunks: list[dict[str, Any]],
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Enrich chunk dicts with DB metadata; optionally refresh strict file-backed text."""
    started_at = perf_counter()
    chunk_ids = [chunk.get("chunk_id") for chunk in chunks if chunk.get("chunk_id")]
    if not chunk_ids:
        return chunks

    result = await db.execute(
        select(Chunk, Source)
        .join(Source, Source.id == Chunk.source_id)
        .where(Chunk.id.in_([uuid.UUID(str(chunk_id)) for chunk_id in chunk_ids]))
    )
    rows = result.fetchall()
    by_id = {str(row.Chunk.id): (row.Chunk, row.Source) for row in rows}

    hydrated_candidates_cache: dict[
        tuple[str, str, str | None, bool],
        dict[tuple[str, str | None], dict[str, Any]],
    ] = {}

    hydrated: list[dict[str, Any]] = []
    hydrated_count = 0
    budget_exhausted = False
    for chunk in chunks:
        elapsed_ms = (perf_counter() - started_at) * 1000
        if elapsed_ms >= _MAX_HYDRATION_DURATION_MS or hydrated_count >= _MAX_HYDRATED_CHUNKS:
            budget_exhausted = True
            hydrated.append(chunk)
            continue

        chunk_id = str(chunk.get("chunk_id"))
        match = by_id.get(chunk_id)
        if not match:
            hydrated.append(chunk)
            continue

        chunk_row, source = match
        hydrated_chunk = dict(chunk)
        hydrated_chunk["source_id"] = str(getattr(source, "id", chunk.get("source_id")))
        doctwin_id = getattr(source, "doctwin_id", chunk.get("doctwin_id"))
        hydrated_chunk["doctwin_id"] = str(doctwin_id) if doctwin_id is not None else None
        hydrated_chunk["snapshot_id"] = chunk_row.snapshot_id
        hydrated_chunk["segment_id"] = chunk_row.segment_id
        hydrated_chunk["start_line"] = chunk_row.start_line
        hydrated_chunk["end_line"] = chunk_row.end_line
        hydrated_chunk["content_hash"] = chunk_row.content_hash
        hydrated_chunk["lineage"] = (
            chunk_row.lineage.value
            if hasattr(chunk_row.lineage, "value")
            else str(chunk_row.lineage)
        )
        if (
            source.index_mode != SourceIndexMode.strict
            or chunk_row.lineage
            not in {ChunkLineage.file_backed, ChunkLineage.connector_segment}
            or not chunk_row.source_ref
        ):
            hydrated.append(hydrated_chunk)
            continue

        refreshed = await _hydrate_deterministic_chunk(
            hydrated_chunk,
            chunk_row,
            source,
            db,
            hydrated_candidates_cache,
        )
        hydrated.append(refreshed)
        if refreshed.get("hydrated"):
            hydrated_count += 1

    logger.info(
        "retrieval_hydration_complete",
        chunk_count=len(chunks),
        hydrated_count=hydrated_count,
        budget_exhausted=budget_exhausted,
        duration_ms=round((perf_counter() - started_at) * 1000, 2),
    )
    return hydrated


async def _hydrate_deterministic_chunk(
    chunk: dict[str, Any],
    chunk_row: Chunk,
    source: Source,
    db: AsyncSession,
    hydrated_candidates_cache: dict[
        tuple[str, str, str | None, bool],
        dict[tuple[str, str | None], dict[str, Any]],
    ],
) -> dict[str, Any]:
    if chunk_row.chunk_type == ChunkType.implementation_fact:
        return chunk

    path = chunk_row.source_ref or ""
    allow_code_snippets = bool(
        ((source.index_health or {}).get("policy") or {}).get("allow_code_snippets")
    )
    cache_key = (str(source.id), path, chunk_row.snapshot_id, allow_code_snippets)

    if cache_key not in hydrated_candidates_cache:
        full_text = await _load_canonical_source_text(source, path, chunk_row.snapshot_id, db)
        if not full_text:
            hydrated_candidates_cache[cache_key] = {}
        else:
            hydrated_candidates_cache[cache_key] = _build_canonical_chunk_map(
                path=path,
                content=full_text,
                allow_code_snippets=allow_code_snippets,
            )

    candidate_map = hydrated_candidates_cache[cache_key]
    candidate = candidate_map.get((chunk_row.chunk_type.value, chunk_row.segment_id))
    if candidate is None:
        return chunk

    hydrated_content = candidate["content"]
    expected_hash = chunk_row.content_hash
    if expected_hash and hash_text(hydrated_content) != expected_hash:
        logger.warning(
            "chunk_hydration_hash_mismatch",
            chunk_id=str(chunk_row.id),
            source_id=str(source.id),
            snapshot_id=chunk_row.snapshot_id,
        )
        return chunk

    updated = dict(chunk)
    updated["content"] = hydrated_content
    updated["snapshot_id"] = chunk_row.snapshot_id
    updated["hydrated"] = True
    return updated


def _build_canonical_chunk_map(
    *,
    path: str,
    content: str,
    allow_code_snippets: bool,
) -> dict[tuple[str, str | None], dict[str, Any]]:
    candidates = extract_chunks(path=path, content=content, allow_code_snippets=allow_code_snippets)
    chunk_map: dict[tuple[str, str | None], dict[str, Any]] = {}
    for candidate in candidates:
        segment_id = candidate.get("segment_id") or build_segment_id(
            path,
            candidate["chunk_type"],
            candidate.get("start_line"),
            candidate.get("end_line"),
            fallback_part=(candidate.get("chunk_metadata") or {}).get("part"),
        )
        chunk_map[(str(candidate["chunk_type"]), segment_id)] = candidate
    return chunk_map


async def _load_canonical_source_text(
    source: Source,
    path: str,
    snapshot_id: str | None,
    db: AsyncSession,
) -> str | None:
    del snapshot_id  # reserved for snapshot-bound canonical reads
    if source.source_type == SourceType.manual:
        return str(source.connection_config.get("content") or "")
    if source.source_type == SourceType.markdown:
        if source.connection_config.get("content"):
            return str(source.connection_config.get("content") or "")
        file_path = source.connection_config.get("file_path")
        if not file_path:
            return None
        try:
            with open(file_path, encoding="utf-8") as handle:
                return handle.read().replace("\x00", "")
        except OSError:
            return None
    if source.source_type == SourceType.pdf:
        return await _hydrate_pdf_text(source)
    if source.source_type == SourceType.google_drive:
        return await _hydrate_google_drive_file(source, path, db)
    return None


async def _resolve_source_access_token(source: Source, db: AsyncSession) -> str | None:
    if source.connected_account_id is None:
        return None
    try:
        return await resolve_access_token(str(source.connected_account_id), db)
    except Exception as exc:
        logger.warning(
            "chunk_hydration_token_resolve_failed",
            source_id=str(source.id),
            error=str(exc),
        )
        return None


async def _hydrate_pdf_text(source: Source) -> str | None:
    file_path = source.connection_config.get("file_path")
    if not file_path:
        return None
    connector = PDFConnector()
    result = await connector.fetch(
        {
            "file_path": file_path,
            "source_id": str(source.id),
        }
    )
    if not result.files:
        return None
    return result.files[0].content.replace("\x00", "")


async def _hydrate_google_drive_file(
    source: Source,
    path: str,
    db: AsyncSession,
) -> str | None:
    token = await _resolve_source_access_token(source, db)
    if not token:
        return None

    file_id = _extract_drive_file_id(path)
    if not file_id:
        return None

    async with drive_make_client(token) as client:
        try:
            resp = await client.get(
                "https://www.googleapis.com/drive/v3/files/" + file_id,
                params={"fields": "id,name,mimeType,size,modifiedTime"},
            )
            resp.raise_for_status()
            item = resp.json()
        except Exception as exc:
            logger.warning(
                "chunk_hydration_drive_metadata_failed",
                source_id=str(source.id),
                file_id=file_id,
                error=str(exc),
            )
            return None

        content, _err = await drive_fetch_file_content(client, item)
        return content


def _extract_drive_file_id(path: str) -> str | None:
    match = _DRIVE_PATH_ID_RE.search(path)
    if not match:
        return None
    return match.group(1)
