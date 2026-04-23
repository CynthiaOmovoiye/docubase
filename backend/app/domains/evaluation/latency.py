from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.core.config import get_settings

settings = get_settings()


@dataclass(slots=True)
class ChatLatencyReport:
    retrieval_ms: int
    generation_ms: int
    verification_ms: int
    total_ms: int
    retrieval_budget_ms: int
    generation_budget_ms: int
    verification_budget_ms: int
    total_budget_ms: int
    workspace_scope: bool
    exceeded_budgets: list[str] = field(default_factory=list)

    @property
    def budget_exceeded(self) -> bool:
        return bool(self.exceeded_budgets)

    def to_log_dict(self) -> dict:
        return {
            **asdict(self),
            "budget_exceeded": self.budget_exceeded,
        }


def build_chat_latency_report(
    *,
    retrieval_ms: float,
    generation_ms: float,
    verification_ms: float,
    total_ms: float,
    workspace_scope: bool,
) -> ChatLatencyReport:
    total_budget_ms = (
        settings.workspace_chat_total_latency_budget_ms
        if workspace_scope
        else settings.chat_total_latency_budget_ms
    )
    exceeded: list[str] = []
    if retrieval_ms > settings.chat_retrieval_latency_budget_ms:
        exceeded.append("retrieval")
    if generation_ms > settings.chat_generation_latency_budget_ms:
        exceeded.append("generation")
    if verification_ms > settings.chat_verification_latency_budget_ms:
        exceeded.append("verification")
    if total_ms > total_budget_ms:
        exceeded.append("total")

    return ChatLatencyReport(
        retrieval_ms=int(round(retrieval_ms)),
        generation_ms=int(round(generation_ms)),
        verification_ms=int(round(verification_ms)),
        total_ms=int(round(total_ms)),
        retrieval_budget_ms=settings.chat_retrieval_latency_budget_ms,
        generation_budget_ms=settings.chat_generation_latency_budget_ms,
        verification_budget_ms=settings.chat_verification_latency_budget_ms,
        total_budget_ms=total_budget_ms,
        workspace_scope=workspace_scope,
        exceeded_budgets=exceeded,
    )
