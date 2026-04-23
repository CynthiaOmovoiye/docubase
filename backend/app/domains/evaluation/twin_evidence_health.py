"""Twin-level rollup of source index health (simplified for docbase)."""

from __future__ import annotations

from typing import Any

from app.models.source import Source, SourceIndexMode, SourceStatus


def build_doctwin_evidence_health_summary(
    *,
    sources: list[Source],
    memory_brief_status: str | None,
) -> dict[str, Any]:
    ready = [s for s in sources if s.status == SourceStatus.ready]
    legacy = [s for s in sources if s.index_mode == SourceIndexMode.legacy]
    strict = [s for s in sources if s.index_mode == SourceIndexMode.strict]
    return {
        "source_count": len(sources),
        "ready_source_count": len(ready),
        "non_ready_source_count": len(sources) - len(ready),
        "legacy_source_count": len(legacy),
        "strict_source_count": len(strict),
        "min_parser_coverage_ratio": None,
        "min_strict_coverage_ratio": None,
        "canonical_mirror_ready_count": 0,
        "canonical_mirror_file_count": 0,
        "implementation_fact_count": 0,
        "any_strict_evidence_not_ready": False,
        "memory_brief_status": memory_brief_status,
    }
