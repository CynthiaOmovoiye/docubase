"""
Twin evidence health summary (Phase 0).

Provides a rolled-up view of source index health and memory brief status
for a twin. Used by dashboards and debugging endpoints to quickly assess
whether evidence is strong enough for high-authority answers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.source import Source


def build_doctwin_evidence_health_summary(
    sources: list["Source"],
    memory_brief_status: str | None = None,
) -> dict:
    """
    Build a health summary dict matching TwinEvidenceHealthResponse fields
    (minus doctwin_id, which the caller adds).

    Returns plain counts and coverage indicators derived from each source's
    index_health field. No DB queries — caller is responsible for loading sources.
    """
    source_count = len(sources)
    ready_sources = [s for s in sources if getattr(s, "status", None) and str(s.status) == "ready"]
    ready_source_count = len(ready_sources)
    non_ready_source_count = source_count - ready_source_count

    legacy_source_count = 0
    strict_source_count = 0
    parser_ratios: list[float] = []
    strict_ratios: list[float] = []
    canonical_mirror_ready_count = 0
    canonical_mirror_file_count = 0

    for source in sources:
        index_health = getattr(source, "index_health", None) or {}
        index_mode = str(getattr(source, "index_mode", "") or "")

        if index_mode == "strict":
            strict_source_count += 1
        elif not index_mode or index_mode == "legacy":
            legacy_source_count += 1

        parser_coverage = index_health.get("parser_coverage_ratio")
        if isinstance(parser_coverage, (int, float)):
            parser_ratios.append(float(parser_coverage))

        strict_coverage = index_health.get("strict_coverage_ratio")
        if isinstance(strict_coverage, (int, float)):
            strict_ratios.append(float(strict_coverage))

        mirror = index_health.get("canonical_mirror") or {}
        if mirror.get("ready"):
            canonical_mirror_ready_count += 1
            canonical_mirror_file_count += int(mirror.get("file_count") or 0)

    any_strict_evidence_not_ready = bool(
        strict_source_count > 0 and non_ready_source_count > 0
    )

    return {
        "source_count": source_count,
        "ready_source_count": ready_source_count,
        "non_ready_source_count": non_ready_source_count,
        "legacy_source_count": legacy_source_count,
        "strict_source_count": strict_source_count,
        "min_parser_coverage_ratio": min(parser_ratios) if parser_ratios else None,
        "min_strict_coverage_ratio": min(strict_ratios) if strict_ratios else None,
        "canonical_mirror_ready_count": canonical_mirror_ready_count,
        "canonical_mirror_file_count": canonical_mirror_file_count,
        "any_strict_evidence_not_ready": any_strict_evidence_not_ready,
        "memory_brief_status": memory_brief_status,
    }
