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
    del sources, source_models
    retrieval_signal: dict[str, Any] = {}
    if retrieval_packet is not None:
        mode_val = (
            retrieval_packet.mode.value
            if hasattr(retrieval_packet.mode, "value")
            else str(retrieval_packet.mode)
        )
        retrieval_signal = {
            "chunks_returned": len(retrieval_packet.chunks),
            "missing_evidence": list(retrieval_packet.missing_evidence),
            "searched_layers": list(retrieval_packet.searched_layers),
            "search_query_preview": (retrieval_packet.search_query or "")[:240],
            "lexical_query_preview": (retrieval_packet.lexical_query or "")[:240],
            "mode": mode_val,
            "hits": [
                {
                    "chunk_id": str(ch.get("chunk_id") or ""),
                    "score": round(float(ch.get("score") or 0.0), 5),
                    "chunk_type": str(ch.get("chunk_type") or ""),
                    "source_ref": (ch.get("source_ref") or "")[:160],
                    "match_reasons": list(ch.get("match_reasons") or []),
                    "content_preview": (ch.get("content") or "")[:220],
                }
                for ch in retrieval_packet.chunks[:16]
            ],
        }
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
            "retrieval": retrieval_signal,
            "generation": {},
            "verification": {},
        },
    )
