"""
Knowledge processing pipeline.

Takes raw files from connectors, applies policy checks,
then extracts safe knowledge representations (chunks).

What this domain does:
- Checks each file against policy (always-blocked patterns, secret scanning)
- Classifies file type and determines appropriate extraction strategy
- Extracts safe knowledge: structure, summaries, docs, feature descriptions
- Chunks content appropriately for retrieval
- Generates embeddings for each chunk
- Stores resulting Chunk records

What this domain does NOT do:
- Store raw source content in public/API-facing tables
- Make LLM calls for answer generation (that's the answering domain)
- Apply retrieval logic (that's the retrieval domain)
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import ConnectorResult, RawFile
from app.core.logging import get_logger
from app.domains.embedding.embedder import EmbeddingProfile, embed_batch_with_failover
from app.domains.knowledge.evidence import (
    build_index_health,
    build_root_hash,
    build_segment_id,
    classify_chunk_lineage,
    hash_text,
    is_strict_chunk_ready,
    resolve_snapshot_id,
)
from app.domains.knowledge.extractors import extract_chunks
from app.domains.policy.rules import is_file_blocked, scan_content_for_secrets
from app.models.chunk import Chunk, ChunkLineage, ChunkType
from app.models.source import Source, SourceIndexMode

logger = get_logger(__name__)

_STRUCTURE_SCHEMA_VERSION = 2
_MAX_STRUCTURE_DEPTH = 4
_MAX_STRUCTURE_GROUPS = 50


async def process_connector_result(
    result: ConnectorResult,
    doctwin_id: str,
    allow_code_snippets: bool,
    db: AsyncSession,
    embedding_profiles: list[EmbeddingProfile] | None = None,
) -> dict:
    """
    Main entry point for the knowledge processing pipeline.

    Called by ingestion jobs after a connector fetch completes.

    Full sync  (result.is_full_sync=True):
      Caller must have already cleared all chunks for the source.
      Processes every file in result.files.

    Delta sync (result.is_full_sync=False):
      1. Deletes chunks for all paths in result.deleted_paths.
      2. Deletes chunks for paths that are being re-added/changed (to avoid duplicates).
      3. Processes only the changed/added files in result.files.

    Steps (per file):
    1. Policy check — always-blocked file patterns
    2. Secret scan — skip files with detected secrets
    3. Extract chunks via type-specific extractors
    4. Batch embed
    5. Write Chunk rows to the database

    Returns a stats dict describing what was processed.
    """
    source = await db.get(Source, uuid.UUID(result.source_id))
    if source is None:
        raise ValueError(f"Source {result.source_id} not found for knowledge pipeline")

    stats = {
        "files_received": len(result.files),
        "files_blocked": 0,
        "files_secret_flagged": 0,
        "files_processed": 0,
        "chunks_created": 0,
        "chunks_embedded": 0,
        "is_full_sync": result.is_full_sync,
        "paths_deleted": 0,
        "embedding_provider": None,
        "embedding_model": None,
        "embedding_dimensions": None,
        "strict_chunk_total": 0,
        "strict_chunk_ready": 0,
        "total_chunks_after_sync": 0,
        "snapshot_id": None,
        "snapshot_root_hash": None,
        "index_mode": source.index_mode.value,
    }
    cleared_paths: list[str] = []

    # ── Delta mode: prune stale chunks before processing new content ──────────
    paths_to_delete: set[str] = set()
    if not result.is_full_sync:
        # Paths that were deleted upstream
        paths_to_delete = set(result.deleted_paths)
        # Paths being re-processed (to avoid duplicate chunks for the same file)
        paths_to_delete.update(f.path for f in result.files)

        if paths_to_delete:
            deleted = await clear_chunks_for_paths(
                result.source_id, list(paths_to_delete), db
            )
            stats["paths_deleted"] = deleted
            logger.info(
                "ingestion_delta_pruned",
                source_id=result.source_id,
                doctwin_id=doctwin_id,
                deleted=deleted,
            )

    # Skip processing when a delta sync had only deletions
    if not result.files:
        snapshot_id, snapshot_root_hash, index_mode = await _update_source_index_state(
            source=source,
            result=result,
            stats=stats,
            allow_code_snippets=allow_code_snippets,
            db=db,
        )
        stats["snapshot_id"] = snapshot_id
        stats["snapshot_root_hash"] = snapshot_root_hash
        stats["index_mode"] = index_mode
        await _update_structure_index(
            source_id=result.source_id,
            is_full_sync=result.is_full_sync,
            added_paths=cleared_paths,
            deleted_paths=list(paths_to_delete),
            snapshot_id=snapshot_id,
            snapshot_root_hash=snapshot_root_hash,
            db=db,
        )
        logger.info(
            "ingestion_pipeline_complete",
            doctwin_id=doctwin_id,
            stats=stats,
        )
        return stats

    # Process files: policy-check, extract, embed
    pending_chunks: list[dict] = []

    # Compute snapshot identity from file content hashes
    preview_snapshot_root_hash = _compute_snapshot_root_hash_from_files(result.files)
    preview_snapshot_id = resolve_snapshot_id(
        result.fetch_metadata,
        result.head_sha,
        result.next_page_token,
        preview_snapshot_root_hash,
    )

    for raw_file in result.files:
        # Step 1: Policy check — always-blocked files
        policy_decision = is_file_blocked(raw_file.path)
        if not policy_decision.allowed:
            logger.info(
                "ingestion_file_blocked",
                path=raw_file.path,
                reason=policy_decision.reason,
                doctwin_id=doctwin_id,
            )
            stats["files_blocked"] += 1
            continue

        # Step 2: Secret scan — skip files with detected secrets
        secret_flags = scan_content_for_secrets(raw_file.content)
        if secret_flags:
            logger.warning(
                "ingestion_secret_flagged",
                path=raw_file.path,
                flag_count=len(secret_flags),
                doctwin_id=doctwin_id,
            )
            stats["files_secret_flagged"] += 1
            continue

        safe_path = _sanitize_text(raw_file.path)
        if safe_path:
            cleared_paths.append(safe_path)

        # Sanitize content before storage/extraction
        safe_content = _sanitize_text(raw_file.content)
        file_content_hash = hash_text(safe_content)

        # Step 3: Extract chunks
        try:
            extracted = extract_chunks(
                path=safe_path,
                content=safe_content,
            )
        except Exception as exc:
            logger.warning(
                "ingestion_extraction_failed",
                path=safe_path,
                error=str(exc),
                doctwin_id=doctwin_id,
            )
            continue

        for chunk in extracted:
            chunk["source_id"] = result.source_id
            chunk_type = ChunkType(chunk["chunk_type"])
            lineage = classify_chunk_lineage(chunk_type, source.source_type)
            start_line = chunk.get("start_line")
            end_line = chunk.get("end_line")
            chunk_metadata = dict(chunk.get("chunk_metadata", {}))
            chunk_metadata.setdefault("file_content_hash", file_content_hash)
            origin_metadata = _sanitize_origin_metadata(raw_file.metadata)
            if origin_metadata:
                chunk_metadata.setdefault("origin", origin_metadata)
            chunk["lineage"] = lineage.value
            chunk["chunk_metadata"] = chunk_metadata
            chunk["segment_id"] = chunk.get("segment_id") or build_segment_id(
                safe_path,
                chunk_type,
                start_line,
                end_line,
                fallback_part=chunk_metadata.get("part"),
            )
            pending_chunks.append(chunk)

        stats["files_processed"] += 1

    if not pending_chunks:
        snapshot_id, snapshot_root_hash, index_mode = await _update_source_index_state(
            source=source,
            result=result,
            stats=stats,
            allow_code_snippets=allow_code_snippets,
            forced_snapshot_id=preview_snapshot_id,
            forced_snapshot_root_hash=preview_snapshot_root_hash,
            db=db,
        )
        stats["snapshot_id"] = snapshot_id
        stats["snapshot_root_hash"] = snapshot_root_hash
        stats["index_mode"] = index_mode
        await _update_structure_index(
            source_id=result.source_id,
            is_full_sync=result.is_full_sync,
            added_paths=cleared_paths,
            deleted_paths=list(paths_to_delete),
            snapshot_id=snapshot_id,
            snapshot_root_hash=snapshot_root_hash,
            db=db,
        )
        logger.info(
            "ingestion_pipeline_complete",
            doctwin_id=doctwin_id,
            stats=stats,
        )
        return stats

    embeddings: list[list[float]] = []
    if pending_chunks:
        # Step 4: Batch embed all chunks
        texts = [c["content"] for c in pending_chunks]
        try:
            batch_result = await embed_batch_with_failover(
                texts,
                task="document",
                profiles=embedding_profiles,
                db=db,
            )
            embeddings = batch_result.embeddings
            stats["chunks_embedded"] = len(embeddings)
            stats["embedding_provider"] = batch_result.profile.provider
            stats["embedding_model"] = batch_result.profile.model
            stats["embedding_dimensions"] = batch_result.profile.dimensions
        except Exception as exc:
            logger.error(
                "ingestion_embedding_failed",
                error=str(exc),
                doctwin_id=doctwin_id,
                chunk_count=len(pending_chunks),
            )
            raise

    # Step 5: Write Chunk rows
    chunk_rows = []
    for i, chunk_dict in enumerate(pending_chunks):
        embedding = embeddings[i] if i < len(embeddings) else None
        try:
            chunk_type = ChunkType(chunk_dict["chunk_type"])
        except ValueError:
            logger.warning(
                "ingestion_unknown_chunk_type",
                chunk_type=chunk_dict.get("chunk_type"),
                path=chunk_dict.get("source_ref"),
            )
            continue

        clean_content = _sanitize_text(chunk_dict["content"])
        lineage = ChunkLineage(chunk_dict["lineage"])
        row = Chunk(
            id=uuid.uuid4(),
            source_id=uuid.UUID(chunk_dict["source_id"]),
            chunk_type=chunk_type,
            lineage=lineage,
            content=clean_content,
            embedding=embedding,
            source_ref=_sanitize_text(chunk_dict.get("source_ref") or ""),
            snapshot_id=preview_snapshot_id,
            segment_id=chunk_dict.get("segment_id"),
            start_line=chunk_dict.get("start_line"),
            end_line=chunk_dict.get("end_line"),
            content_hash=hash_text(clean_content),
            token_count=_estimate_tokens(clean_content),
            chunk_metadata=chunk_dict.get("chunk_metadata", {}),
        )
        chunk_rows.append(row)

    if chunk_rows:
        db.add_all(chunk_rows)
        await db.flush()
        stats["chunks_created"] = len(chunk_rows)

    snapshot_id, snapshot_root_hash, index_mode = await _update_source_index_state(
        source=source,
        result=result,
        stats=stats,
        allow_code_snippets=allow_code_snippets,
        forced_snapshot_id=preview_snapshot_id,
        forced_snapshot_root_hash=preview_snapshot_root_hash,
        db=db,
    )
    stats["snapshot_id"] = snapshot_id
    stats["snapshot_root_hash"] = snapshot_root_hash
    stats["index_mode"] = index_mode

    if snapshot_id:
        for row in chunk_rows:
            row.snapshot_id = snapshot_id
        await db.flush()

    await _update_structure_index(
        source_id=result.source_id,
        is_full_sync=result.is_full_sync,
        added_paths=cleared_paths,
        deleted_paths=list(paths_to_delete),
        snapshot_id=snapshot_id,
        snapshot_root_hash=snapshot_root_hash,
        db=db,
    )

    logger.info(
        "ingestion_pipeline_complete",
        doctwin_id=doctwin_id,
        stats=stats,
    )
    return stats


async def clear_chunks_for_source(source_id: str, db: AsyncSession) -> int:
    """
    Delete ALL existing chunks for a source before a full re-ingestion.

    Called by the ingestion job when doing a full sync to ensure stale chunks
    do not remain after a source is updated.
    """
    result = await db.execute(
        delete(Chunk).where(Chunk.source_id == uuid.UUID(source_id))
    )
    return result.rowcount


async def clear_chunks_for_paths(
    source_id: str, paths: list[str], db: AsyncSession
) -> int:
    """
    Delete chunks for specific file paths within a source.

    Called during delta sync to remove stale chunks for files that were
    deleted, renamed, or modified upstream before re-processing them.

    Matches on source_ref which connectors populate with the file path.
    """
    if not paths:
        return 0
    result = await db.execute(
        delete(Chunk).where(
            Chunk.source_id == uuid.UUID(source_id),
            Chunk.source_ref.in_(paths),
        )
    )
    return result.rowcount


def _sanitize_text(text: str) -> str:
    """
    Strip characters that PostgreSQL TEXT/VARCHAR columns cannot store.

    Null bytes (U+0000 / \\x00) are valid UTF-8 but rejected by Postgres.
    They appear in files that slip through the binary-extension filter
    (e.g. compiled outputs, null-padded configs, certain Jupyter notebooks).

    This is the final safety net before any string reaches the database.
    Connectors should strip null bytes earlier, but this ensures the pipeline
    never fails with CharacterNotInRepertoireError regardless of connector behaviour.
    """
    return text.replace("\x00", "")


def _sanitize_origin_metadata(raw_metadata: dict | None) -> dict:
    """
    Persist only safe connector metadata needed for strict hydration and audits.
    """
    if not raw_metadata:
        return {}

    allowed = {
        "drive_file_id",
        "name",
        "modified_time",
        "page_count",
        "source_path",
        "revision_id",
        "title",
        "source_type",
    }
    sanitized: dict[str, str | int] = {}
    for key, value in raw_metadata.items():
        if key not in allowed or value is None:
            continue
        if isinstance(value, (str, int)):
            sanitized[key] = value
        else:
            sanitized[key] = str(value)
    return sanitized


def _estimate_tokens(text: str) -> int:
    """
    Rough token count estimate (4 chars ≈ 1 token for English text).

    Used for context window management in the answering domain.
    Not a substitute for a proper tokenizer, but good enough for
    budget checks without adding a heavy dependency.
    """
    return max(1, len(text) // 4)


def _select_meaningful_dirs(file_paths: list[str]) -> dict[str, list[str]]:
    """
    Group policy-cleared file paths by their meaningful parent directory.

    Rules:
    - Root-level files go under `_root`
    - Nested files group by their immediate parent directory
    - Parent depth is capped at `_MAX_STRUCTURE_DEPTH`
    - Result is sorted by depth ASC then file_count DESC and capped
    """
    grouped: dict[str, list[str]] = defaultdict(list)

    for raw_path in sorted({p.strip("/") for p in file_paths if p and p.strip("/")}):
        pure_path = PurePosixPath(raw_path)
        parts = pure_path.parts
        if len(parts) <= 1:
            grouped["_root"].append(raw_path)
            continue

        parent_parts = list(parts[:-1])[:_MAX_STRUCTURE_DEPTH]
        parent = "/".join(parent_parts) if parent_parts else "_root"
        grouped[parent].append(raw_path)

    ordered = sorted(
        grouped.items(),
        key=lambda item: (_dir_depth(item[0]), -len(item[1]), item[0]),
    )[:_MAX_STRUCTURE_GROUPS]

    return {
        dir_path: sorted(paths)
        for dir_path, paths in ordered
    }


def _build_structure_index(
    cleared_paths: list[str],
    snapshot_id: str | None = None,
    snapshot_root_hash: str | None = None,
    is_partial: bool = False,
) -> dict:
    """
    Build a deterministic structure inventory from policy-cleared file paths.
    """
    unique_paths = sorted({p for p in cleared_paths if p})
    return {
        "schema_version": _STRUCTURE_SCHEMA_VERSION,
        "meaningful_dirs": _select_meaningful_dirs(unique_paths),
        "total_files": len(unique_paths),
        "generated_at": datetime.now(UTC).isoformat(),
        "is_partial": is_partial,
        "snapshot_id": snapshot_id,
        "snapshot_root_hash": snapshot_root_hash,
    }


def _patch_structure_index(
    existing: dict | None,
    added: list[str],
    deleted: list[str],
    snapshot_id: str | None = None,
    snapshot_root_hash: str | None = None,
) -> dict:
    """
    Patch an existing structure inventory for a delta sync.

    Changed paths are deleted first, then policy-cleared paths are added back.
    This keeps the structure inventory consistent with chunk pruning behavior.
    """
    current_paths: set[str] = set()
    if existing:
        for paths in (existing.get("meaningful_dirs") or {}).values():
            current_paths.update(str(p) for p in paths if p)

    for path in deleted:
        if path:
            current_paths.discard(path)

    for path in added:
        if path:
            current_paths.add(path)

    return _build_structure_index(
        sorted(current_paths),
        snapshot_id=snapshot_id,
        snapshot_root_hash=snapshot_root_hash,
    )


async def _update_structure_index(
    source_id: str,
    is_full_sync: bool,
    added_paths: list[str],
    deleted_paths: list[str],
    snapshot_id: str | None,
    snapshot_root_hash: str | None,
    db: AsyncSession,
) -> None:
    """
    Persist the per-source structure inventory after a sync pass.
    """
    source = await db.get(Source, uuid.UUID(source_id))
    if source is None:
        logger.warning("structure_index_source_missing", source_id=source_id)
        return

    if is_full_sync:
        source.structure_index = _build_structure_index(
            added_paths,
            snapshot_id=snapshot_id,
            snapshot_root_hash=snapshot_root_hash,
        )
    else:
        source.structure_index = _patch_structure_index(
            source.structure_index,
            added=added_paths,
            deleted=deleted_paths,
            snapshot_id=snapshot_id,
            snapshot_root_hash=snapshot_root_hash,
        )

    await db.flush()
    logger.info(
        "structure_index_updated",
        source_id=source_id,
        total_files=(source.structure_index or {}).get("total_files", 0),
        groups=len((source.structure_index or {}).get("meaningful_dirs", {})),
        partial=(source.structure_index or {}).get("is_partial", False),
        snapshot_id=snapshot_id,
    )


def _dir_depth(dir_path: str) -> int:
    if not dir_path or dir_path == "_root":
        return 0
    return len(PurePosixPath(dir_path).parts)


def _compute_snapshot_root_hash_from_files(files: list[RawFile]) -> str | None:
    """Compute a deterministic root hash from raw file content hashes."""
    if not files:
        return None
    pairs = [(f.path, hash_text(f.content)) for f in files]
    return build_root_hash(pairs)


async def _load_current_file_fingerprints(
    source_id: str,
    db: AsyncSession,
) -> list[tuple[str, str]]:
    result = await db.execute(
        select(Chunk.source_ref, Chunk.chunk_metadata).where(
            Chunk.source_id == uuid.UUID(source_id),
            Chunk.source_ref.is_not(None),
        )
    )
    fingerprints: set[tuple[str, str]] = set()
    for row in result.fetchall():
        source_ref = str(row.source_ref or "")
        metadata = row.chunk_metadata or {}
        file_hash = metadata.get("file_content_hash")
        if source_ref and file_hash:
            fingerprints.add((source_ref, str(file_hash)))
    return sorted(fingerprints)


async def _update_source_index_state(
    source: Source,
    result: ConnectorResult,
    stats: dict,
    allow_code_snippets: bool,
    db: AsyncSession,
    forced_snapshot_id: str | None = None,
    forced_snapshot_root_hash: str | None = None,
) -> tuple[str | None, str | None, str]:
    if forced_snapshot_id is not None or forced_snapshot_root_hash is not None:
        snapshot_root_hash = forced_snapshot_root_hash
        snapshot_id = forced_snapshot_id or resolve_snapshot_id(
            result.fetch_metadata,
            result.head_sha,
            result.next_page_token,
            snapshot_root_hash,
        )
    else:
        fingerprints = await _load_current_file_fingerprints(str(source.id), db)
        snapshot_root_hash = build_root_hash(fingerprints)
        snapshot_id = resolve_snapshot_id(
            result.fetch_metadata,
            result.head_sha,
            result.next_page_token,
            snapshot_root_hash,
        )

    chunk_result = await db.execute(
        select(
            Chunk.lineage,
            Chunk.snapshot_id,
            Chunk.content_hash,
            Chunk.start_line,
            Chunk.end_line,
            Chunk.segment_id,
        ).where(Chunk.source_id == source.id)
    )
    rows = chunk_result.fetchall()
    strict_chunk_total = 0
    strict_chunk_ready = 0
    for row in rows:
        lineage = row.lineage
        if lineage in {ChunkLineage.file_backed, ChunkLineage.connector_segment}:
            strict_chunk_total += 1
            if is_strict_chunk_ready(
                lineage=lineage,
                snapshot_id=row.snapshot_id or snapshot_id,
                content_hash=row.content_hash,
                start_line=row.start_line,
                end_line=row.end_line,
                segment_id=row.segment_id,
            ):
                strict_chunk_ready += 1

    stats["strict_chunk_total"] = strict_chunk_total
    stats["strict_chunk_ready"] = strict_chunk_ready
    stats["total_chunks_after_sync"] = len(rows)

    source.snapshot_id = snapshot_id
    source.snapshot_root_hash = snapshot_root_hash

    health = build_index_health(
        source_type=source.source_type,
        snapshot_id=snapshot_id,
        snapshot_root_hash=snapshot_root_hash,
        stats=stats,
        strict_chunk_total=strict_chunk_total,
        strict_chunk_ready=strict_chunk_ready,
        total_chunks=len(rows),
        policy_signature={"allow_code_snippets": allow_code_snippets},
    )
    source.index_health = health
    source.index_mode = SourceIndexMode(health["index_mode"])
    await db.flush()

    return snapshot_id, snapshot_root_hash, source.index_mode.value
