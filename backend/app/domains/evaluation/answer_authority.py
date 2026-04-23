"""Answer authority / degraded-mode diagnosis (simplified logging helper)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.domains.evaluation.metrics import AnswerQualityMetrics
from app.domains.retrieval.packets import RetrievalEvidencePacket


class AuthorityLevel(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


@dataclass
class AnswerAuthorityDiagnosis:
    authority_level: AuthorityLevel
    degraded_reasons: list[str] = field(default_factory=list)
    stage_signals: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "authority_level": self.authority_level.value,
            "degraded_reasons": list(self.degraded_reasons),
            "stage_signals": self.stage_signals,
        }


def build_answer_authority_diagnosis(
    *,
    used_deterministic_fallback: bool,
    chunk_count: int,
    retrieval_packet: RetrievalEvidencePacket | None,
    memory_brief_injected: bool,
    memory_brief_status: str | None,
    quality_metrics: AnswerQualityMetrics | dict[str, Any] | None,
    latency_budget_exceeded: bool,
    workspace_scope: bool,
    sources: list[dict[str, Any]] | None,
    source_models: list[Any] | None,
) -> AnswerAuthorityDiagnosis:
    del retrieval_packet, sources, source_models
    reasons: list[str] = []
    if used_deterministic_fallback:
        reasons.append("deterministic_fallback")
    if chunk_count == 0:
        reasons.append("no_retrieved_chunks")
    if memory_brief_status not in (None, "ready") and not memory_brief_injected:
        reasons.append("memory_brief_not_ready")
    if latency_budget_exceeded:
        reasons.append("latency_budget_exceeded")
    overall_raw = None
    if quality_metrics is not None:
        if isinstance(quality_metrics, dict):
            overall_raw = quality_metrics.get("overall_score")
        else:
            overall_raw = getattr(quality_metrics, "overall_score", None)
    if overall_raw is not None:
        try:
            score = float(overall_raw)
            if score < 0.35:
                reasons.append("low_quality_score")
        except (TypeError, ValueError):
            pass

    level = AuthorityLevel.high
    if reasons:
        level = AuthorityLevel.medium if len(reasons) == 1 else AuthorityLevel.low

    return AnswerAuthorityDiagnosis(
        authority_level=level,
        degraded_reasons=reasons,
        stage_signals={
            "retrieval": {},
            "generation": {},
            "verification": {},
        },
    )
