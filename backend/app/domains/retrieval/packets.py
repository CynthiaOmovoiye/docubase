"""
Evidence packet types for retrieval.

Phase 2 keeps the answering surface stable by still exposing hydrated chunks,
but chat and workspace routing now carry a richer packet alongside them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.domains.retrieval.fact_retrieval import build_flow_outline
from app.domains.retrieval.planner import RetrievalMode, RetrievalPlan


LEXICAL_SEARCH_SUBSTRATE = "postgres_fts"
_BACKTICK_RE = re.compile(r"`([^`\n]{1,200})`")
_FILELIKE_RE = re.compile(
    r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+|[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|jsx|json|yaml|yml|sql|md|toml|go|java|rb|php|rs)"
)


@dataclass(slots=True)
class EvidenceFileRef:
    path: str
    twin_id: str | None = None
    source_id: str | None = None
    snapshot_id: str | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceSymbolRef:
    symbol_name: str
    qualified_name: str
    symbol_kind: str
    path: str
    twin_id: str | None = None
    source_id: str | None = None
    snapshot_id: str | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceSpan:
    chunk_id: str
    chunk_type: str
    path: str | None
    twin_id: str | None
    source_id: str | None
    snapshot_id: str | None
    start_line: int | None
    end_line: int | None
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RetrievalEvidencePacket:
    query: str
    search_query: str
    lexical_query: str
    intent: str | None
    mode: RetrievalMode
    search_substrate: str = LEXICAL_SEARCH_SUBSTRATE
    twin_id: str | None = None
    workspace_id: str | None = None
    searched_layers: list[str] = field(default_factory=list)
    negative_evidence_scope: list[str] = field(default_factory=list)
    query_labels: list[str] = field(default_factory=list)
    flow_outline: str = ""
    facts: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    files: list[EvidenceFileRef] = field(default_factory=list)
    symbols: list[EvidenceSymbolRef] = field(default_factory=list)
    spans: list[EvidenceSpan] = field(default_factory=list)
    graph_edges: list[dict[str, str]] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    layer_hits: dict[str, int] = field(default_factory=dict)

    @property
    def chunk_ids(self) -> list[str]:
        return [str(chunk["chunk_id"]) for chunk in self.chunks if chunk.get("chunk_id")]


def build_evidence_packet(
    *,
    plan: RetrievalPlan,
    chunks: list[dict[str, Any]],
    twin_id: str | None,
    workspace_id: str | None = None,
    file_matches: list[EvidenceFileRef] | None = None,
    symbol_matches: list[EvidenceSymbolRef] | None = None,
    graph_edges: list[dict[str, str]] | None = None,
    missing_evidence: list[str] | None = None,
    facts: list[dict[str, Any]] | None = None,
    query_labels: list[str] | None = None,
    flow_outline: str | None = None,
) -> RetrievalEvidencePacket:
    fact_rows = list(facts or [])
    labels = list(query_labels if query_labels is not None else plan.query_labels)
    outline = (
        flow_outline
        if flow_outline is not None
        else build_flow_outline(fact_rows, graph_edges=list(graph_edges or []))
    )
    packet = RetrievalEvidencePacket(
        query=plan.query,
        search_query=plan.search_query,
        lexical_query=plan.lexical_query,
        intent=plan.intent.value if plan.intent else None,
        mode=plan.mode,
        twin_id=twin_id,
        workspace_id=workspace_id,
        searched_layers=list(plan.searched_layers),
        negative_evidence_scope=list(plan.negative_evidence_scope),
        query_labels=labels,
        flow_outline=outline,
        facts=fact_rows,
        chunks=chunks,
        files=list(file_matches or []),
        symbols=list(symbol_matches or []),
        graph_edges=list(graph_edges or []),
        missing_evidence=list(missing_evidence or []),
    )

    packet.spans = _build_spans(chunks)
    packet.files = _merge_files(packet.files, chunks)
    packet.layer_hits = _build_layer_hits(chunks, packet.files, packet.symbols, fact_count=len(fact_rows))
    return packet


def _build_spans(chunks: list[dict[str, Any]]) -> list[EvidenceSpan]:
    spans: list[EvidenceSpan] = []
    for chunk in chunks:
        chunk_type = chunk.get("chunk_type")
        if hasattr(chunk_type, "value"):
            chunk_type = chunk_type.value
        spans.append(
            EvidenceSpan(
                chunk_id=str(chunk.get("chunk_id")),
                chunk_type=str(chunk_type),
                path=chunk.get("source_ref"),
                twin_id=chunk.get("twin_id"),
                source_id=chunk.get("source_id"),
                snapshot_id=chunk.get("snapshot_id"),
                start_line=chunk.get("start_line"),
                end_line=chunk.get("end_line"),
                score=float(chunk.get("score") or 0.0),
                reasons=list(chunk.get("match_reasons") or []),
            )
        )
    return spans


def _merge_files(
    file_matches: list[EvidenceFileRef],
    chunks: list[dict[str, Any]],
) -> list[EvidenceFileRef]:
    by_path: dict[str, EvidenceFileRef] = {file_ref.path: file_ref for file_ref in file_matches}
    for chunk in chunks:
        path = chunk.get("source_ref")
        if not path or str(path).startswith("__memory__/"):
            for derived_path, derived_reason in _memory_file_refs_from_chunk(chunk):
                _upsert_file_ref(
                    by_path,
                    path=derived_path,
                    twin_id=chunk.get("twin_id"),
                    source_id=chunk.get("source_id"),
                    snapshot_id=chunk.get("snapshot_id"),
                    reasons=[derived_reason, *(chunk.get("match_reasons") or [])],
                )
            continue
        _upsert_file_ref(
            by_path,
            path=str(path),
            twin_id=chunk.get("twin_id"),
            source_id=chunk.get("source_id"),
            snapshot_id=chunk.get("snapshot_id"),
            reasons=list(chunk.get("match_reasons") or []),
        )
    return sorted(by_path.values(), key=_file_sort_key)


def _upsert_file_ref(
    by_path: dict[str, EvidenceFileRef],
    *,
    path: str,
    twin_id: str | None,
    source_id: str | None,
    snapshot_id: str | None,
    reasons: list[str],
) -> None:
    file_ref = by_path.get(path)
    if file_ref is None:
        file_ref = EvidenceFileRef(
            path=path,
            twin_id=twin_id,
            source_id=source_id,
            snapshot_id=snapshot_id,
            reasons=[],
        )
        by_path[file_ref.path] = file_ref
    for reason in reasons:
        if reason and reason not in file_ref.reasons:
            file_ref.reasons.append(reason)


def _memory_file_refs_from_chunk(chunk: dict[str, Any]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    metadata = chunk.get("chunk_metadata") or {}
    provenance = metadata.get("provenance") or []
    for item in provenance:
        if not isinstance(item, dict):
            continue
        candidate = item.get("path") or item.get("file_path") or item.get("source_ref")
        if isinstance(candidate, str) and _looks_like_file_path(candidate):
            refs.append((candidate, "memory:provenance"))

    if refs:
        return list(dict.fromkeys(refs))

    content = str(chunk.get("content") or "")
    inferred: list[tuple[str, str]] = []
    for match in _BACKTICK_RE.finditer(content):
        token = match.group(1).strip()
        if _looks_like_file_path(token):
            inferred.append((token, "memory:content"))
    for match in _FILELIKE_RE.finditer(content):
        token = match.group(0).strip()
        if _looks_like_file_path(token):
            inferred.append((token, "memory:content"))
    return list(dict.fromkeys(inferred))


def _looks_like_file_path(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered or lowered.startswith("__memory__/"):
        return False
    if "@" in lowered:
        return False
    return bool(("/" in lowered or "." in lowered) and _FILELIKE_RE.fullmatch(lowered))


def _build_layer_hits(
    chunks: list[dict[str, Any]],
    files: list[EvidenceFileRef],
    symbols: list[EvidenceSymbolRef],
    *,
    fact_count: int = 0,
) -> dict[str, int]:
    hits: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for chunk in chunks:
        for reason in chunk.get("match_reasons") or []:
            layer = reason.split(":", 1)[0]
            reason_counts[layer] = reason_counts.get(layer, 0) + 1
    hits.update(reason_counts)
    if files:
        hits["file"] = max(hits.get("file", 0), len(files))
    if symbols:
        hits["symbol"] = max(hits.get("symbol", 0), len(symbols))
    if fact_count:
        hits["facts"] = fact_count
    return hits


def _file_sort_key(item: EvidenceFileRef) -> tuple[int, str]:
    lowered = item.path.lower()
    layers = {reason.split(":", 1)[0] for reason in item.reasons}
    priority = 0
    if lowered.startswith("__memory__/"):
        priority += 40
    if (
        lowered.endswith("agents.md")
        or lowered.endswith("claude.md")
        or lowered.endswith(".docx")
        or "/templates/" in lowered
    ):
        priority += 20
    if any(layer in {"symbol", "file", "path"} for layer in layers):
        priority -= 15
    if any(token in lowered for token in ("auth", "logout", "refresh", "session", "token", "dashboard")):
        priority -= 8
    return priority, item.path
