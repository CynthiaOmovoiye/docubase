"""
Structured implementation-fact retrieval (stub).

The docbase product line keeps vector + lexical RAG over chunks; the prior
implementation-facts SQL layer was removed. Router still calls these helpers so
hybrid retrieval stays stable when the facts layer is disabled.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


async def search_implementation_facts_for_twin(
    db: AsyncSession,
    doctwin_id: str,
    terms: list[str],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    del db, doctwin_id, terms, limit
    return []


def build_flow_outline(
    fact_rows: list[dict[str, Any]],
    *,
    graph_edges: list[Any] | None = None,
) -> str:
    """Compact summary for prompts: fact-type counts plus optional graph edge hints."""
    counts: dict[str, int] = {}
    for row in fact_rows:
        if not isinstance(row, dict):
            continue
        ft = row.get("fact_type")
        if ft is None:
            continue
        key = str(ft)
        counts[key] = counts.get(key, 0) + 1

    fact_segment = ", ".join(f"{k}:{counts[k]}" for k in sorted(counts))

    edge_summaries: list[str] = []
    for edge in graph_edges or []:
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("source") or "").strip()
        rel = str(edge.get("relationship") or edge.get("relationship_type") or "").strip()
        tgt = str(edge.get("target") or "").strip()
        if not (src or rel or tgt):
            continue
        edge_summaries.append(f"{src} {rel} {tgt}".strip())

    parts: list[str] = []
    if fact_segment:
        parts.append(fact_segment)
    if edge_summaries:
        parts.append(f"|| structural: {' | '.join(edge_summaries)}")
    return " ".join(parts).strip()
