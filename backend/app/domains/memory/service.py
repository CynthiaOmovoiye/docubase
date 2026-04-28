"""
Memory / knowledge brief orchestrator.

Post-ingestion ARQ job (`generate_memory_brief` in ``app/jobs/ingestion.py``) now
uses **incremental** brief generation by default:

  - With ``source_id``: concatenates raw chunk text from that source, merges with
    the existing ``TwinConfig.memory_brief`` via LLM, persists brief + ``memory_brief``
    embedding chunk, then marks that source ``ready``.

  - Without ``source_id`` (manual regenerate): merges each ``ready`` source
    sequentially, then promotes any ``processing`` sources on success.

``run_memory_extraction()`` remains for tests and legacy tooling: it rebuilds the
per-twin knowledge graph, generates one ``memory_brief`` via ``generate_memory_brief``,
embeds it, persists ``TwinConfig.memory_brief``, and refreshes workspace synthesis.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.redis import get_redis
from app.domains.answering.llm_provider import get_llm_provider
from app.domains.embedding.embedder import embed_batch_with_failover
from app.domains.graph.deterministic import build_deterministic_graph, merge_graph_extractions
from app.domains.graph.extractor import extract_graph_from_chunks
from app.domains.graph.service import get_graph_summary, rebuild_graph
from app.domains.knowledge.evidence import hash_text
from app.domains.memory.evidence import (
    build_workspace_synthesis_content,
    load_doctwin_memory_evidence,
)
from app.domains.memory.extractor import generate_memory_brief
from app.domains.memory.prompts import INCREMENTAL_KNOWLEDGE_BRIEF_SYSTEM
from app.models.chunk import Chunk, ChunkLineage, ChunkType
from app.models.source import Source, SourceStatus, SourceType
from app.models.twin import Twin, TwinConfig
from app.models.workspace import Workspace
from app.models.workspace_memory import WorkspaceMemoryArtifact, WorkspaceMemoryArtifactType

logger = get_logger(__name__)

_LOCK_TTL_SECONDS = 600
_LOCK_PREFIX = "memory_lock:"


def _lock_key(doctwin_id: str) -> str:
    return f"{_LOCK_PREFIX}{doctwin_id}"


def _memory_ref(doctwin_id: str) -> str:
    return f"__memory__/{doctwin_id}"


# ── Public API ────────────────────────────────────────────────────────────────


async def run_memory_extraction(
    doctwin_id: str,
    db: AsyncSession,
    commit_history: list[dict] | None = None,
    trace_id: str | None = None,
) -> dict:
    """
    Orchestrate the full memory extraction pass for a twin.

    Returns a stats dict regardless of success or failure:

      - ``doctwin_id``, ``status`` (``ready`` | ``failed`` | ``skipped``),
      - ``brief_generated``, ``workspace_synthesis_generated``,
      - optional ``reason`` when skipped, ``error`` when failed.

    ``commit_history`` is accepted for API compatibility but does not change extraction;
    only diagnostic logging uses it.

    Never raises — all exceptions are caught and reflected in the status.
    """
    redis = get_redis()
    lock_key = _lock_key(doctwin_id)

    # Acquire distributed lock (SET NX with TTL)
    acquired = await redis.set(lock_key, "1", nx=True, ex=_LOCK_TTL_SECONDS)
    if not acquired:
        logger.warning("memory_extraction_already_running", doctwin_id=doctwin_id)
        return {
            "doctwin_id": doctwin_id,
            "status": "skipped",
            "reason": "extraction already in progress",
            "brief_generated": False,
            "workspace_synthesis_generated": False,
            "error": None,
        }

    stats = {
        "doctwin_id": doctwin_id,
        "status": "failed",
        "brief_generated": False,
        "workspace_synthesis_generated": False,
        "error": None,
    }

    try:
        # Mark as generating
        await _set_brief_status(doctwin_id, "generating", db)

        # Load existing file-derived chunks for this twin (all sources)
        existing_chunks = await _load_doctwin_chunks(doctwin_id, db)
        structure_overview = await _build_structure_overview(doctwin_id, db)
        await load_doctwin_memory_evidence(
            doctwin_id,
            db,
            structure_overview=structure_overview,
        )
        # Log chunk type breakdown for diagnostics
        type_counts: dict[str, int] = defaultdict(int)
        for c in existing_chunks:
            type_counts[str(c.get("chunk_type", "unknown"))] += 1
        logger.info(
            "memory_extraction_start",
            doctwin_id=doctwin_id,
            input_chunks=len(existing_chunks),
            commit_history_count=len(commit_history) if commit_history else 0,
            structure_groups=len(structure_overview),
            chunk_type_breakdown=dict(type_counts),
        )
        if existing_chunks:
            sample = existing_chunks[0]
            logger.info(
                "memory_extraction_sample_chunk",
                doctwin_id=doctwin_id,
                chunk_type=sample.get("chunk_type"),
                source_ref=sample.get("source_ref"),
                content_len=len(sample.get("content", "")),
                content_preview=(sample.get("content") or "")[:200],
            )

        # Delete all previously generated memory chunks (idempotency)
        deleted_count = await clear_memory_chunks_for_twin(doctwin_id, db)
        if deleted_count:
            logger.info("memory_chunks_cleared", doctwin_id=doctwin_id, deleted=deleted_count)

        # ── Knowledge graph build ─────────────────────────────────────────────
        deterministic_graph = await build_deterministic_graph(doctwin_id, db)
        llm_graph = await extract_graph_from_chunks(
            existing_chunks, doctwin_id, trace_id=trace_id
        )
        graph_extraction = merge_graph_extractions(deterministic_graph, llm_graph)
        await rebuild_graph(doctwin_id, graph_extraction, db)

        # ── Memory Brief generation ───────────────────────────────────────────
        graph_context = await get_graph_summary(doctwin_id, db)
        brief_text = await generate_memory_brief(
            doctwin_id=doctwin_id,
            architecture_text=None,
            arch_chunk_dicts=[],
            risk_chunks=[],
            change_chunks=[],
            existing_chunks=existing_chunks,
            structure_overview=structure_overview,
            graph_context=graph_context or None,
            trace_id=trace_id,
        )

        if brief_text:
            # Store the brief as a chunk for RAG retrieval
            brief_chunk_dicts = [{
                "chunk_type": "memory_brief",
                "content": brief_text,
                "source_ref": _memory_ref(doctwin_id),
                "chunk_metadata": {
                    "extraction": "memory_brief",
                },
            }]
            await _embed_and_write_chunks(brief_chunk_dicts, doctwin_id, db)

            # Store the brief text on TwinConfig for unconditional injection
            await _save_memory_brief(doctwin_id, brief_text, db)
            stats["brief_generated"] = True
            stats["workspace_synthesis_generated"] = await _rebuild_workspace_synthesis_for_twin(
                doctwin_id,
                db,
            )

        await _set_brief_status(doctwin_id, "ready" if brief_text else "failed", db)
        await db.commit()
        stats["status"] = "ready" if brief_text else "failed"

        logger.info(
            "memory_extraction_complete",
            doctwin_id=doctwin_id,
            brief_generated=stats["brief_generated"],
            workspace_synthesis_generated=stats["workspace_synthesis_generated"],
            status=stats["status"],
        )

    except Exception as exc:
        stats["error"] = str(exc)
        logger.error(
            "memory_extraction_error",
            doctwin_id=doctwin_id,
            error=str(exc),
            exc_info=True,
        )
        try:
            # Roll back any partial work so the session is usable for the status update.
            # Without this, a flush error (e.g. FK violation) leaves the session poisoned
            # and the subsequent _set_brief_status flush silently fails → status stays NULL.
            await db.rollback()
            await _set_brief_status(doctwin_id, "failed", db)
            await db.commit()
        except Exception as status_exc:
            logger.warning(
                "memory_extraction_status_update_failed",
                doctwin_id=doctwin_id,
                error=str(status_exc),
            )

    finally:
        # Always release the lock
        await redis.delete(lock_key)

    return stats


async def clear_memory_chunks_for_twin(doctwin_id: str, db: AsyncSession) -> int:
    """
    Delete all LLM-generated memory chunks for a twin.
    Matches on source_ref = "__memory__/{doctwin_id}".
    Returns the count of deleted rows.
    """
    ref = _memory_ref(doctwin_id)
    # We use a JOIN-free approach: find source IDs for this twin then delete chunks by source_ref
    result = await db.execute(
        delete(Chunk).where(Chunk.source_ref == ref).returning(Chunk.id)
    )
    deleted = len(result.fetchall())
    return deleted


async def get_memory_brief(doctwin_id: str, db: AsyncSession) -> str | None:
    """Return the current Memory Brief text for a twin, or None if not generated."""
    result = await db.execute(
        select(TwinConfig.memory_brief).where(TwinConfig.doctwin_id == uuid.UUID(doctwin_id))
    )
    row = result.scalar_one_or_none()
    return row


async def get_workspace_synthesis(workspace_id: str, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(WorkspaceMemoryArtifact.content).where(
            WorkspaceMemoryArtifact.workspace_id == uuid.UUID(workspace_id),
            WorkspaceMemoryArtifact.artifact_type == WorkspaceMemoryArtifactType.workspace_synthesis,
            WorkspaceMemoryArtifact.status == "ready",
        )
    )
    return result.scalar_one_or_none()


# ── Internals ─────────────────────────────────────────────────────────────────


async def _load_doctwin_chunks(doctwin_id: str, db: AsyncSession) -> list[dict]:
    """
    Load file-derived chunks for a twin from **ready** sources only.

    Aligns memory synthesis with hybrid retrieval, which only considers chunks
    from sources the platform treats as fully indexed (`Source.status == ready`).
    Chunks from `processing`, `ingesting`, `failed`, etc. are excluded so the
    memory brief and downstream artifacts never absorb partial or non-answerable
    index state that chat would not retrieve.

    Excludes LLM-generated memory chunks (source_ref starting with __memory__).
    Returns a list of dicts with keys: chunk_type, content, source_ref, chunk_metadata.
    """
    stmt = (
        select(
            Chunk.chunk_type,
            Chunk.content,
            Chunk.source_ref,
            Chunk.chunk_metadata,
        )
        .join(Source, Chunk.source_id == Source.id)
        .where(
            Source.doctwin_id == uuid.UUID(doctwin_id),
            Source.status == SourceStatus.ready,
            Chunk.source_ref.not_like("__memory__%"),
        )
    )
    result = await db.execute(stmt)
    rows = result.fetchall()
    return [
        {
            "chunk_type": str(row.chunk_type.value if hasattr(row.chunk_type, 'value') else row.chunk_type),
            "content": row.content,
            "source_ref": row.source_ref or "",
            "chunk_metadata": row.chunk_metadata or {},
        }
        for row in rows
    ]


async def _build_structure_overview(doctwin_id: str, db: AsyncSession) -> list[dict]:
    """
    Build a sorted structure overview for the memory brief from source inventory.
    """
    inventory = await _load_structure_inventory(doctwin_id, db)
    meaningful_dirs = inventory.get("meaningful_dirs") or {}
    overview = [
        {
            "dir_path": dir_path,
            "file_paths": sorted(str(path) for path in file_paths if path),
            "file_count": len(file_paths),
        }
        for dir_path, file_paths in meaningful_dirs.items()
    ]
    overview.sort(key=lambda entry: (_dir_depth(entry["dir_path"]), entry["dir_path"]))
    return overview


async def _rebuild_workspace_synthesis_for_twin(
    doctwin_id: str,
    db: AsyncSession,
) -> bool:
    twin = (
        await db.execute(
            select(Twin).options(selectinload(Twin.config)).where(Twin.id == uuid.UUID(doctwin_id))
        )
    ).scalar_one_or_none()
    if twin is None:
        return False
    return await _rebuild_workspace_synthesis(str(twin.workspace_id), db)


async def _rebuild_workspace_synthesis(
    workspace_id: str,
    db: AsyncSession,
) -> bool:
    workspace = (
        await db.execute(
            select(Workspace)
            .options(selectinload(Workspace.twins).selectinload(Twin.config))
            .where(Workspace.id == uuid.UUID(workspace_id))
        )
    ).scalar_one_or_none()
    if workspace is None:
        return False

    artifact = (
        await db.execute(
            select(WorkspaceMemoryArtifact).where(
                WorkspaceMemoryArtifact.workspace_id == workspace.id,
                WorkspaceMemoryArtifact.artifact_type == WorkspaceMemoryArtifactType.workspace_synthesis,
            )
        )
    ).scalar_one_or_none()
    if artifact is None:
        artifact = WorkspaceMemoryArtifact(
            workspace_id=workspace.id,
            artifact_type=WorkspaceMemoryArtifactType.workspace_synthesis,
            status="generating",
            content=None,
            artifact_metadata={},
        )
        db.add(artifact)
        await db.flush()
    else:
        artifact.status = "generating"

    project_rows: list[dict] = []
    for twin in sorted(workspace.twins, key=lambda item: item.created_at):
        files_indexed = 0
        symbols_indexed = 0
        relationships_indexed = 0
        artifact_labels = await _load_memory_artifact_labels_for_twin(str(twin.id), db)
        brief_excerpt = ""
        if twin.config and twin.config.memory_brief:
            brief_excerpt = _brief_excerpt(twin.config.memory_brief)
        project_rows.append(
            {
                "doctwin_id": str(twin.id),
                "name": twin.name,
                "files_indexed": files_indexed,
                "symbols_indexed": symbols_indexed,
                "relationships_indexed": relationships_indexed,
                "artifact_labels": artifact_labels,
                "brief_excerpt": brief_excerpt,
                "languages": [],
            }
        )

    content, metadata = build_workspace_synthesis_content(
        workspace_name=workspace.name,
        project_rows=project_rows,
    )
    artifact.content = content
    artifact.artifact_metadata = metadata
    artifact.status = "ready"
    artifact.generated_at = datetime.now(UTC)
    await db.flush()
    return True


async def _load_structure_inventory(doctwin_id: str, db: AsyncSession) -> dict:
    result = await db.execute(
        select(Source.structure_index)
        .where(
            Source.doctwin_id == uuid.UUID(doctwin_id),
            Source.status.in_([SourceStatus.ready, SourceStatus.processing]),
            Source.name != "__memory__",
        )
    )
    indexes = [row.structure_index for row in result.fetchall() if row.structure_index]
    if indexes:
        merged_dirs: dict[str, set[str]] = defaultdict(set)
        for index in indexes:
            for dir_path, file_paths in (index.get("meaningful_dirs") or {}).items():
                merged_dirs[str(dir_path)].update(str(path) for path in file_paths if path)
        return {
            "meaningful_dirs": {
                dir_path: sorted(paths)
                for dir_path, paths in sorted(
                    merged_dirs.items(),
                    key=lambda item: (_dir_depth(item[0]), item[0]),
                )
            }
        }

    fallback_result = await db.execute(
        select(Chunk.source_ref)
        .join(Source, Chunk.source_id == Source.id)
        .where(
            Source.doctwin_id == uuid.UUID(doctwin_id),
            Source.status.in_([SourceStatus.ready, SourceStatus.processing]),
            Chunk.source_ref.is_not(None),
            Chunk.source_ref.not_like("__memory__%"),
        )
    )
    file_paths = [str(row.source_ref) for row in fallback_result.fetchall() if row.source_ref]
    return {"meaningful_dirs": _group_paths_by_parent(file_paths)}


async def _ensure_memory_source(
    doctwin_id: str,
    synthetic_source_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """
    Ensure a phantom Source row exists for memory-generated chunks.

    Memory chunks use a deterministic synthetic source_id derived from the
    doctwin_id (UUID v5). Because the `chunks` table has a FK to `sources`, we
    must have a real row before inserting chunks. This row is never exposed to
    the user — it's purely a FK anchor.

    Uses get() (PK lookup) + add() so it only issues one INSERT on the very
    first extraction and is a no-op on every subsequent run.
    """
    existing = await db.get(Source, synthetic_source_id)
    if existing is None:
        phantom = Source(
            id=synthetic_source_id,
            name="__memory__",
            source_type=SourceType.manual,
            status=SourceStatus.ready,
            doctwin_id=uuid.UUID(doctwin_id),
            connection_config={},
        )
        db.add(phantom)
        await db.flush()
        logger.info("memory_source_created", doctwin_id=doctwin_id, source_id=str(synthetic_source_id))


async def _embed_and_write_chunks(
    chunk_dicts: list[dict],
    doctwin_id: str,
    db: AsyncSession,
) -> list[Chunk]:
    """
    Embed a list of chunk dicts and write them as Chunk rows.

    Memory chunks are written with a synthetic source_id derived from the
    doctwin_id (deterministic UUID v5). A phantom Source row is created if it
    doesn't exist yet (satisfies the chunks.source_id FK).

    Returns the list of written Chunk ORM objects.
    """
    if not chunk_dicts:
        return []

    # Generate a deterministic synthetic source_id for memory chunks.
    # Ensure the corresponding Source row exists before inserting chunks.
    synthetic_source_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"memory:{doctwin_id}")
    await _ensure_memory_source(doctwin_id, synthetic_source_id, db)

    texts = [c["content"] for c in chunk_dicts]
    batch_result = await embed_batch_with_failover(texts, task="document", db=db)
    embeddings = batch_result.embeddings
    memory_source = await db.get(Source, synthetic_source_id)
    if memory_source is not None:
        memory_source.embedding_provider = batch_result.profile.provider
        memory_source.embedding_model = batch_result.profile.model
        memory_source.embedding_dimensions = batch_result.profile.dimensions
        await db.flush()

    rows: list[Chunk] = []
    for chunk_dict, embedding in zip(chunk_dicts, embeddings, strict=False):
        chunk_type_str = chunk_dict["chunk_type"]
        try:
            chunk_type = ChunkType(chunk_type_str)
        except ValueError:
            logger.warning("unknown_chunk_type", value=chunk_type_str)
            continue

        content = chunk_dict["content"].replace("\x00", "")  # PostgreSQL safety
        token_count = len(content) // 4

        row = Chunk(
            source_id=synthetic_source_id,
            chunk_type=chunk_type,
            lineage=ChunkLineage.memory_derived,
            content=content,
            embedding=embedding,
            source_ref=chunk_dict.get("source_ref", _memory_ref(doctwin_id)),
            snapshot_id=None,
            segment_id=None,
            start_line=None,
            end_line=None,
            content_hash=hash_text(content),
            token_count=token_count,
            chunk_metadata=chunk_dict.get("chunk_metadata", {}),
        )
        db.add(row)
        rows.append(row)

    if rows:
        await db.flush()

    return rows


async def _set_brief_status(doctwin_id: str, status: str, db: AsyncSession) -> None:
    """Update doctwin_configs.memory_brief_status for this twin."""
    result = await db.execute(
        select(TwinConfig).where(TwinConfig.doctwin_id == uuid.UUID(doctwin_id))
    )
    config = result.scalar_one_or_none()
    if config:
        config.memory_brief_status = status
        if status == "ready":
            config.memory_brief_generated_at = datetime.now(UTC)
        await db.flush()


async def _save_memory_brief(doctwin_id: str, brief: str, db: AsyncSession) -> None:
    """Write the generated brief text to doctwin_configs.memory_brief."""
    result = await db.execute(
        select(TwinConfig).where(TwinConfig.doctwin_id == uuid.UUID(doctwin_id))
    )
    config = result.scalar_one_or_none()
    if config:
        config.memory_brief = brief
        config.memory_brief_generated_at = datetime.now(UTC)
        await db.flush()


def _group_paths_by_parent(file_paths: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for raw_path in file_paths:
        path = raw_path.strip("/")
        if not path:
            continue
        parts = PurePosixPath(path).parts
        if len(parts) <= 1:
            grouped["_root"].add(path)
            continue
        grouped["/".join(parts[:-1])].add(path)

    return {
        dir_path: sorted(paths)
        for dir_path, paths in sorted(
            grouped.items(),
            key=lambda item: (_dir_depth(item[0]), item[0]),
        )
    }


def _dir_depth(dir_path: str) -> int:
    if not dir_path or dir_path == "_root":
        return 0
    return len(PurePosixPath(dir_path).parts)


async def _load_memory_artifact_labels_for_twin(doctwin_id: str, db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(Chunk.chunk_type).where(
            Chunk.source_ref == _memory_ref(doctwin_id),
            Chunk.chunk_type.in_(
                [
                    ChunkType.feature_summary,
                    ChunkType.auth_flow,
                    ChunkType.onboarding_map,
                    ChunkType.risk_note,
                    ChunkType.change_entry,
                ]
            ),
        )
    )
    return [
        str(row.chunk_type.value if hasattr(row.chunk_type, "value") else row.chunk_type)
        for row in result.fetchall()
    ]


def _brief_excerpt(brief: str) -> str:
    cleaned = " ".join(line.strip() for line in brief.splitlines() if line.strip() and not line.startswith("#"))
    return cleaned[:220] + ("..." if len(cleaned) > 220 else "")


# ── Incremental knowledge brief (raw chunk text → LLM, per source or full rebuild) ──

_RAW_TEXT_CAP = 120_000


async def _concat_chunks_for_source(source_id: str, db: AsyncSession) -> tuple[str, int]:
    """Concatenate all chunk content for a source in stable order (ingestion order)."""
    result = await db.execute(
        select(Chunk.content)
        .where(Chunk.source_id == uuid.UUID(source_id))
        .order_by(Chunk.created_at.asc(), Chunk.id.asc())
    )
    parts = [row[0] or "" for row in result.fetchall()]
    joined = "\n\n".join(parts)
    if len(joined) > _RAW_TEXT_CAP:
        joined = joined[:_RAW_TEXT_CAP]
    return joined, len(parts)


async def _incremental_llm_merge_brief(
    existing_brief: str,
    raw_document_text: str,
    document_label: str,
    *,
    trace_id: str | None,
) -> str:
    provider = get_llm_provider()
    prev = existing_brief.strip() if existing_brief else ""
    user_body = (
        f"## PREVIOUS_BRIEF\n\n{prev or '(none — first document for this twin)'}\n\n"
        f"## RAW_DOCUMENT_TEXT (source: {document_label})\n\n{raw_document_text}"
    )
    response = await provider.complete(
        system_prompt=INCREMENTAL_KNOWLEDGE_BRIEF_SYSTEM,
        messages=[{"role": "user", "content": user_body}],
        max_tokens=8192,
        temperature=0.1,
        trace_id=trace_id,
        generation_name="incremental_knowledge_brief",
    )
    return (response.content or "").strip()


async def _persist_incremental_memory_brief(doctwin_id: str, brief_text: str, db: AsyncSession) -> None:
    """Replace `memory_brief` chunks + TwinConfig text; leave other memory_* chunk types."""
    synthetic_source_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"memory:{doctwin_id}")
    await _ensure_memory_source(doctwin_id, synthetic_source_id, db)
    await db.execute(
        delete(Chunk).where(
            Chunk.source_id == synthetic_source_id,
            Chunk.chunk_type == ChunkType.memory_brief,
        )
    )
    await db.flush()
    safe = brief_text.replace("\x00", "")
    await _embed_and_write_chunks(
        [
            {
                "chunk_type": "memory_brief",
                "content": safe,
                "source_ref": _memory_ref(doctwin_id),
                "chunk_metadata": {
                    "extraction": "incremental_knowledge_brief",
                    "provenance": [],
                },
            }
        ],
        doctwin_id,
        db,
    )
    await _save_memory_brief(doctwin_id, safe, db)
    await _rebuild_workspace_synthesis_for_twin(doctwin_id, db)


async def run_incremental_brief_for_source(
    doctwin_id: str,
    source_id: str,
    db: AsyncSession,
    trace_id: str | None = None,
) -> dict:
    """
    Merge RAW text from one source's chunks with the existing TwinConfig brief via LLM.

    Called after ingestion indexed chunks for that source (source may still be
    ``processing``). Caller must commit.
    """
    stats: dict = {
        "doctwin_id": doctwin_id,
        "source_id": source_id,
        "status": "failed",
        "brief_generated": False,
        "error": None,
        "raw_chars": 0,
        "chunk_rows": 0,
    }
    try:
        src = await db.get(Source, uuid.UUID(source_id))
        if src is None or str(src.doctwin_id) != str(doctwin_id) or src.name == "__memory__":
            stats["error"] = "invalid_source"
            await _set_brief_status(doctwin_id, "failed", db)
            return stats

        raw, n = await _concat_chunks_for_source(source_id, db)
        stats["raw_chars"] = len(raw)
        stats["chunk_rows"] = n
        if not raw.strip():
            stats["error"] = "no_chunk_text"
            await _set_brief_status(doctwin_id, "failed", db)
            return stats

        existing = (await get_memory_brief(doctwin_id, db)) or ""
        brief = await _incremental_llm_merge_brief(
            existing, raw, src.name, trace_id=trace_id
        )
        if not brief.strip():
            stats["error"] = "empty_llm_brief"
            await _set_brief_status(doctwin_id, "failed", db)
            return stats

        await _persist_incremental_memory_brief(doctwin_id, brief, db)
        await _set_brief_status(doctwin_id, "ready", db)
        stats["brief_generated"] = True
        stats["status"] = "ready"
        logger.info(
            "incremental_memory_brief_ok",
            doctwin_id=doctwin_id,
            source_id=source_id,
            brief_len=len(brief),
            chunk_rows=n,
        )
        return stats
    except Exception as exc:
        stats["error"] = str(exc)
        logger.error(
            "incremental_memory_brief_failed",
            doctwin_id=doctwin_id,
            source_id=source_id,
            error=str(exc),
            exc_info=True,
        )
        await _set_brief_status(doctwin_id, "failed", db)
        return stats


async def run_incremental_brief_full_rebuild(
    doctwin_id: str,
    db: AsyncSession,
    trace_id: str | None = None,
) -> dict:
    """
    Rebuild the knowledge brief by merging each ready source sequentially.

    Used when the ARQ job runs without a ``source_id`` (manual regenerate).
    """
    stats: dict = {
        "doctwin_id": doctwin_id,
        "source_id": None,
        "status": "failed",
        "brief_generated": False,
        "error": None,
        "sources_processed": 0,
    }
    try:
        rows = await db.execute(
            select(Source)
            .where(
                Source.doctwin_id == uuid.UUID(doctwin_id),
                Source.name != "__memory__",
                Source.status == SourceStatus.ready,
            )
            .order_by(Source.created_at.asc())
        )
        sources = list(rows.scalars().all())
        if not sources:
            stats["error"] = "no_ready_sources"
            await _set_brief_status(doctwin_id, "failed", db)
            return stats

        merged = ""
        for src in sources:
            raw, n = await _concat_chunks_for_source(str(src.id), db)
            if not raw.strip():
                continue
            merged = await _incremental_llm_merge_brief(
                merged, raw, src.name, trace_id=trace_id
            )
            stats["sources_processed"] += 1

        if not merged.strip():
            stats["error"] = "empty_after_merge"
            await _set_brief_status(doctwin_id, "failed", db)
            return stats

        await _persist_incremental_memory_brief(doctwin_id, merged, db)
        await _set_brief_status(doctwin_id, "ready", db)
        stats["brief_generated"] = True
        stats["status"] = "ready"
        logger.info(
            "incremental_memory_brief_full_rebuild_ok",
            doctwin_id=doctwin_id,
            sources=stats["sources_processed"],
            brief_len=len(merged),
        )
        return stats
    except Exception as exc:
        stats["error"] = str(exc)
        logger.error(
            "incremental_memory_brief_full_rebuild_failed",
            doctwin_id=doctwin_id,
            error=str(exc),
            exc_info=True,
        )
        await _set_brief_status(doctwin_id, "failed", db)
        return stats
