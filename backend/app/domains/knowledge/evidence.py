"""
Phase 0 evidence-contract helpers.

These helpers define the strict evidence contract for repo intelligence without
mixing product-critical rules into the generic chunking pipeline.

Namespace field names for strict file-backed evidence are also listed in
``app.domains.evidence.invariants`` for cross-layer documentation.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from app.models.chunk import ChunkLineage, ChunkType
from app.models.source import SourceIndexMode, SourceType

_STRICT_HYDRATION_SOURCE_TYPES = {
    SourceType.google_drive,
    SourceType.markdown,
    SourceType.pdf,
    SourceType.url,
}

_MEMORY_TYPES = {
    ChunkType.change_entry,
    ChunkType.risk_note,
    ChunkType.decision_record,
    ChunkType.hotspot,
    ChunkType.memory_brief,
    ChunkType.feature_summary,
    ChunkType.auth_flow,
    ChunkType.onboarding_map,
}

_SYNTHETIC_TYPES = {
    ChunkType.career_summary,
    ChunkType.experience_entry,
    ChunkType.project_description,
    ChunkType.skill_profile,
    ChunkType.manual_note,
}


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_root_hash(file_fingerprints: list[tuple[str, str]]) -> str | None:
    """
    Build a deterministic root hash from (path, file_content_hash) pairs.
    """
    if not file_fingerprints:
        return None
    material = "\n".join(
        f"{path}:{file_hash}"
        for path, file_hash in sorted(set(file_fingerprints))
    )
    return hash_text(material)


def resolve_snapshot_id(
    fetch_metadata: dict[str, Any] | None,
    head_sha: str | None,
    next_page_token: str | None,
    snapshot_root_hash: str | None,
) -> str | None:
    """
    Determine a stable snapshot id for the current sync.
    """
    if head_sha:
        return head_sha
    if fetch_metadata:
        revision_id = fetch_metadata.get("revision_id") or fetch_metadata.get("snapshot_id")
        if revision_id:
            return str(revision_id)
        drive_revision = fetch_metadata.get("modified_time")
        file_id = fetch_metadata.get("file_id")
        if file_id and drive_revision:
            return f"drive:{file_id}:{drive_revision}"
    if next_page_token:
        return f"drive_cursor:{next_page_token}"
    if snapshot_root_hash:
        return f"hash:{snapshot_root_hash}"
    return None


def classify_chunk_lineage(
    chunk_type: ChunkType | str,
    source_type: SourceType,
) -> ChunkLineage:
    """
    Classify a chunk into the correct evidence lineage.
    """
    normalized = chunk_type if isinstance(chunk_type, ChunkType) else ChunkType(chunk_type)

    if normalized in _MEMORY_TYPES:
        return ChunkLineage.memory_derived
    if normalized in _SYNTHETIC_TYPES or source_type == SourceType.manual:
        return ChunkLineage.synthetic_profile
    if source_type in {SourceType.google_drive, SourceType.markdown, SourceType.pdf, SourceType.url}:
        return ChunkLineage.file_backed
    return ChunkLineage.connector_segment


def supports_strict_evidence(source_type: SourceType) -> bool:
    return source_type in _STRICT_HYDRATION_SOURCE_TYPES


def build_segment_id(
    path: str | None,
    chunk_type: ChunkType | str,
    start_line: int | None,
    end_line: int | None,
    fallback_part: int | None = None,
) -> str | None:
    """
    Build a stable segment id for a chunk when the lineage requires one.
    """
    if not path:
        return None
    if start_line is not None and end_line is not None:
        return f"{path}:{start_line}-{end_line}:{ChunkType(chunk_type).value}"
    if fallback_part is not None:
        return f"{path}:part-{fallback_part}:{ChunkType(chunk_type).value}"
    return f"{path}:{ChunkType(chunk_type).value}"


def is_strict_chunk_ready(
    lineage: ChunkLineage,
    snapshot_id: str | None,
    content_hash: str | None,
    start_line: int | None,
    end_line: int | None,
    segment_id: str | None,
) -> bool:
    """
    Check whether a chunk satisfies the strict evidence contract for its lineage.
    """
    if lineage in {ChunkLineage.synthetic_profile, ChunkLineage.memory_derived}:
        return True
    if not snapshot_id or not content_hash or not segment_id:
        return False
    if lineage in {ChunkLineage.file_backed, ChunkLineage.connector_segment}:
        return start_line is not None and end_line is not None and start_line <= end_line
    return False


def determine_index_mode(
    source_type: SourceType,
    strict_ready: bool,
) -> SourceIndexMode:
    if supports_strict_evidence(source_type) and strict_ready:
        return SourceIndexMode.strict
    return SourceIndexMode.legacy


def stale_after_hours_for_source(source_type: SourceType) -> int:
    if source_type == SourceType.google_drive:
        return 48
    if source_type in {SourceType.pdf, SourceType.markdown, SourceType.url}:
        return 72
    return 168


def build_index_health(
    *,
    source_type: SourceType,
    snapshot_id: str | None,
    snapshot_root_hash: str | None,
    stats: dict[str, Any],
    strict_chunk_total: int,
    strict_chunk_ready: int,
    total_chunks: int,
    policy_signature: dict[str, Any] | None = None,
    implementation_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    strict_supported = supports_strict_evidence(source_type)
    strict_ready = strict_supported and (
        strict_chunk_total == 0 or strict_chunk_total == strict_chunk_ready
    )
    index_mode = determine_index_mode(source_type, strict_ready)

    legacy_reasons: list[str] = []
    if not strict_supported:
        legacy_reasons.append(f"{source_type.value} canonical hydration is not implemented yet")
    if strict_chunk_total > strict_chunk_ready:
        legacy_reasons.append("some evidence chunks are missing strict metadata invariants")
    if strict_supported and not snapshot_id:
        legacy_reasons.append("snapshot identity is missing")
    if strict_supported and not snapshot_root_hash:
        legacy_reasons.append("snapshot root hash is missing")

    coverage = {
        "files_received": stats.get("files_received", 0),
        "files_processed": stats.get("files_processed", 0),
        "files_blocked": stats.get("files_blocked", 0),
        "files_secret_flagged": stats.get("files_secret_flagged", 0),
        "chunks_created": stats.get("chunks_created", 0),
        "chunks_embedded": stats.get("chunks_embedded", 0),
        "implementation_files_indexed": stats.get("implementation_files_indexed", 0),
        "implementation_symbols_indexed": stats.get("implementation_symbols_indexed", 0),
        "implementation_relationships_indexed": stats.get("implementation_relationships_indexed", 0),
    }

    contract = {
        "total_chunks": total_chunks,
        "strict_chunk_total": strict_chunk_total,
        "strict_chunk_ready": strict_chunk_ready,
        "strict_coverage_ratio": (
            round(strict_chunk_ready / strict_chunk_total, 4)
            if strict_chunk_total
            else 1.0
        ),
    }
    freshness = {
        "last_indexed_at": datetime.now(UTC).isoformat(),
        "stale_after_hours": stale_after_hours_for_source(source_type),
    }

    return {
        "snapshot_id": snapshot_id,
        "snapshot_root_hash": snapshot_root_hash,
        "strict_evidence_supported": strict_supported,
        "strict_evidence_ready": index_mode == SourceIndexMode.strict,
        "index_mode": index_mode.value,
        "backfill_required": index_mode == SourceIndexMode.legacy,
        "legacy_reasons": legacy_reasons,
        "policy": policy_signature or {},
        "coverage": coverage,
        "contract": contract,
        "freshness": freshness,
        "implementation_index": implementation_index or {},
    }
