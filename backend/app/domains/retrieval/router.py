"""
Retrieval and routing domain.

Given a user query, this domain:
1. Generates a query embedding
2. Searches the vector index for relevant chunks
3. Filters results by policy (chunk type, twin config)
4. For workspace-level chat, identifies the most relevant twin first

The result is a ranked list of policy-cleared chunks ready for the answering domain.

pgvector operator used: <=> (cosine distance, lower = more similar).
We convert to similarity scores: score = 1 - distance.

Intent-aware retrieval:
  When an optional QueryIntent is provided, preferred chunk types receive a +0.15
  SQL score boost. This is a soft boost — not a hard filter — so results always
  return even when preferred types have no matches yet.
"""

import inspect
import uuid
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domains.embedding.embedder import (
    EmbeddingProfile,
    embed_text_with_profile,
    get_primary_embedding_profile,
    resolve_embedding_profile,
)
from app.domains.retrieval.hybrid import (
    fetch_file_candidates,
    fetch_lexical_chunk_candidates,
    fetch_symbol_candidates,
    merge_candidate,
)
from app.domains.retrieval.hydration import hydrate_retrieved_chunks
from app.domains.retrieval.intent import QueryIntent, extract_path_hint
from app.domains.retrieval.multihop import multihop_retrieve_with_graph
from app.domains.retrieval.packets import (
    EvidenceFileRef,
    EvidenceSymbolRef,
    RetrievalEvidencePacket,
    build_evidence_packet,
)
from app.domains.retrieval.planner import RetrievalMode, build_retrieval_plan
from app.domains.retrieval.reranker import rerank_chunks, reranker_available
from app.models.chunk import Chunk
from app.models.source import Source, SourceStatus
from app.models.twin import Twin, TwinConfig

logger = get_logger(__name__)

# When a reranker is configured, over-fetch this many candidates from pgvector
# so the reranker has a larger pool to choose from.
_RERANK_OVERFETCH_MULTIPLIER = 3
_RERANK_MAX_CANDIDATES = 40
_MAX_GUARANTEED_CHUNKS = 8
_MAX_GUARANTEED_PER_REF = 2

# Minimum similarity score to include a chunk in results.
# 0.15 is intentionally permissive — Jina and similar embedding models produce
# lower raw cosine similarity than OpenAI models. Reranking happens after
# retrieval and will down-rank genuinely irrelevant chunks, so a lower floor
# here improves recall without hurting precision in the final answer.
_MIN_SCORE = 0.15

# Score boost for preferred chunk types per mode (+/- additive)
_MODE_SCORE_ADJUSTMENTS: dict[RetrievalMode, dict[str, float]] = {
    RetrievalMode.implementation: {
        "implementation_fact": 0.40,
        "code_snippet": 0.35,
        "module_description": 0.22,
        "feature_description": 0.12,
        "documentation": -0.18,
        "memory_brief": -0.22,
        "auth_flow": -0.08,
        "onboarding_map": -0.10,
        "feature_summary": -0.10,
        "decision_record": -0.06,
    },
    RetrievalMode.onboarding: {
        "implementation_fact": 0.30,
        "code_snippet": 0.22,
        "module_description": 0.18,
        "feature_description": 0.12,
        "onboarding_map": 0.12,
        "documentation": -0.10,
        "memory_brief": -0.08,
    },
    RetrievalMode.workspace_comparison: {
        "implementation_fact": 0.38,
        "code_snippet": 0.32,
        "module_description": 0.2,
        "feature_description": 0.1,
        "documentation": -0.18,
        "memory_brief": -0.2,
        "auth_flow": -0.06,
        "feature_summary": -0.08,
    },
    RetrievalMode.architecture: {
        "implementation_fact": 0.16,
        "module_description": 0.16,
        "feature_description": 0.1,
        "decision_record": 0.1,
        "feature_summary": 0.08,
        "code_snippet": 0.08,
    },
    RetrievalMode.change_review: {
        "change_entry": 0.24,
        "implementation_fact": 0.12,
        "code_snippet": 0.08,
        "documentation": -0.06,
    },
    RetrievalMode.risk_review: {
        "risk_note": 0.24,
        "implementation_fact": 0.12,
        "module_description": 0.12,
        "code_snippet": 0.08,
        "documentation": -0.08,
    },
    RetrievalMode.recruiter_summary: {
        "feature_summary": 0.12,
        "implementation_fact": 0.12,
        "module_description": 0.1,
        "code_snippet": 0.08,
        "documentation": -0.08,
    },
    RetrievalMode.project_status: {
        "change_entry": 0.22,
        "risk_note": 0.12,
        "implementation_fact": 0.10,
        "documentation": -0.08,
    },
    RetrievalMode.general: {},
}

_IMPLEMENTATIONISH_MODES = {
    RetrievalMode.implementation,
    RetrievalMode.onboarding,
    RetrievalMode.workspace_comparison,
}

_AUTH_QUERY_HINTS = (
    "auth",
    "authentication",
    "authorization",
    "login",
    "logout",
    "register",
    "signup",
    "signin",
    "refresh",
    "token",
    "session",
    "jwt",
    "current_user",
)
_DASHBOARD_QUERY_HINTS = ("dashboard", "audit", "useaudit", "load")
_AUTH_CONTENT_HINTS = (
    "get_current_user",
    "current_user",
    "owner_id",
    "oauth2passwordbearer",
    "refresh_token",
    "refresh token",
    "token",
    "jwt",
)
_AUTH_FEATURE_PATH_HINTS = (
    "/core/auth.py",
    "/routes/auth.py",
    "/api/v1/routes/auth.py",
    "/users.py",
    "/auth.ts",
    "/authrefresh.ts",
    "/sessiongate.tsx",
    "/tokenrefreshscheduler.tsx",
    "/app.tsx",
)
_AUTH_FEATURE_CONTENT_HINTS = (
    "get_current_user",
    "oauth2passwordbearer",
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_refresh_token",
    "hash_password",
    "verify_password",
    "async def login",
    "async def register",
    "async def refresh_tokens",
    "depends(get_current_user)",
    "owner_id",
    "protectedroute",
    "sessiongate",
    "setsessiontokens",
    "clearauth",
    "performtokenrefresh",
)
# Diversity demotion for broad general queries (Phase 4) — tune with golden / retrieval evals.
_SURPLUS_SAME_SOURCE_DEMOTION_FACTOR = 0.62

_ENGINE_QUERY_HINTS = (
    "engine",
    "engines",
    "intake",
    "document",
    "documents",
    "task intelligence",
    "verification",
    "audit",
)

# top_k overrides per intent (broader context for high-level questions)
_INTENT_TOP_K: dict[QueryIntent, int] = {
    QueryIntent.change_query:  12,
    QueryIntent.risk_query:    10,
    QueryIntent.architecture:  8,
    QueryIntent.onboarding:    16,
    QueryIntent.file_specific: 8,
    QueryIntent.general:       8,
}


def _build_mode_boost_sql(mode: RetrievalMode) -> str:
    adjustments = _MODE_SCORE_ADJUSTMENTS.get(mode, {})
    if not adjustments:
        return ""

    when_clauses = "\n".join(
        f"            WHEN c.chunk_type = '{chunk_type}' THEN {adjustment}"
        for chunk_type, adjustment in adjustments.items()
    )
    return f"""
          + CASE
{when_clauses}
            ELSE 0
          END"""


async def retrieve_packet_for_twin(
    query: str,
    doctwin_id: str,
    allow_code_snippets: bool,
    db: AsyncSession,
    top_k: int = 8,
    intent: QueryIntent | None = None,
    path_hints: list[str] | None = None,
    guaranteed_refs: list[str] | None = None,
    expanded_query: str = "",
) -> RetrievalEvidencePacket:
    """
    Retrieve a hybrid evidence packet for a single twin.

    Phase 2 fuses vector candidates with lexical, file, symbol, and graph
    signals, then hydrates the winning chunks and returns a structured packet.
    """
    effective_intent = intent or QueryIntent.general
    if _query_has_auth_hint(f"{query} {expanded_query}"):
        top_k = max(top_k, 22)
    if _query_has_engine_hint(f"{query} {expanded_query}"):
        top_k = max(top_k, 18)
    if top_k == 8:
        top_k = _INTENT_TOP_K.get(effective_intent, top_k)
    plan = build_retrieval_plan(
        query=query,
        intent=effective_intent,
        expanded_query=expanded_query,
        path_hints=path_hints,
        top_k=top_k,
        workspace_scope=False,
    )

    use_reranker = reranker_available()
    dense_fetch_k = (
        min(plan.dense_budget * _RERANK_OVERFETCH_MULTIPLIER, _RERANK_MAX_CANDIDATES)
        if use_reranker
        else plan.dense_budget
    )
    rerank_budget = min(plan.rerank_budget, _RERANK_MAX_CANDIDATES)

    code_filter = "" if allow_code_snippets else "AND c.chunk_type != 'code_snippet'"
    boost_sql = _build_mode_boost_sql(plan.mode)
    profiles = await _load_doctwin_embedding_profiles(doctwin_id, db)
    candidates_by_id: dict[str, dict[str, Any]] = {}
    path_fetch_embedding_literal: str | None = None
    file_matches: list[EvidenceFileRef] = []
    symbol_matches: list[EvidenceSymbolRef] = []
    missing_evidence: list[str] = []
    feature_chunks: list[dict[str, Any]] = []

    if profiles:
        for profile in profiles:
            try:
                query_embedding = await embed_text_with_profile(
                    plan.search_query,
                    profile,
                    task="query",
                    db=db,
                )
            except Exception as exc:
                logger.error(
                    "retrieval_embed_failed",
                    doctwin_id=doctwin_id,
                    provider=profile.provider,
                    model=profile.model,
                    error=str(exc),
                )
                continue

            embedding_literal = _format_embedding(query_embedding)
            if path_fetch_embedding_literal is None:
                path_fetch_embedding_literal = embedding_literal

            try:
                rows = await _fetch_doctwin_candidates_for_profile(
                    db=db,
                    doctwin_id=doctwin_id,
                    embedding_literal=embedding_literal,
                    profile=profile,
                    code_filter=code_filter,
                    boost_sql=boost_sql,
                    top_k=dense_fetch_k,
                )
            except Exception as exc:
                logger.error(
                    "retrieval_query_failed",
                    doctwin_id=doctwin_id,
                    provider=profile.provider,
                    model=profile.model,
                    error=str(exc),
                )
                await db.rollback()
                continue

            for row in rows:
                merge_candidate(
                    candidates_by_id,
                    {
                        "chunk_id": str(row.id),
                        "content": row.content,
                        "chunk_type": row.chunk_type,
                        "source_ref": row.source_ref,
                        "score": float(row.score),
                        "match_reasons": ["vector"],
                    },
                )
    else:
        missing_evidence.append("no_embedding_profiles")
        logger.info("retrieval_no_embedding_profiles", doctwin_id=doctwin_id)

    if "lexical" in plan.searched_layers:
        lexical_chunks = await fetch_lexical_chunk_candidates(
            db=db,
            doctwin_id=doctwin_id,
            lexical_query=plan.lexical_query,
            allow_code_snippets=allow_code_snippets,
            limit=plan.lexical_budget,
        )
        for candidate in lexical_chunks:
            merge_candidate(candidates_by_id, candidate)
        if not lexical_chunks:
            missing_evidence.append("lexical")

    if "file" in plan.searched_layers:
        file_result = await fetch_file_candidates(
            db=db,
            doctwin_id=doctwin_id,
            lexical_query=plan.lexical_query,
            allow_code_snippets=allow_code_snippets,
            limit=plan.file_budget,
        )
        file_matches = file_result.files
        for candidate in file_result.chunks:
            merge_candidate(candidates_by_id, candidate)
        if not file_result.files:
            missing_evidence.append("file")

    if "symbol" in plan.searched_layers:
        symbol_result = await fetch_symbol_candidates(
            db=db,
            doctwin_id=doctwin_id,
            lexical_query=plan.lexical_query,
            allow_code_snippets=allow_code_snippets,
            limit=plan.symbol_budget,
        )
        symbol_matches = symbol_result.symbols
        for candidate in symbol_result.chunks:
            merge_candidate(candidates_by_id, candidate)
        if not symbol_result.symbols:
            missing_evidence.append("symbol")

    if plan.mode in _IMPLEMENTATIONISH_MODES and _query_has_auth_hint(plan.search_query):
        feature_chunks = await _fetch_auth_feature_chunks(
            db=db,
            doctwin_id=doctwin_id,
            query=plan.query,
            allow_code_snippets=allow_code_snippets,
            limit=max(14, top_k),
        )
        for feature_chunk in feature_chunks:
            merge_candidate(candidates_by_id, feature_chunk)
    if _query_has_engine_hint(plan.search_query):
        engine_feature_chunks = await _fetch_engine_feature_chunks(
            db=db,
            doctwin_id=doctwin_id,
            query=plan.query,
            allow_code_snippets=allow_code_snippets,
            limit=max(12, top_k),
        )
        if engine_feature_chunks:
            feature_chunks.extend(engine_feature_chunks)
            for feature_chunk in engine_feature_chunks:
                merge_candidate(candidates_by_id, feature_chunk)

    # Path-hint: guarantee chunks from explicitly-named directories are included
    resolved_hints: list[str] = list(path_hints) if path_hints else []
    if not resolved_hints and "path" in plan.searched_layers:
        regex_hint = extract_path_hint(query)
        if regex_hint:
            resolved_hints = [regex_hint]

    if resolved_hints:
        logger.info(
            "retrieval_path_hints_resolving",
            doctwin_id=doctwin_id,
            hints=resolved_hints,
        )

    for path_hint in resolved_hints:
        path_chunks = await _fetch_by_path_prefix(
            path_hint, path_fetch_embedding_literal, doctwin_id, db,
            allow_code_snippets=allow_code_snippets,
            limit=4,
        )
        for pc in path_chunks:
            pc["match_reasons"] = [f"path:{path_hint}"]
            merge_candidate(candidates_by_id, pc)
        if path_chunks:
            logger.info(
                "retrieval_path_hint_added",
                doctwin_id=doctwin_id,
                path_hint=path_hint,
                added=len(path_chunks),
            )

    graph_chunks: list[dict[str, Any]] = []
    graph_edges: list[dict[str, str]] = []
    if "graph" in plan.searched_layers:
        graph_chunks, graph_edges = await multihop_retrieve_with_graph(
            plan.search_query,
            doctwin_id,
            db,
            allow_code_snippets,
            max_additional_chunks=plan.graph_budget,
        )
        for gc in graph_chunks:
            reasons = list(gc.get("match_reasons") or [])
            reasons.append("graph")
            gc["match_reasons"] = reasons
            merge_candidate(candidates_by_id, gc)
        if not graph_chunks:
            missing_evidence.append("graph")

    for memory_chunk in await _fetch_supporting_memory_chunks(
        db=db,
        doctwin_id=doctwin_id,
        mode=plan.mode,
    ):
        merge_candidate(candidates_by_id, memory_chunk)

    if guaranteed_refs:
        remaining_budget = _MAX_GUARANTEED_CHUNKS
        for ref in guaranteed_refs:
            if remaining_budget <= 0:
                break
            ref_chunks = await _fetch_by_path_prefix(
                ref,
                path_fetch_embedding_literal,
                doctwin_id,
                db,
                allow_code_snippets=allow_code_snippets,
                limit=min(_MAX_GUARANTEED_PER_REF, remaining_budget),
            )
            for rc in ref_chunks[:_MAX_GUARANTEED_PER_REF]:
                if remaining_budget <= 0:
                    break
                rc["match_reasons"] = [f"path:{ref}"]
                merge_candidate(candidates_by_id, rc)
                remaining_budget -= 1
        logger.info(
            "retrieval_guaranteed_refs_added",
            doctwin_id=doctwin_id,
            refs=guaranteed_refs,
            added=len(guaranteed_refs),
        )

    candidate_list = list(candidates_by_id.values())

    candidates = _score_and_prune_candidates(candidate_list, plan)
    if use_reranker and candidates:
        chunks = await rerank_chunks(plan.search_query, candidates[:rerank_budget], top_k)
    else:
        chunks = candidates[:top_k]
    chunks = _pin_feature_chunks(chunks, feature_chunks, top_k)

    logger.info(
        "retrieval_complete",
        doctwin_id=doctwin_id,
        query_length=len(query),
        chunks_returned=len(chunks),
        intent=plan.intent.value if plan.intent else None,
        mode=plan.mode.value,
        reranked=use_reranker,
        graph_chunks=len(graph_chunks),
        guaranteed_refs=len(guaranteed_refs or []),
        lexical_hits=sum(1 for chunk in chunks if "lexical" in (chunk.get("match_reasons") or [])),
        symbol_hits=len(symbol_matches),
    )
    hydrated_chunks = await hydrate_retrieved_chunks(chunks, db)
    return build_evidence_packet(
        plan=plan,
        chunks=hydrated_chunks,
        doctwin_id=doctwin_id,
        file_matches=file_matches,
        symbol_matches=symbol_matches,
        graph_edges=graph_edges,
        missing_evidence=sorted(set(missing_evidence)),
    )


def _demote_surplus_same_source(candidates: list[dict[str, Any]], *, max_per_source: int = 2) -> None:
    """Cap dominance of a single file for broad general questions (Phase 4 diversity)."""
    if len(candidates) < 4:
        return
    order = sorted(
        range(len(candidates)),
        key=lambda i: float(candidates[i].get("score") or 0.0),
        reverse=True,
    )
    counts: dict[str, int] = {}
    for i in order:
        c = candidates[i]
        key = str(c.get("source_ref") or "") or "__empty__"
        seen = counts.get(key, 0)
        counts[key] = seen + 1
        if seen >= max_per_source:
            c["score"] = float(c.get("score") or 0.0) * _SURPLUS_SAME_SOURCE_DEMOTION_FACTOR


def _score_and_prune_candidates(
    candidates: list[dict[str, Any]],
    plan: Any,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    query_text = f"{plan.query} {plan.search_query}".lower()
    auth_query = any(token in query_text for token in _AUTH_QUERY_HINTS)
    dashboard_query = any(token in query_text for token in _DASHBOARD_QUERY_HINTS)
    has_code_candidates = any(_is_code_backed_candidate(candidate) for candidate in candidates)
    auth_boost_trim = 0.0

    adjusted: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate = dict(candidate)
        score = float(candidate.get("score") or 0.0)
        chunk_type = _chunk_type_name(candidate)
        source_ref = str(candidate.get("source_ref") or "")
        lowered_ref = source_ref.lower()
        lowered_content = str(candidate.get("content") or "").lower()
        match_layers = {reason.split(":", 1)[0] for reason in (candidate.get("match_reasons") or [])}

        if plan.mode in _IMPLEMENTATIONISH_MODES:
            if chunk_type == "code_snippet":
                score += 0.18
            elif chunk_type == "module_description":
                score += 0.14
            elif chunk_type == "documentation":
                score -= 0.08

            if any(layer in {"file", "symbol", "path"} for layer in match_layers):
                score += 0.08 * sum(layer in {"file", "symbol", "path"} for layer in match_layers)

            if auth_query and any(token in lowered_ref for token in _AUTH_QUERY_HINTS):
                score += 0.18 - auth_boost_trim
            if auth_query and any(token in lowered_content for token in _AUTH_CONTENT_HINTS):
                score += 0.18 - auth_boost_trim
                if "/api/" in lowered_ref or "/routes/" in lowered_ref:
                    score += 0.14
                if lowered_ref.startswith("tests/"):
                    score += 0.08
            if dashboard_query and any(token in lowered_ref for token in _DASHBOARD_QUERY_HINTS):
                score += 0.16

            if has_code_candidates and source_ref.startswith("__memory__/"):
                score -= 0.2
            if has_code_candidates and _is_meta_doc_path(lowered_ref):
                score -= 0.24

        elif plan.mode == RetrievalMode.recruiter_summary:
            if chunk_type in {"module_description", "code_snippet", "feature_summary"}:
                score += 0.08
            if _is_meta_doc_path(lowered_ref):
                score -= 0.22

        elif plan.mode == RetrievalMode.project_status:
            if chunk_type == "change_entry":
                score += 0.16
            if _is_meta_doc_path(lowered_ref):
                score -= 0.18

        elif plan.mode == RetrievalMode.change_review:
            if chunk_type == "change_entry":
                score += 0.2
            if auth_query and any(token in lowered_ref for token in _AUTH_QUERY_HINTS):
                score += 0.1

        candidate["score"] = score
        adjusted.append(candidate)

    adjusted.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    if plan.mode in _IMPLEMENTATIONISH_MODES and has_code_candidates:
        adjusted = _prune_low_signal_candidates(adjusted)
    return adjusted


async def _fetch_auth_feature_chunks(
    *,
    db: AsyncSession,
    doctwin_id: str,
    query: str,
    allow_code_snippets: bool,
    limit: int,
) -> list[dict[str, Any]]:
    """
    Fetch deterministic auth/session evidence for implementation questions.

    Dense and reranked search can prefer broad frontend/session chunks or docs
    even when the codebase has the exact auth primitives.  This feature pass is
    deliberately parser/index backed: it pins the files that form the real auth
    flow before the LLM writes.
    """
    code_filter = "" if allow_code_snippets else "AND c.chunk_type != 'code_snippet'"
    sql = text(
        f"""
        SELECT
            c.id,
            c.content,
            c.chunk_type,
            c.source_ref
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE s.doctwin_id = :doctwin_id
          AND s.status = 'ready'
          AND coalesce(c.source_ref, '') NOT LIKE '__memory__/%'
          {code_filter}
          AND (
               lower(coalesce(c.source_ref, '')) LIKE '%/core/auth.py'
            OR lower(coalesce(c.source_ref, '')) LIKE '%/routes/auth.py'
            OR lower(coalesce(c.source_ref, '')) LIKE '%/api/v1/routes/auth.py'
            OR lower(coalesce(c.source_ref, '')) LIKE '%/users.py'
            OR lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/lib/auth.ts'
            OR lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/lib/authrefresh.ts'
            OR lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/lib/api.ts'
            OR lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/components/auth/%'
            OR lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/pages/loginpage.tsx'
            OR lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/components/layout/pageshell.tsx'
            OR lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/app.tsx'
            OR lower(coalesce(c.content, '')) LIKE '%get_current_user%'
            OR lower(coalesce(c.content, '')) LIKE '%depends(get_current_user)%'
            OR lower(coalesce(c.content, '')) LIKE '%owner_id%'
            OR lower(coalesce(c.content, '')) LIKE '%oauth2passwordbearer%'
            OR lower(coalesce(c.content, '')) LIKE '%create_access_token%'
            OR lower(coalesce(c.content, '')) LIKE '%decode_refresh_token%'
            OR lower(coalesce(c.content, '')) LIKE '%clearauth%'
            OR lower(coalesce(c.content, '')) LIKE '%performtokenrefresh%'
            OR lower(coalesce(c.content, '')) LIKE '%authapi.login%'
            OR lower(coalesce(c.content, '')) LIKE '%handlelogout%'
            OR lower(coalesce(c.content, '')) LIKE '%protectedroute%'
          )
        ORDER BY
          CASE
            WHEN lower(coalesce(c.source_ref, '')) LIKE '%/core/auth.py' THEN 0
            WHEN lower(coalesce(c.source_ref, '')) LIKE '%/routes/auth.py'
              OR lower(coalesce(c.source_ref, '')) LIKE '%/api/v1/routes/auth.py' THEN 1
            WHEN lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/lib/auth.ts' THEN 2
            WHEN lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/lib/authrefresh.ts' THEN 3
            WHEN lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/lib/api.ts' THEN 4
            WHEN lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/pages/loginpage.tsx' THEN 5
            WHEN lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/components/layout/pageshell.tsx' THEN 6
            WHEN lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/app.tsx' THEN 7
            WHEN lower(coalesce(c.source_ref, '')) LIKE '%frontend/src/components/auth/%' THEN 8
            WHEN lower(coalesce(c.source_ref, '')) LIKE '%/routes/%' THEN 9
            ELSE 10
          END,
          c.start_line NULLS LAST,
          c.id
        LIMIT 300
        """
    )
    try:
        result = await db.execute(sql, {"doctwin_id": doctwin_id})
    except Exception as exc:
        logger.warning("auth_feature_chunk_fetch_failed", doctwin_id=doctwin_id, error=str(exc))
        await _safe_rollback(db)
        return []

    rows = result.fetchall()
    if not rows:
        return []

    query_lower = query.lower()
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        chunk_id = str(row.id)
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        priority = _auth_feature_priority(
            source_ref=str(row.source_ref or ""),
            content=str(row.content or ""),
            query=query_lower,
        )
        if priority >= 100:
            continue
        candidates.append(
            {
                "chunk_id": chunk_id,
                "content": row.content,
                "chunk_type": row.chunk_type,
                "source_ref": row.source_ref,
                "score": max(0.55, 1.08 - (priority * 0.025)),
                "match_reasons": ["feature:auth_flow"],
                "_feature_priority": priority,
            }
        )

    candidates.sort(
        key=lambda item: (
            _feature_priority_sort_value(item),
            -float(item.get("score") or 0.0),
            str(item.get("source_ref") or ""),
        )
    )
    return candidates[:limit]


async def _fetch_engine_feature_chunks(
    *,
    db: AsyncSession,
    doctwin_id: str,
    query: str,
    allow_code_snippets: bool,
    limit: int,
) -> list[dict[str, Any]]:
    """Fetch deterministic Scaffold engine evidence for engine/system questions."""
    code_filter = "" if allow_code_snippets else "AND c.chunk_type != 'code_snippet'"
    sql = text(
        f"""
        SELECT
            c.id,
            c.content,
            c.chunk_type,
            c.source_ref
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE s.doctwin_id = :doctwin_id
          AND s.status = 'ready'
          AND coalesce(c.source_ref, '') NOT LIKE '__memory__/%'
          {code_filter}
          AND (
               lower(coalesce(c.source_ref, '')) LIKE '%readme.md'
            OR lower(coalesce(c.source_ref, '')) LIKE '%/api/v1/routes/intake.py'
            OR lower(coalesce(c.source_ref, '')) LIKE '%/engines/intake/%'
            OR lower(coalesce(c.source_ref, '')) LIKE '%/engines/intake_engine.py'
            OR lower(coalesce(c.source_ref, '')) LIKE '%/engines/documents/%'
            OR lower(coalesce(c.source_ref, '')) LIKE '%/engines/tasks/%'
            OR lower(coalesce(c.source_ref, '')) LIKE '%/engines/verification/%'
            OR lower(coalesce(c.source_ref, '')) LIKE '%/engines/audit/%'
            OR lower(coalesce(c.content, '')) LIKE '%intake engine%'
            OR lower(coalesce(c.content, '')) LIKE '%document engine%'
            OR lower(coalesce(c.content, '')) LIKE '%task intelligence engine%'
            OR lower(coalesce(c.content, '')) LIKE '%verification engine%'
            OR lower(coalesce(c.content, '')) LIKE '%audit engine%'
            OR lower(coalesce(c.content, '')) LIKE '%run_intake%'
            OR lower(coalesce(c.content, '')) LIKE '%build_intake_graph%'
            OR lower(coalesce(c.content, '')) LIKE '%generate_document%'
            OR lower(coalesce(c.content, '')) LIKE '%recommend_assignments%'
            OR lower(coalesce(c.content, '')) LIKE '%process_commit%'
            OR lower(coalesce(c.content, '')) LIKE '%evaluate_all_controls%'
          )
        LIMIT 400
        """
    )
    try:
        result = await db.execute(sql, {"doctwin_id": doctwin_id})
    except Exception as exc:
        logger.warning("engine_feature_chunk_fetch_failed", doctwin_id=doctwin_id, error=str(exc))
        await _safe_rollback(db)
        return []

    query_lower = query.lower()
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in result.fetchall():
        priority = _engine_feature_priority(
            source_ref=str(row.source_ref or ""),
            content=str(row.content or ""),
            query=query_lower,
        )
        if priority >= 100:
            continue
        chunk_id = str(row.id)
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        candidates.append(
            {
                "chunk_id": chunk_id,
                "content": row.content,
                "chunk_type": row.chunk_type,
                "source_ref": row.source_ref,
                "score": max(0.56, 1.06 - (priority * 0.025)),
                "match_reasons": ["feature:engine_flow"],
                "_feature_priority": priority,
            }
        )

    candidates.sort(
        key=lambda item: (
            _feature_priority_sort_value(item),
            -float(item.get("score") or 0.0),
            str(item.get("source_ref") or ""),
        )
    )
    if "5 engine" in query_lower or "five engine" in query_lower or "engines" in query_lower:
        # Engine-list questions need breadth across engine folders more than
        # several chunks from the same high-scoring README or intake file.
        selected: list[dict[str, Any]] = []
        selected_refs: set[str] = set()
        selected_ids: set[str] = set()
        for candidate in candidates:
            source_ref = str(candidate.get("source_ref") or "")
            if source_ref in selected_refs:
                continue
            selected.append(candidate)
            selected_refs.add(source_ref)
            selected_ids.add(str(candidate.get("chunk_id") or ""))
            if len(selected) >= limit:
                return selected
        for candidate in candidates:
            chunk_id = str(candidate.get("chunk_id") or "")
            if chunk_id in selected_ids:
                continue
            selected.append(candidate)
            if len(selected) >= limit:
                break
        return selected[:limit]
    return candidates[:limit]


def _engine_feature_priority(*, source_ref: str, content: str, query: str) -> int:
    ref = source_ref.lower()
    text = content.lower()
    compact = text.replace(" ", "")
    wants_intake = "intake" in query
    wants_list = "5 engine" in query or "five engine" in query or "engines" in query

    if wants_intake:
        if ref.endswith("/api/v1/routes/intake.py"):
            return 0
        if "/engines/intake/graph.py" in ref or "build_intake_graph" in compact or "run_intake" in compact:
            return 1
        if "/engines/intake/nodes.py" in ref:
            return 2
        if "/engines/intake/parser.py" in ref:
            return 3
        if "/engines/intake/brief_confidence.py" in ref:
            return 4
        if "/engines/intake/schemas.py" in ref or "/engines/intake/state.py" in ref:
            return 5
        if ref.endswith("readme.md") and "intake engine" in text:
            return 6
        return 100

    if wants_list:
        if ref.endswith("readme.md") and any(
            marker in text
            for marker in (
                "intake engine",
                "document engine",
                "task intelligence engine",
                "verification engine",
                "audit engine",
            )
        ):
            return 0
        if "/engines/intake/" in ref:
            return 1
        if "/engines/documents/" in ref:
            return 2
        if "/engines/tasks/" in ref:
            return 3
        if "/engines/verification/" in ref:
            return 4
        if "/engines/audit/" in ref:
            return 5
        return 100

    if "/engines/" in ref or ref.endswith("readme.md"):
        return 20
    return 100


def _feature_priority_sort_value(item: dict[str, Any]) -> int:
    priority = item.get("_feature_priority")
    if priority is None:
        return 100
    try:
        return int(priority)
    except (TypeError, ValueError):
        return 100


def _auth_feature_priority(*, source_ref: str, content: str, query: str) -> int:
    ref = source_ref.lower()
    text = content.lower().replace(" ", "")
    spaced_text = content.lower()
    logout_query = "logout" in query or "sign out" in query or "sign-out" in query
    authorization_query = "authorization" in query or "authorisation" in query or "permission" in query

    if logout_query:
        if ref.endswith("frontend/src/lib/auth.ts") and "clearauth" in text:
            return 0
        if "pageshell.tsx" in ref and ("handlelogout" in text or "clearauth" in text):
            return 1
        if ref.endswith("frontend/src/lib/auth.ts") and "setsessiontokens" in text:
            return 2
        if "authrefresh.ts" in ref and "performtokenrefresh" in text:
            return 3
        if ref.endswith("/routes/auth.py") or ref.endswith("/api/v1/routes/auth.py"):
            if "async def refresh_tokens" in spaced_text:
                return 4
            if "async def login" in spaced_text:
                return 5
        if ref.endswith("/core/auth.py") and "decode_refresh_token" in spaced_text:
            return 6
        if "testauthflow" in text or "test_register_and_login" in text:
            return 8
        return 100

    if ref.endswith("/core/auth.py") and "get_current_user" in spaced_text:
        return 0
    if authorization_query and ("owner_id" in text or "depends(get_current_user)" in text):
        if "/routes/projects.py" in ref:
            return 1
        if "/routes/project_team.py" in ref:
            return 2
        if "/routes/" in ref:
            return 3
    if ref.endswith("/routes/auth.py") or ref.endswith("/api/v1/routes/auth.py"):
        if "async def login" in spaced_text:
            return 4 if authorization_query else 1
        if "async def register" in spaced_text:
            return 5 if authorization_query else 2
        if "async def refresh_tokens" in spaced_text:
            return 6 if authorization_query else 3
        if "async def me" in spaced_text:
            return 4
        if "module:" in spaced_text:
            return 5 if authorization_query else 5
    if ref.endswith("/core/auth.py"):
        if "create_access_token" in spaced_text:
            return 7 if authorization_query else 6
        if "create_refresh_token" in spaced_text:
            return 8 if authorization_query else 7
        if "decode_access_token" in spaced_text:
            return 9 if authorization_query else 8
        if "decode_refresh_token" in spaced_text:
            return 10 if authorization_query else 9
        if "module:" in spaced_text:
            return 10
    if "loginpage.tsx" in ref and ("authapi.login" in text or "setsessiontokens" in text):
        return 11
    if ref.endswith("frontend/src/lib/api.ts") and "authapi" in text:
        return 12
    if ref.endswith("frontend/src/app.tsx") and "protectedroute" in text:
        return 13
    if ref.endswith("frontend/src/lib/auth.ts"):
        if "setsessiontokens" in text:
            return 14
        if "clearauth" in text:
            return 15
        if "isaccesstokenvalid" in text or "isrefreshtokenvalid" in text:
            return 16
        if "module:" in spaced_text:
            return 17
    if "authrefresh.ts" in ref and "performtokenrefresh" in text:
        return 18
    if "sessiongate.tsx" in ref or "tokenrefreshscheduler.tsx" in ref:
        return 19
    if "app.tsx" in ref and "protectedroute" in text:
        return 20
    return 100


def _pin_feature_chunks(
    chunks: list[dict[str, Any]],
    feature_chunks: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    if not feature_chunks:
        return chunks[:top_k]

    by_id: dict[str, dict[str, Any]] = {}
    for chunk in feature_chunks + chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        if chunk_id and chunk_id not in by_id:
            by_id[chunk_id] = chunk
    ordered = list(by_id.values())
    return ordered[:top_k]


def _query_has_auth_hint(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in _AUTH_QUERY_HINTS)


def _query_has_engine_hint(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in _ENGINE_QUERY_HINTS)


async def _safe_rollback(db: AsyncSession) -> None:
    rollback = getattr(db, "rollback", None)
    if rollback is None:
        return
    result = rollback()
    if inspect.isawaitable(result):
        await result


def _prune_low_signal_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pruned: list[dict[str, Any]] = []
    memory_budget = 1
    meta_doc_budget = 1
    for candidate in candidates:
        source_ref = str(candidate.get("source_ref") or "")
        lowered_ref = source_ref.lower()
        chunk_type = _chunk_type_name(candidate)
        if source_ref.startswith("__memory__/") and chunk_type in {
            "memory_brief",
            "feature_summary",
            "auth_flow",
            "onboarding_map",
            "decision_record",
        }:
            if memory_budget <= 0:
                continue
            memory_budget -= 1
        elif _is_meta_doc_path(lowered_ref):
            if meta_doc_budget <= 0:
                continue
            meta_doc_budget -= 1
        pruned.append(candidate)
    return pruned


def _is_code_backed_candidate(candidate: dict[str, Any]) -> bool:
    chunk_type = _chunk_type_name(candidate)
    if chunk_type in {"code_snippet", "module_description", "feature_description"}:
        source_ref = str(candidate.get("source_ref") or "")
        return not source_ref.startswith("__memory__/")
    return False


def _chunk_type_name(candidate: dict[str, Any]) -> str:
    chunk_type = candidate.get("chunk_type")
    if hasattr(chunk_type, "value"):
        return str(chunk_type.value)
    return str(chunk_type)


def _is_meta_doc_path(lowered_ref: str) -> bool:
    return (
        lowered_ref.endswith("agents.md")
        or lowered_ref.endswith("claude.md")
        or lowered_ref.endswith(".docx")
        or "/templates/" in lowered_ref
        or lowered_ref.startswith("guides/")
        or lowered_ref.startswith("community_contributions/")
    )


async def retrieve_for_twin(
    query: str,
    doctwin_id: str,
    allow_code_snippets: bool,
    db: AsyncSession,
    top_k: int = 8,
    intent: QueryIntent | None = None,
    path_hints: list[str] | None = None,
    guaranteed_refs: list[str] | None = None,
    expanded_query: str = "",
) -> list[dict]:
    packet = await retrieve_packet_for_twin(
        query=query,
        doctwin_id=doctwin_id,
        allow_code_snippets=allow_code_snippets,
        db=db,
        top_k=top_k,
        intent=intent,
        path_hints=path_hints,
        guaranteed_refs=guaranteed_refs,
        expanded_query=expanded_query,
    )
    return packet.chunks


async def route_and_retrieve_packet_for_workspace(
    query: str,
    workspace_id: str,
    db: AsyncSession,
    top_k: int = 8,
    intent: QueryIntent | None = None,
    path_hints: list[str] | None = None,
    expanded_query: str = "",
) -> tuple[str | None, RetrievalEvidencePacket]:
    """
    For workspace-level chat: identify the most relevant twin, then retrieve.

    Strategy:
    1. Embed the query
    2. Run pgvector search across all chunks in the workspace
    3. Group by doctwin_id and pick the twin with the highest average top-3 score
    4. Retrieve top_k chunks from that twin (code snippets excluded at workspace level)

    Returns (routed_doctwin_id, evidence_packet).
    """
    effective_intent = intent or QueryIntent.general
    plan = build_retrieval_plan(
        query=query,
        intent=effective_intent,
        expanded_query=expanded_query,
        path_hints=path_hints,
        top_k=top_k,
        workspace_scope=True,
    )
    if path_hints:
        structure_doctwin_id = await _route_by_structure(workspace_id, path_hints, db)
        if structure_doctwin_id:
            inventory = await _load_structure_inventory(structure_doctwin_id, db)
            guaranteed_refs = _resolve_refs_from_inventory(path_hints, inventory)
            allow_code_snippets = await _load_doctwin_allow_code_snippets(structure_doctwin_id, db)
            packet = await retrieve_packet_for_twin(
                query=query,
                doctwin_id=structure_doctwin_id,
                allow_code_snippets=allow_code_snippets,
                db=db,
                top_k=top_k,
                intent=effective_intent,
                path_hints=path_hints,
                guaranteed_refs=guaranteed_refs,
                expanded_query=expanded_query,
            )
            logger.info(
                "routing_complete",
                workspace_id=workspace_id,
                routed_doctwin_id=structure_doctwin_id,
                chunks_returned=len(packet.chunks),
                routing_method="structure",
            )
            packet.workspace_id = workspace_id
            return structure_doctwin_id, packet

    profiles = await _load_workspace_embedding_profiles(workspace_id, db)
    if not profiles:
        logger.info(
            "routing_no_match",
            workspace_id=workspace_id,
            query_length=len(query),
        )
        return None, build_evidence_packet(
            plan=plan,
            chunks=[],
            doctwin_id=None,
            workspace_id=workspace_id,
            missing_evidence=["no_embedding_profiles"],
        )

    use_reranker = reranker_available()
    fetch_k = (
        min(plan.rerank_budget, _RERANK_MAX_CANDIDATES)
        if use_reranker
        else max(top_k, 12)
    )
    candidates_by_id: dict[str, dict[str, Any]] = {}

    for profile in profiles:
        try:
            query_embedding = await embed_text_with_profile(plan.search_query, profile, task="query", db=db)
        except Exception as exc:
            logger.error(
                "routing_embed_failed",
                workspace_id=workspace_id,
                provider=profile.provider,
                model=profile.model,
                error=str(exc),
            )
            continue

        embedding_literal = _format_embedding(query_embedding)
        try:
            rows = await _fetch_workspace_candidates_for_profile(
                db=db,
                workspace_id=workspace_id,
                embedding_literal=embedding_literal,
                profile=profile,
                top_k=fetch_k,
            )
        except Exception as exc:
            logger.error(
                "routing_query_failed",
                workspace_id=workspace_id,
                provider=profile.provider,
                model=profile.model,
                error=str(exc),
            )
            await db.rollback()
            continue

        for row in rows:
            merge_candidate(
                candidates_by_id,
                {
                    "chunk_id": str(row.id),
                    "content": row.content,
                    "chunk_type": row.chunk_type,
                    "source_ref": row.source_ref,
                    "score": float(row.score),
                    "doctwin_id": str(row.doctwin_id),
                    "match_reasons": ["vector"],
                },
            )

    lexical_candidates = await _fetch_workspace_lexical_candidates(
        db=db,
        workspace_id=workspace_id,
        lexical_query=plan.lexical_query,
        limit=plan.lexical_budget,
    )
    for candidate in lexical_candidates:
        merge_candidate(candidates_by_id, candidate)

    if not candidates_by_id:
        logger.info(
            "routing_no_match",
            workspace_id=workspace_id,
            query_length=len(query),
        )
        return None, build_evidence_packet(
            plan=plan,
            chunks=[],
            doctwin_id=None,
            workspace_id=workspace_id,
            missing_evidence=["no_workspace_candidates"],
        )

    combined_candidates = sorted(
        candidates_by_id.values(),
        key=lambda item: item["score"],
        reverse=True,
    )
    if use_reranker:
        ranked_candidates = await rerank_chunks(
            plan.search_query,
            combined_candidates[:fetch_k],
            min(len(combined_candidates), fetch_k),
        )
    else:
        ranked_candidates = combined_candidates[:fetch_k]

    doctwin_scores: dict[str, list[float]] = {}
    for candidate in ranked_candidates:
        doctwin_scores.setdefault(str(candidate["doctwin_id"]), []).append(float(candidate["score"]))

    routed_doctwin_id = max(
        doctwin_scores,
        key=lambda tid: sum(doctwin_scores[tid][:3]) / len(doctwin_scores[tid][:3]),
    )
    inventory = await _load_structure_inventory(routed_doctwin_id, db)
    guaranteed_refs = _resolve_refs_from_inventory(path_hints or [], inventory)
    allow_code_snippets = await _load_doctwin_allow_code_snippets(routed_doctwin_id, db)

    # Step 2: Retrieve from the selected twin (no code snippets at workspace level)
    packet = await retrieve_packet_for_twin(
        query=query,
        doctwin_id=routed_doctwin_id,
        allow_code_snippets=allow_code_snippets,
        db=db,
        top_k=top_k,
        intent=effective_intent,
        path_hints=path_hints,
        guaranteed_refs=guaranteed_refs,
        expanded_query=expanded_query,
    )
    packet.workspace_id = workspace_id

    logger.info(
        "routing_complete",
        workspace_id=workspace_id,
        routed_doctwin_id=routed_doctwin_id,
        chunks_returned=len(packet.chunks),
        routing_method="embedding",
    )
    return routed_doctwin_id, packet


async def route_and_retrieve_for_workspace(
    query: str,
    workspace_id: str,
    db: AsyncSession,
    top_k: int = 8,
    intent: QueryIntent | None = None,
    path_hints: list[str] | None = None,
    expanded_query: str = "",
) -> tuple[str | None, list[dict]]:
    routed_doctwin_id, packet = await route_and_retrieve_packet_for_workspace(
        query=query,
        workspace_id=workspace_id,
        db=db,
        top_k=top_k,
        intent=intent,
        path_hints=path_hints,
        expanded_query=expanded_query,
    )
    return routed_doctwin_id, packet.chunks


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _format_embedding(embedding: list[float]) -> str:
    """Format a float list as a PostgreSQL vector literal: '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


async def _load_doctwin_embedding_profiles(
    doctwin_id: str,
    db: AsyncSession,
) -> list[EmbeddingProfile]:
    result = await db.execute(
        select(
            Source.embedding_provider,
            Source.embedding_model,
            Source.embedding_dimensions,
        )
        .join(Chunk, Chunk.source_id == Source.id)
        .where(
            Source.doctwin_id == uuid.UUID(doctwin_id),
            Source.status == SourceStatus.ready,
            Chunk.embedding.is_not(None),
        )
        .distinct()
    )
    return _rows_to_profiles(result.fetchall())


async def _load_workspace_embedding_profiles(
    workspace_id: str,
    db: AsyncSession,
) -> list[EmbeddingProfile]:
    result = await db.execute(
        select(
            Source.embedding_provider,
            Source.embedding_model,
            Source.embedding_dimensions,
        )
        .join(Twin, Twin.id == Source.doctwin_id)
        .join(Chunk, Chunk.source_id == Source.id)
        .where(
            Twin.workspace_id == uuid.UUID(workspace_id),
            Source.status == SourceStatus.ready,
            Chunk.embedding.is_not(None),
        )
        .distinct()
    )
    return _rows_to_profiles(result.fetchall())


async def _load_doctwin_allow_code_snippets(
    doctwin_id: str,
    db: AsyncSession,
) -> bool:
    result = await db.execute(
        select(TwinConfig.allow_code_snippets).where(
            TwinConfig.doctwin_id == uuid.UUID(doctwin_id)
        )
    )
    return bool(result.scalar_one_or_none())


def _rows_to_profiles(rows: list[Any]) -> list[EmbeddingProfile]:
    profiles: list[EmbeddingProfile] = []
    primary = get_primary_embedding_profile()
    seen: set[tuple[str, str, int]] = set()
    for row in rows:
        profile = resolve_embedding_profile(
            getattr(row, "embedding_provider", None) or primary.provider,
            getattr(row, "embedding_model", None) or primary.model,
            getattr(row, "embedding_dimensions", None) or primary.dimensions,
            use_default_model=True,
        )
        key = (profile.provider, profile.model, profile.dimensions)
        if key in seen:
            continue
        seen.add(key)
        profiles.append(profile)
    return profiles


def _profile_query_params(profile: EmbeddingProfile) -> dict[str, Any]:
    primary = get_primary_embedding_profile()
    return {
        "profile_provider": profile.provider,
        "profile_model": profile.model,
        "profile_dimensions": profile.dimensions,
        "legacy_provider": primary.provider,
        "legacy_model": primary.model,
        "legacy_dimensions": primary.dimensions,
    }


async def _fetch_doctwin_candidates_for_profile(
    *,
    db: AsyncSession,
    doctwin_id: str,
    embedding_literal: str,
    profile: EmbeddingProfile,
    code_filter: str,
    boost_sql: str,
    top_k: int,
) -> list[Any]:
    sql = text(
        f"""
        SELECT
            c.id,
            c.content,
            c.chunk_type,
            c.source_ref,
            (1 - (c.embedding <=> :embedding ::vector)){boost_sql} AS score
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE s.doctwin_id = :doctwin_id
          AND s.status = 'ready'
          AND c.embedding IS NOT NULL
          AND COALESCE(s.embedding_provider, :legacy_provider) = :profile_provider
          AND COALESCE(s.embedding_model, :legacy_model) = :profile_model
          AND COALESCE(s.embedding_dimensions, :legacy_dimensions) = :profile_dimensions
          {code_filter}
          AND 1 - (c.embedding <=> :embedding ::vector) >= :min_score
        ORDER BY (1 - (c.embedding <=> :embedding ::vector)){boost_sql} DESC
        LIMIT :top_k
        """
    )
    params = {
        "embedding": embedding_literal,
        "doctwin_id": str(doctwin_id),
        "min_score": _MIN_SCORE,
        "top_k": top_k,
        **_profile_query_params(profile),
    }
    result = await db.execute(sql, params)
    return result.fetchall()


async def _fetch_workspace_candidates_for_profile(
    *,
    db: AsyncSession,
    workspace_id: str,
    embedding_literal: str,
    profile: EmbeddingProfile,
    top_k: int,
) -> list[Any]:
    sql = text(
        """
        SELECT
            c.id,
            c.content,
            c.chunk_type,
            c.source_ref,
            s.doctwin_id,
            1 - (c.embedding <=> :embedding ::vector) AS score
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        JOIN twins t ON t.id = s.doctwin_id
        WHERE t.workspace_id = :workspace_id
          AND s.status = 'ready'
          AND c.embedding IS NOT NULL
          AND c.chunk_type != 'code_snippet'
          AND COALESCE(s.embedding_provider, :legacy_provider) = :profile_provider
          AND COALESCE(s.embedding_model, :legacy_model) = :profile_model
          AND COALESCE(s.embedding_dimensions, :legacy_dimensions) = :profile_dimensions
          AND 1 - (c.embedding <=> :embedding ::vector) >= :min_score
        ORDER BY c.embedding <=> :embedding ::vector
        LIMIT :top_k
        """
    )
    params = {
        "embedding": embedding_literal,
        "workspace_id": str(workspace_id),
        "min_score": _MIN_SCORE,
        "top_k": top_k,
        **_profile_query_params(profile),
    }
    result = await db.execute(sql, params)
    return result.fetchall()


async def _fetch_workspace_lexical_candidates(
    *,
    db: AsyncSession,
    workspace_id: str,
    lexical_query: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not lexical_query.strip():
        return []

    sql = text(
        """
        WITH lexical_query AS (
            SELECT websearch_to_tsquery('simple', :query) AS q
        )
        SELECT
            c.id,
            c.content,
            c.chunk_type,
            c.source_ref,
            s.doctwin_id,
            LEAST(
                0.95,
                0.35 + ts_rank_cd(
                    setweight(to_tsvector('simple', COALESCE(c.source_ref, '')), 'A') ||
                    setweight(to_tsvector('simple', COALESCE(c.content, '')), 'B'),
                    lexical_query.q
                )
            ) AS score
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        JOIN twins t ON t.id = s.doctwin_id
        CROSS JOIN lexical_query
        WHERE t.workspace_id = :workspace_id
          AND s.status = 'ready'
          AND c.chunk_type != 'code_snippet'
          AND lexical_query.q <> ''::tsquery
          AND (
            setweight(to_tsvector('simple', COALESCE(c.source_ref, '')), 'A') ||
            setweight(to_tsvector('simple', COALESCE(c.content, '')), 'B')
          ) @@ lexical_query.q
        ORDER BY score DESC
        LIMIT :limit
        """
    )
    try:
        result = await db.execute(
            sql,
            {
                "query": lexical_query,
                "workspace_id": workspace_id,
                "limit": limit,
            },
        )
    except Exception as exc:
        logger.warning("workspace_lexical_search_failed", workspace_id=workspace_id, error=str(exc))
        await db.rollback()
        return []

    return [
        {
            "chunk_id": str(row.id),
            "content": row.content,
            "chunk_type": row.chunk_type,
            "source_ref": row.source_ref,
            "doctwin_id": str(row.doctwin_id),
            "score": float(row.score),
            "match_reasons": ["lexical"],
        }
        for row in result.fetchall()
    ]


async def _fetch_supporting_memory_chunks(
    *,
    db: AsyncSession,
    doctwin_id: str,
    mode: RetrievalMode,
) -> list[dict[str, Any]]:
    if mode == RetrievalMode.onboarding:
        chunk_types = ["onboarding_map"]
    elif mode == RetrievalMode.change_review:
        chunk_types = ["change_entry"]
    elif mode == RetrievalMode.risk_review:
        chunk_types = ["risk_note"]
    elif mode == RetrievalMode.project_status:
        chunk_types = ["change_entry", "risk_note"]
    else:
        return []

    sql = text(
        """
        SELECT c.id, c.content, c.chunk_type, c.source_ref, c.metadata AS chunk_metadata
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE s.doctwin_id = :doctwin_id
          AND s.status = 'ready'
          AND c.source_ref LIKE '__memory__/%'
          AND c.chunk_type = ANY(:chunk_types)
        ORDER BY c.created_at DESC
        LIMIT 2
        """
    )
    try:
        result = await db.execute(
            sql,
            {
                "doctwin_id": str(doctwin_id),
                "chunk_types": chunk_types,
            },
        )
    except Exception as exc:
        logger.warning("supporting_memory_chunk_fetch_failed", doctwin_id=doctwin_id, error=str(exc))
        await db.rollback()
        return []

    return [
        {
            "chunk_id": str(row.id),
            "content": row.content,
            "chunk_type": row.chunk_type,
            "source_ref": row.source_ref,
            "chunk_metadata": row.chunk_metadata,
            "score": 0.32,
            "match_reasons": ["memory"],
        }
        for row in result.fetchall()
    ]


async def _load_structure_inventory(doctwin_id: str, db: AsyncSession) -> dict:
    """
    Load a merged structure inventory for all ready sources attached to a twin.

    Falls back to deriving the inventory from chunk source_refs when no source
    has a persisted structure_index yet.
    """
    result = await db.execute(
        select(Source.structure_index)
        .where(
            Source.doctwin_id == uuid.UUID(doctwin_id),
            Source.status == SourceStatus.ready,
            Source.name != "__memory__",
        )
    )
    indexes = [row.structure_index for row in result.fetchall() if row.structure_index]

    if indexes:
        merged_dirs: dict[str, set[str]] = {}
        total_files: set[str] = set()
        for index in indexes:
            for dir_path, paths in (index.get("meaningful_dirs") or {}).items():
                bucket = merged_dirs.setdefault(str(dir_path), set())
                bucket.update(str(path) for path in paths if path)
                total_files.update(str(path) for path in paths if path)
        return {
            "schema_version": max(
                int(index.get("schema_version", 1)) for index in indexes
            ),
            "meaningful_dirs": {
                dir_path: sorted(paths)
                for dir_path, paths in sorted(
                    merged_dirs.items(),
                    key=lambda item: (_dir_depth(item[0]), item[0]),
                )
            },
            "total_files": len(total_files),
            "generated_at": None,
            "is_partial": False,
        }

    fallback_result = await db.execute(
        select(Chunk.source_ref)
        .join(Source, Chunk.source_id == Source.id)
        .where(
            Source.doctwin_id == uuid.UUID(doctwin_id),
            Source.status == SourceStatus.ready,
            Chunk.source_ref.is_not(None),
            Chunk.source_ref.not_like("__memory__%"),
        )
    )
    file_paths = [str(row.source_ref) for row in fallback_result.fetchall() if row.source_ref]
    grouped = _group_paths_by_parent(file_paths)
    return {
        "schema_version": 1,
        "meaningful_dirs": grouped,
        "total_files": len({path for path in file_paths if path}),
        "generated_at": None,
        "is_partial": True,
    }


def _resolve_refs_from_inventory(path_hints: list[str], inventory: dict) -> list[str]:
    """
    Resolve query path hints against a structure inventory.

    Returns matched directory keys and exact file path prefixes that exist in
    the inventory. Matching is case-insensitive and ignores spaces.
    """
    meaningful_dirs = inventory.get("meaningful_dirs") or {}
    resolved: list[tuple[int, str]] = []
    seen: set[str] = set()

    for hint in path_hints:
        normalised_hint = _normalise_structure_key(hint)
        if not normalised_hint:
            continue

        matched_dir = False
        for dir_path, _file_paths in meaningful_dirs.items():
            normalised_dir = _normalise_structure_key(dir_path)
            if _matches_structure_hint(normalised_hint, normalised_dir):
                if dir_path not in seen:
                    resolved.append((0, dir_path))
                    seen.add(dir_path)
                matched_dir = True

        if matched_dir:
            continue

        for _dir_path, file_paths in meaningful_dirs.items():
            for file_path in file_paths:
                normalised_file = _normalise_structure_key(file_path)
                if (_matches_structure_hint(normalised_hint, normalised_file) or (
                    len(normalised_hint) >= 4 and normalised_hint in normalised_file
                )) and file_path not in seen:
                    resolved.append((1, file_path))
                    seen.add(file_path)

    resolved.sort(key=lambda item: (item[0], _dir_depth(item[1]), item[1]))
    return [ref for _, ref in resolved]


async def _route_by_structure(
    workspace_id: str,
    path_hints: list[str],
    db: AsyncSession,
) -> str | None:
    """
    Route to a twin by deterministic structure match before embedding routing.
    """
    result = await db.execute(
        select(Source.doctwin_id, Source.structure_index)
        .join(Twin, Twin.id == Source.doctwin_id)
        .where(
            Twin.workspace_id == uuid.UUID(workspace_id),
            Source.status == SourceStatus.ready,
            Source.name != "__memory__",
            Source.structure_index.is_not(None),
        )
    )

    matched_twins: set[str] = set()
    for row in result.fetchall():
        inventory = row.structure_index or {}
        matched_refs = _resolve_refs_from_inventory(path_hints, inventory)
        if matched_refs:
            matched_twins.add(str(row.doctwin_id))

    if len(matched_twins) == 1:
        doctwin_id = next(iter(matched_twins))
        logger.info(
            "structure_routing_matched",
            workspace_id=workspace_id,
            doctwin_id=doctwin_id,
            path_hints=path_hints,
        )
        return doctwin_id

    if len(matched_twins) > 1:
        logger.info(
            "structure_routing_ambiguous",
            workspace_id=workspace_id,
            doctwin_ids=sorted(matched_twins),
            path_hints=path_hints,
        )
    return None


async def _fetch_by_path_prefix(
    path_hint: str,
    embedding_literal: str | None,
    doctwin_id: str,
    db: AsyncSession,
    allow_code_snippets: bool = True,
    limit: int = 4,
) -> list[dict]:
    """
    Fetch the top `limit` chunks whose source_ref starts with `path_hint`.

    Used as a supplemental fetch when the user's query explicitly mentions a
    directory/section name (e.g. "week3", "finale"). This guarantees those
    chunks appear in the retrieved context even if there are very few of them
    and they're outranked by high-density sections in the main vector search.

    path_hint is a normalised lowercase prefix like "week3" or "finale".
    The SQL matches both exact paths ("week3/README.md") and subdirectory
    paths ("week3/day1.md") by using LIKE 'week3%'.

    Intentionally does NOT filter out chunks with NULL embeddings — path-hint
    retrieval is a path-based lookup, not a similarity search. Chunks that
    failed to embed during ingestion must still be reachable this way.
    Embedded chunks are ranked by cosine similarity; un-embedded chunks receive
    a neutral score (0.5) and sort after embedded ones.
    """
    code_filter = "" if allow_code_snippets else "AND c.chunk_type != 'code_snippet'"
    has_embedding = embedding_literal is not None
    score_sql = (
        "COALESCE(1 - (c.embedding <=> :embedding ::vector), 0.5)"
        if has_embedding
        else "0.5"
    )
    order_sql = (
        """
            CASE WHEN c.embedding IS NULL THEN 1 ELSE 0 END,
            c.embedding <=> :embedding ::vector
        """
        if has_embedding
        else "lower(c.source_ref)"
    )
    sql = text(
        f"""
        SELECT
            c.id,
            c.content,
            c.chunk_type,
            c.source_ref,
            {score_sql} AS score
        FROM chunks c
        JOIN sources s ON s.id = c.source_id
        WHERE s.doctwin_id = :doctwin_id
          AND s.status = 'ready'
          AND lower(c.source_ref) LIKE :prefix
          {code_filter}
        ORDER BY {order_sql}
        LIMIT :limit
        """
    )
    try:
        result = await db.execute(
            sql,
            {
                "embedding": embedding_literal,
                "doctwin_id": str(doctwin_id),
                "prefix": f"{path_hint.lower()}%",
                "limit": limit,
            },
        )
        rows = result.fetchall()
    except Exception as exc:
        logger.warning("retrieval_path_fetch_failed", path_hint=path_hint, error=str(exc))
        await db.rollback()
        return []

    chunks = [
        {
            "chunk_id": str(row.id),
            "content": row.content,
            "chunk_type": row.chunk_type,
            "source_ref": row.source_ref,
            "score": float(row.score),
        }
        for row in rows
    ]
    logger.debug(
        "retrieval_path_prefix_fetch",
        doctwin_id=doctwin_id,
        path_hint=path_hint,
        found=len(chunks),
        sources=[c["source_ref"] for c in chunks],
    )
    return chunks


def _group_paths_by_parent(file_paths: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = {}
    for raw_path in file_paths:
        path = raw_path.strip("/")
        if not path:
            continue
        pure_path = PurePosixPath(path)
        parts = pure_path.parts
        if len(parts) <= 1:
            grouped.setdefault("_root", set()).add(path)
            continue
        parent = "/".join(parts[:-1])
        grouped.setdefault(parent, set()).add(path)

    return {
        dir_path: sorted(paths)
        for dir_path, paths in sorted(
            grouped.items(),
            key=lambda item: (_dir_depth(item[0]), item[0]),
        )
    }


def _normalise_structure_key(value: str) -> str:
    return value.lower().replace(" ", "")


def _matches_structure_hint(normalised_hint: str, normalised_target: str) -> bool:
    return (
        normalised_target == normalised_hint
        or normalised_target.startswith(normalised_hint)
    )


def _dir_depth(ref: str) -> int:
    if not ref or ref == "_root":
        return 0
    return len(PurePosixPath(ref).parts)
