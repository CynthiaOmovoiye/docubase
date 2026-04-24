"""
Chat domain service.

Handles chat session creation, message sending, and history retrieval.

Architecture notes:
- Sessions are anchored to a workspace. Twin is optional (null = workspace-wide routing).
- Answer generation is grounded in retrieved context and/or a ready Memory Brief.
- When neither exists, chat falls back to a deterministic no-knowledge response.
- Message history is persisted for auditability and multi-turn context.
- Streaming responses are supported via async generators.
- Public (anonymous) sessions are allowed for share surfaces.

Security:
- Authenticated sessions verify workspace/twin ownership.
- Public sessions verify the share surface slug is active.
- All context chunks go through policy + retrieval filtering before reaching the LLM.
- Context chunk IDs are stored on each Message for auditability.

Observability:
- Each send_message call creates a Langfuse trace (when configured).
- The trace carries retrieval metadata and links to the LLM generation span.
- When ``chat_quality_gate_enabled`` is false, a passive LLM-as-judge may still run
  after persist for dimensional scores. When the gate is enabled, an active judge
  runs before persist (bounded regeneration).
"""

import asyncio
import re
import uuid
from dataclasses import dataclass
from time import perf_counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.observability import get_langfuse
from app.domains.chat.routing_heuristics import (
    WORKSPACE_ROUTE_ALIAS_STOPWORDS as _WORKSPACE_ROUTE_ALIAS_STOPWORDS,
    query_prefers_workspace_aggregate_over_single_twin as _workspace_query_prefers_aggregate_over_single_twin,
)
from app.domains.answering.generator import generate_answer, generate_workspace_answer
from app.domains.answering.llm_provider import LLMResponse
from app.domains.answering.verifier import (
    verify_single_project_answer,
    verify_workspace_answer,
)
from app.domains.evaluation.answer_authority import build_answer_authority_diagnosis
from app.domains.evaluation.latency import build_chat_latency_report
from app.domains.evaluation.metrics import (
    build_single_project_quality_metrics,
    build_workspace_quality_metrics,
)
from app.domains.memory.service import get_workspace_synthesis
from app.domains.retrieval.intent import QueryAnalysis, QueryIntent, analyse_query
from app.domains.retrieval.router import (
    _load_structure_inventory,
    _resolve_refs_from_inventory,
    retrieve_packet_for_twin,
    route_and_retrieve_packet_for_workspace,
)
from app.models.chat import ChatSession, Message, MessageRole
from app.models.sharing import ShareSurface
from app.models.source import Source, SourceStatus
from app.models.twin import Twin, TwinConfig
from app.models.workspace import Workspace

logger = get_logger(__name__)

# Maximum number of history turns included in the LLM context
_MAX_HISTORY_TURNS = 10
# Hard character cap across all history messages (~3K tokens at 4 chars/token).
# Oldest turns are dropped first when over budget. Individual messages longer
# than _MAX_MESSAGE_CHARS are truncated to prevent one turn monopolising context.
_MAX_HISTORY_CHARS = 12_000
_MAX_MESSAGE_CHARS = 2_000


def _session_belongs_to_surface(session: ChatSession, surface: ShareSurface) -> bool:
    """True if this chat session was created for the given public share surface."""
    if surface.doctwin_id is not None:
        return session.doctwin_id == surface.doctwin_id
    if surface.workspace_id is None:
        return False
    return session.workspace_id == surface.workspace_id and session.doctwin_id is None


# Context chunks for focused questions (default)
_CONTEXT_CHUNKS_FOCUSED = 8
# Context chunks for broad overview questions — more context = richer answers
_CONTEXT_CHUNKS_BROAD = 16

# Patterns that indicate a broad / overview question.
# These get more retrieval context so the LLM can produce comprehensive responses.
_BROAD_QUERY_RE = re.compile(
    r"\b("
    r"tell me about|what is|what are|what does|what do|"
    r"overview|explain|describe|summarize|summarise|"
    r"walk me through|give me|show me|how does|how do|"
    r"who are|who is|why does|why is|what can|introduce"
    r")\b",
    re.IGNORECASE,
)

_HEDGE_RE = re.compile(
    r"\b(I don'?t have|I don'?t know|no information about|not have specific|"
    r"only covers? (week|month|chapter|section)|I can'?t find|"
    r"not available in|outside (of )?my knowledge|no data about)\b",
    re.IGNORECASE,
)
_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|hiya|yo|good\s+(morning|afternoon|evening))\b",
    re.IGNORECASE,
)
_SOURCE_QUERY_RE = re.compile(
    r"\b("
    r"what do you have|what sources?|which sources?|do you have|"
    r"what do you know|what knowledge|attached sources?"
    r")\b",
    re.IGNORECASE,
)
_WORKSPACE_COVERAGE_RE = re.compile(
    r"\b("
    r"how many twins|how many projects|which twins|which projects|"
    r"what twins|what projects|what can you help with|what can you cover|"
    r"what do you cover|what are you serving|what projects can you help with"
    r")\b",
    re.IGNORECASE,
)
_ANY_PROJECT_RE = re.compile(
    r"\b(any of|any one|one of|pick any|pick one|either one|whichever)\b",
    re.IGNORECASE,
)

_AUTH_TOPIC_RE = re.compile(
    r"\b(auth|authentication|login|sign.?in|sign.?up|jwt|oauth|sso|session)\b",
    re.IGNORECASE,
)


def _is_broad_query(query: str) -> bool:
    """
    Detect whether a query is asking for a broad overview vs a specific fact.

    Broad queries get more retrieval context (top_k=16 vs 8) so the LLM has
    enough material to produce a comprehensive structured response.
    """
    stripped = query.strip()
    # Very short queries without a verb are almost always broad ("this project",
    # "the architecture", etc.)
    if len(stripped.split()) <= 5:
        return True
    return bool(_BROAD_QUERY_RE.search(stripped))


def _is_greeting(query: str) -> bool:
    return bool(_GREETING_RE.search(query.strip()))


def _is_source_query(query: str) -> bool:
    return bool(_SOURCE_QUERY_RE.search(query.strip()))


def _is_workspace_coverage_query(query: str) -> bool:
    return bool(_WORKSPACE_COVERAGE_RE.search(query.strip()))


def _is_any_project_query(query: str) -> bool:
    return bool(_ANY_PROJECT_RE.search(query.strip()))


class NotFoundError(Exception):
    pass


class ForbiddenError(Exception):
    pass


# ─── Session creation ─────────────────────────────────────────────────────────

async def create_doctwin_session(
    doctwin_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ChatSession:
    """
    Create a new chat session anchored to a specific twin.

    The twin must belong to a workspace owned by user_id.
    """
    twin = await _load_doctwin_with_workspace(doctwin_id, db)
    if twin is None:
        raise NotFoundError(f"Twin {doctwin_id} not found")
    if twin.workspace.owner_id != user_id:
        raise ForbiddenError("You do not own this twin's workspace")

    session = ChatSession(
        id=uuid.uuid4(),
        workspace_id=twin.workspace_id,
        doctwin_id=doctwin_id,
        user_id=user_id,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    logger.info("chat_session_created", session_id=str(session.id), doctwin_id=str(doctwin_id))
    return session


async def create_workspace_session(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ChatSession:
    """
    Create a new workspace-level chat session.

    Twin routing happens at message-send time.
    """
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise NotFoundError(f"Workspace {workspace_id} not found")
    if workspace.owner_id != user_id:
        raise ForbiddenError("You do not own this workspace")

    session = ChatSession(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        doctwin_id=None,
        user_id=user_id,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    logger.info(
        "chat_session_created",
        session_id=str(session.id),
        workspace_id=str(workspace_id),
    )
    return session


async def create_public_session(
    public_slug: str,
    db: AsyncSession,
    *,
    visitor_id: str | None = None,
) -> ChatSession:
    """
    Create an anonymous chat session via a public share surface.

    No authentication required. The share surface must be active.
    When ``visitor_id`` is set, the session can be listed and resumed with the same id.
    """
    surface = await _load_active_surface(public_slug, db)

    # Determine workspace_id and doctwin_id from the surface
    if surface.doctwin_id is not None:
        twin = await _load_doctwin_with_workspace(surface.doctwin_id, db)
        workspace_id = twin.workspace_id if twin else surface.workspace_id
        doctwin_id = surface.doctwin_id
    else:
        workspace_id = surface.workspace_id
        doctwin_id = None

    session = ChatSession(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        doctwin_id=doctwin_id,
        user_id=None,  # Anonymous
        visitor_id=visitor_id,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    logger.info(
        "public_chat_session_created",
        session_id=str(session.id),
        surface_slug=public_slug,
    )
    return session


# ─── Message sending ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class SendMessageResult:
    """Assistant turn plus optional Phase 0 answer diagnostics (API-controlled)."""

    message: Message
    answer_diagnostics: dict | None = None


async def send_message(
    session_id: uuid.UUID,
    content: str,
    user_id: uuid.UUID | None,
    db: AsyncSession,
    *,
    include_answer_diagnostics: bool = False,
) -> SendMessageResult:
    """
    Send a user message and generate an assistant response.

    Loads relevant context chunks, generates a grounded answer,
    and persists both the user message and assistant response.

    Returns ``SendMessageResult`` with the assistant ``Message`` and optional
    ``answer_diagnostics`` when ``include_answer_diagnostics`` is True.
    """
    session = await _load_session(session_id, db)
    _assert_session_access(session, user_id)

    # ── Open Langfuse trace for this message ───────────────────────────────────
    trace_id: str | None = None
    lf = get_langfuse()
    if lf:
        try:
            trace = lf.trace(
                name="chat_message",
                session_id=str(session_id),
                user_id=str(user_id) if user_id else "anonymous",
                input=content,
                metadata={
                    "doctwin_id": str(session.doctwin_id) if session.doctwin_id else None,
                    "workspace_id": str(session.workspace_id),
                },
            )
            trace_id = trace.id
        except Exception as exc:
            logger.warning("langfuse_trace_open_failed", error=str(exc))

    # Correlates structured RAG logs (retrieval stages → LLM chunks) in one request.
    pipeline_trace_id = str(uuid.uuid4())

    # Persist the user message
    user_message = Message(
        id=uuid.uuid4(),
        session_id=session_id,
        role=MessageRole.user,
        content=content,
        routed_doctwin_id=None,
        context_chunk_ids=[],
    )
    db.add(user_message)
    await db.flush()

    total_started_at = perf_counter()
    retrieval_elapsed_ms = 0.0
    generation_elapsed_ms = 0.0
    verification_elapsed_ms = 0.0
    quality_metrics = None
    verification = None
    answer_from_workspace_aggregate = False

    # Load twin config for policy decisions
    doctwin_config = await _load_doctwin_config(session.doctwin_id, db) if session.doctwin_id else None
    allow_code_snippets = doctwin_config.allow_code_snippets if doctwin_config else False
    doctwin_name = _get_doctwin_display_name(session, doctwin_config)
    custom_context = doctwin_config.custom_context if doctwin_config else None
    memory_brief_status_str: str | None = (
        doctwin_config.memory_brief_status if doctwin_config else None
    )

    # Load Memory Brief for unconditional injection into the system prompt.
    # Only inject when status is "ready" — never a partial/stale brief.
    memory_brief: str | None = None
    if doctwin_config and doctwin_config.memory_brief_status == "ready":
        memory_brief = doctwin_config.memory_brief

    # Analyse query intent for boosted retrieval (LLM, with regex fallback).
    # This runs before retrieval so intent + path_hints are available together.
    analysis: QueryAnalysis = await analyse_query(content)
    intent: QueryIntent = analysis.intent

    workspace_summary: dict | None = None
    workspace_scope_response: str | None = None
    workspace_scope_id: uuid.UUID | None = None
    if session.doctwin_id is None:
        workspace_scope_id = session.workspace_id
        workspace_summary = await _load_workspace_summary(workspace_scope_id, db)
        workspace_scope_response = _build_workspace_scope_response(content, workspace_summary)

    answer: LLMResponse | None = None
    used_deterministic_fallback = False

    if workspace_scope_response is not None:
        answer = LLMResponse(
            content=workspace_scope_response,
            model="deterministic-workspace-scope",
            input_tokens=0,
            output_tokens=0,
        )
        chunks: list[dict] = []
        retrieval_packet = None
        routed_doctwin_id: uuid.UUID | None = None
        source_list: list[dict] = []
        used_deterministic_fallback = True
        memory_brief = None
        doctwin_name = workspace_summary["workspace_name"] if workspace_summary else "this workspace"
    else:
        routed_doctwin_id = session.doctwin_id
        # top_k is now driven by intent; fall back to broad-query heuristic for
        # backward compatibility when the session has no specific twin.
        top_k = _CONTEXT_CHUNKS_FOCUSED  # default; intent override applied inside retrieve_for_twin
        inventory: dict | None = None
        guaranteed_refs: list[str] = []
        history = await _build_message_history(session_id, db)
        source_list = []
        retrieval_packet = None

        if session.doctwin_id is not None:
            inventory = await _load_structure_inventory(str(session.doctwin_id), db)
            guaranteed_refs = _resolve_refs_from_inventory(analysis.path_hints, inventory)
            retrieval_started_at = perf_counter()
            retrieval_packet = await retrieve_packet_for_twin(
                query=content,
                doctwin_id=str(session.doctwin_id),
                allow_code_snippets=allow_code_snippets,
                db=db,
                top_k=top_k,
                intent=intent,
                path_hints=analysis.path_hints,
                guaranteed_refs=guaranteed_refs,
                expanded_query=analysis.expanded_query,
                pipeline_trace_id=pipeline_trace_id,
            )
            retrieval_elapsed_ms += (perf_counter() - retrieval_started_at) * 1000
            chunks = retrieval_packet.chunks
        else:
            targeted_workspace_twin = _resolve_workspace_doctwin_from_query(content, workspace_summary or {})
            prefer_workspace_aggregate = _workspace_query_prefers_aggregate_over_single_twin(content)
            if (
                (targeted_workspace_twin is None or prefer_workspace_aggregate)
                and not _is_any_project_query(content)
            ):
                assert workspace_scope_id is not None
                answer, chunks, workspace_metrics = await _answer_across_workspace(
                    session=session,
                    workspace_id=workspace_scope_id,
                    query=content,
                    history=history,
                    analysis=analysis,
                    workspace_summary=workspace_summary or {},
                    db=db,
                    trace_id=trace_id,
                    pipeline_trace_id=pipeline_trace_id,
                )
                answer_from_workspace_aggregate = True
                retrieval_elapsed_ms += workspace_metrics["retrieval_ms"]
                generation_elapsed_ms += workspace_metrics["generation_ms"]
                verification_elapsed_ms += workspace_metrics["verification_ms"]
                quality_metrics = workspace_metrics["quality_metrics"]
                routed_doctwin_id = None
                source_list = []
                custom_context = None
                memory_brief = None
            else:
                # Workspace-level single-project path:
                # - named project => use that twin directly
                # - "any one" style query => pick the strongest single twin
                top_k_ws = _CONTEXT_CHUNKS_BROAD if _is_broad_query(content) else _CONTEXT_CHUNKS_FOCUSED
                if targeted_workspace_twin is not None:
                    routed_id_str = str(targeted_workspace_twin["id"])
                    doctwin_name = str(targeted_workspace_twin.get("name") or doctwin_name)
                    targeted_config = await _load_doctwin_config(uuid.UUID(routed_id_str), db)
                    retrieval_started_at = perf_counter()
                    retrieval_packet = await retrieve_packet_for_twin(
                        query=content,
                        doctwin_id=routed_id_str,
                        allow_code_snippets=bool(
                            targeted_config.allow_code_snippets if targeted_config else False
                        ),
                        db=db,
                        top_k=top_k_ws,
                        intent=intent,
                        path_hints=analysis.path_hints,
                        guaranteed_refs=_resolve_refs_from_inventory(
                            analysis.path_hints,
                            await _load_structure_inventory(routed_id_str, db),
                        ),
                        expanded_query=analysis.expanded_query,
                        pipeline_trace_id=pipeline_trace_id,
                    )
                    retrieval_elapsed_ms += (perf_counter() - retrieval_started_at) * 1000
                    chunks = retrieval_packet.chunks
                else:
                    retrieval_started_at = perf_counter()
                    routed_id_str, retrieval_packet = await route_and_retrieve_packet_for_workspace(
                        query=content,
                        workspace_id=str(workspace_scope_id),
                        db=db,
                        top_k=top_k_ws,
                        intent=intent,
                        path_hints=analysis.path_hints,
                        expanded_query=analysis.expanded_query,
                    )
                    retrieval_elapsed_ms += (perf_counter() - retrieval_started_at) * 1000
                    chunks = retrieval_packet.chunks

                if routed_id_str:
                    routed_doctwin_id = uuid.UUID(routed_id_str)
                    inventory = await _load_structure_inventory(routed_id_str, db)
                    guaranteed_refs = _resolve_refs_from_inventory(analysis.path_hints, inventory)
                    # Load the routed twin's config
                    routed_config = await _load_doctwin_config(routed_doctwin_id, db)
                    if routed_config:
                        doctwin_name = _get_doctwin_display_name(session, routed_config)
                        custom_context = routed_config.custom_context
                        if routed_config.memory_brief_status == "ready":
                            memory_brief = routed_config.memory_brief
            if answer is not None:
                used_deterministic_fallback = answer.model.startswith("deterministic-")

        # Log retrieval span to Langfuse
        if lf and trace_id:
            try:
                lf.span(
                    trace_id=trace_id,
                    name="retrieval",
                    input={
                        "query": content,
                        "top_k": top_k,
                        "intent": intent.value,
                        "path_hints": analysis.path_hints,
                        "guaranteed_refs": guaranteed_refs or None,
                        "expanded_query": analysis.expanded_query or None,
                        "broad_query": _is_broad_query(content),
                        "searched_layers": retrieval_packet.searched_layers if retrieval_packet else None,
                        "negative_evidence_scope": (
                            retrieval_packet.negative_evidence_scope if retrieval_packet else None
                        ),
                    },
                    output={"chunks_returned": len(chunks), "scores": [c.get("score") for c in chunks]},
                    metadata={
                        "doctwin_id": str(routed_doctwin_id) if routed_doctwin_id else None,
                        "retrieval_mode": retrieval_packet.mode.value if retrieval_packet else None,
                        "workspace_mode": (
                            "twin"
                            if session.doctwin_id is not None
                            else (
                                "aggregate"
                                if routed_doctwin_id is None and not source_list
                                else "single_project"
                            )
                        ),
                    },
                )
            except Exception as exc:
                logger.warning("langfuse_retrieval_span_failed", error=str(exc))

        if answer is None:
            # Load source list so the LLM knows what's attached to this twin.
            # This lets it correctly answer "do you have my resume?" without relying
            # solely on whether resume chunks happen to score highly for that query.
            source_list = source_list or await _load_sources_for_twin(routed_doctwin_id or session.doctwin_id, db)
            scope_name = (
                doctwin_name
                if (routed_doctwin_id is not None or session.doctwin_id is not None)
                else "this workspace"
            )
            fallback_response = _build_no_grounding_response(
                query=content,
                scope_name=scope_name,
                sources=source_list,
                has_context_chunks=bool(chunks),
                has_memory_brief=bool(memory_brief),
                is_workspace_scope=(routed_doctwin_id is None and session.doctwin_id is None),
            )

            used_deterministic_fallback = fallback_response is not None
            if fallback_response is not None:
                answer = LLMResponse(
                    content=fallback_response,
                    model="deterministic-fallback",
                    input_tokens=0,
                    output_tokens=0,
                )
            else:
                # Generate grounded answer — memory_brief injected into system prompt when ready
                generation_started_at = perf_counter()
                answer = await generate_answer(
                    doctwin_name=doctwin_name,
                    query=content,
                    context_chunks=chunks,
                    conversation_history=history,
                    custom_context=custom_context,
                    allow_code_snippets=allow_code_snippets,
                    trace_id=trace_id,
                    sources=source_list,
                    memory_brief=memory_brief,
                    retrieval_packet=retrieval_packet,
                    pipeline_trace_id=pipeline_trace_id,
                )
                generation_elapsed_ms += (perf_counter() - generation_started_at) * 1000
                retry_hint: str | None = None
                if guaranteed_refs and _HEDGE_RE.search(answer.content):
                    retry_hint = (
                        f"The retrieved context contains content from: {', '.join(guaranteed_refs)}. "
                        "Answer directly from the retrieved <knowledge> and do not claim the information "
                        "is unavailable."
                    )
                    logger.info(
                        "response_retry_hedging",
                        session_id=str(session_id),
                        doctwin_id=str(routed_doctwin_id) if routed_doctwin_id else None,
                        refs=guaranteed_refs,
                    )
                else:
                    verification_started_at = perf_counter()
                    verification = verify_single_project_answer(
                        answer=answer.content,
                        doctwin_name=doctwin_name,
                        packet=retrieval_packet,
                        allow_retry=True,
                        query=content,
                    )
                    verification_elapsed_ms += (perf_counter() - verification_started_at) * 1000
                    if verification.retry_hint:
                        retry_hint = verification.retry_hint
                        logger.info(
                            "answer_verifier_retry_requested",
                            session_id=str(session_id),
                            doctwin_id=str(routed_doctwin_id) if routed_doctwin_id else None,
                            issues=verification.issues,
                        )
                    else:
                        answer.content = verification.content

                if retry_hint:
                    generation_started_at = perf_counter()
                    answer = await generate_answer(
                        doctwin_name=doctwin_name,
                        query=content,
                        context_chunks=chunks,
                        conversation_history=history,
                        custom_context=custom_context,
                        allow_code_snippets=allow_code_snippets,
                        trace_id=trace_id,
                        sources=source_list,
                        memory_brief=memory_brief,
                        regeneration_hint=retry_hint,
                        retrieval_packet=retrieval_packet,
                        pipeline_trace_id=pipeline_trace_id,
                    )
                    generation_elapsed_ms += (perf_counter() - generation_started_at) * 1000
                    verification_started_at = perf_counter()
                    verification = verify_single_project_answer(
                        answer=answer.content,
                        doctwin_name=doctwin_name,
                        packet=retrieval_packet,
                        allow_retry=False,
                        query=content,
                    )
                    verification_elapsed_ms += (perf_counter() - verification_started_at) * 1000
                    answer.content = verification.content

                if verification is not None:
                    quality_metrics = build_single_project_quality_metrics(
                        answer=answer.content,
                        packet=retrieval_packet,
                        verification=verification,
                        retry_requested=bool(retry_hint),
                    )
                    logger.info(
                        "answer_verifier_complete",
                        session_id=str(session_id),
                        doctwin_id=str(routed_doctwin_id) if routed_doctwin_id else None,
                        verified=verification.verified,
                        rewritten=verification.rewritten,
                        issues=verification.issues,
                        retried=bool(retry_hint),
                    )
                    logger.info(
                        "answer_quality_metrics",
                        session_id=str(session_id),
                        doctwin_id=str(routed_doctwin_id) if routed_doctwin_id else None,
                        **quality_metrics.to_log_dict(),
                    )

    from app.core.config import get_settings

    _cfg = get_settings()
    if (
        _cfg.chat_quality_gate_enabled
        and not used_deterministic_fallback
        and not answer.model.startswith("deterministic")
        and not answer_from_workspace_aggregate
        and (session.doctwin_id is not None or routed_doctwin_id is not None)
    ):
        from app.domains.evaluation.quality_gate import apply_twin_path_quality_gate

        answer, qg_gen_ms, qg_ver_ms = await apply_twin_path_quality_gate(
            answer=answer,
            query=content,
            context_chunks=chunks,
            doctwin_name=doctwin_name,
            conversation_history=history,
            custom_context=custom_context,
            allow_code_snippets=allow_code_snippets,
            trace_id=trace_id,
            sources=source_list,
            memory_brief=memory_brief,
            retrieval_packet=retrieval_packet,
            pipeline_trace_id=pipeline_trace_id,
        )
        generation_elapsed_ms += qg_gen_ms
        verification_elapsed_ms += qg_ver_ms
        if retrieval_packet is not None:
            verification = verify_single_project_answer(
                answer=answer.content,
                doctwin_name=doctwin_name,
                packet=retrieval_packet,
                allow_retry=False,
                query=content,
            )
            answer.content = verification.content
            quality_metrics = build_single_project_quality_metrics(
                answer=answer.content,
                packet=retrieval_packet,
                verification=verification,
                retry_requested=True,
            )

    # Persist assistant message
    context_chunk_ids = [c["chunk_id"] for c in chunks if "chunk_id" in c]
    assistant_message = Message(
        id=uuid.uuid4(),
        session_id=session_id,
        role=MessageRole.assistant,
        content=answer.content,
        routed_doctwin_id=routed_doctwin_id,
        context_chunk_ids=context_chunk_ids,
    )
    db.add(assistant_message)
    await db.flush()
    await db.refresh(assistant_message)

    logger.info(
        "chat_message_processed",
        session_id=str(session_id),
        pipeline_trace_id=pipeline_trace_id,
        chunks_used=len(chunks),
        intent=intent.value,
        memory_brief_injected=memory_brief is not None,
        deterministic_fallback=used_deterministic_fallback,
        routed_doctwin_id=str(routed_doctwin_id) if routed_doctwin_id else None,
        input_tokens=answer.input_tokens,
        output_tokens=answer.output_tokens,
        trace_id=trace_id,
    )

    latency_report = build_chat_latency_report(
        retrieval_ms=retrieval_elapsed_ms,
        generation_ms=generation_elapsed_ms,
        verification_ms=verification_elapsed_ms,
        total_ms=(perf_counter() - total_started_at) * 1000,
        workspace_scope=(session.doctwin_id is None),
    )
    logger.info(
        "chat_latency_metrics",
        session_id=str(session_id),
        doctwin_id=str(routed_doctwin_id) if routed_doctwin_id else None,
        **latency_report.to_log_dict(),
    )
    if latency_report.budget_exceeded:
        logger.warning(
            "chat_latency_budget_exceeded",
            session_id=str(session_id),
            doctwin_id=str(routed_doctwin_id) if routed_doctwin_id else None,
            **latency_report.to_log_dict(),
        )

    # Phase 0 — evidence authority / degraded-mode diagnosis (logs + Langfuse)
    _doctwin_for_health = routed_doctwin_id or session.doctwin_id
    _src_orms = (
        await _load_source_orms_for_twin(_doctwin_for_health, db) if _doctwin_for_health else []
    )
    answer_authority = build_answer_authority_diagnosis(
        used_deterministic_fallback=used_deterministic_fallback,
        chunk_count=len(chunks),
        retrieval_packet=retrieval_packet,
        memory_brief_injected=memory_brief is not None,
        memory_brief_status=memory_brief_status_str,
        quality_metrics=quality_metrics,
        latency_budget_exceeded=latency_report.budget_exceeded,
        workspace_scope=(session.doctwin_id is None),
        sources=source_list if not _src_orms else None,
        source_models=_src_orms if _src_orms else None,
    )
    logger.info(
        "answer_authority_diagnosis",
        session_id=str(session_id),
        doctwin_id=str(routed_doctwin_id) if routed_doctwin_id else None,
        **answer_authority.to_log_dict(),
    )

    if lf and trace_id:
        try:
            lf.trace(
                id=trace_id,
                output=answer.content,
                metadata={
                    "input_tokens": answer.input_tokens,
                    "output_tokens": answer.output_tokens,
                    "chunks_used": len(chunks),
                    "routed_doctwin_id": str(routed_doctwin_id) if routed_doctwin_id else None,
                    "authority_level": answer_authority.authority_level.value,
                    "authority_degraded_reasons": answer_authority.degraded_reasons,
                },
            )
        except Exception as exc:
            logger.warning("langfuse_trace_update_failed", error=str(exc))

    # ── Passive LLM-as-judge (non-blocking) when active gate is off ────────────
    if not used_deterministic_fallback and not _cfg.chat_quality_gate_enabled:
        try:
            from app.domains.evaluation.evaluator import evaluate_response_async

            asyncio.create_task(
                evaluate_response_async(
                    query=content,
                    context_chunks=chunks,
                    response=answer.content,
                    doctwin_name=doctwin_name,
                    trace_id=trace_id,
                )
            )
        except Exception as exc:
            logger.warning("evaluator_task_fire_failed", error=str(exc))

    diag_payload = answer_authority.to_log_dict() if include_answer_diagnostics else None
    return SendMessageResult(message=assistant_message, answer_diagnostics=diag_payload)


async def send_public_message(
    public_slug: str,
    session_id: uuid.UUID,
    content: str,
    db: AsyncSession,
    *,
    visitor_id: str | None = None,
) -> Message:
    """
    Send a message in a public (anonymous) session.

    Verifies the session is anonymous and that the share surface is still active.
    Sessions created with a ``visitor_id`` require the same id on each message.
    """
    surface = await _load_active_surface(public_slug, db)

    session = await _load_session(session_id, db)
    if session.user_id is not None:
        raise ForbiddenError("Session is not a public anonymous session")
    if not _session_belongs_to_surface(session, surface):
        raise ForbiddenError("Session does not match this share link")
    if session.visitor_id is not None and (
        visitor_id is None or session.visitor_id != visitor_id
    ):
        raise ForbiddenError("Matching visitor_id required for this session")

    result = await send_message(
        session_id=session_id,
        content=content,
        user_id=None,
        db=db,
        include_answer_diagnostics=False,
    )
    return result.message


# ─── Session listing ──────────────────────────────────────────────────────────

async def list_sessions_for_twin(
    doctwin_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 30,
) -> list[dict]:
    """
    List recent chat sessions for a twin, owned by user_id, newest first.

    Returns lightweight summaries: session_id, timestamps, message count,
    and a preview (first user message, truncated to 120 chars).
    Ownership is verified via the twin's workspace.
    """
    twin = await _load_doctwin_with_workspace(doctwin_id, db)
    if twin is None:
        raise NotFoundError(f"Twin {doctwin_id} not found")
    if twin.workspace.owner_id != user_id:
        raise ForbiddenError("You do not own this twin's workspace")

    sessions_result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.doctwin_id == doctwin_id,
            ChatSession.user_id == user_id,
        )
        .order_by(ChatSession.created_at.desc())
        .limit(limit)
    )
    sessions = list(sessions_result.scalars().all())
    return await _summarize_sessions(sessions, db)


async def list_sessions_for_workspace(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 30,
) -> list[dict]:
    """
    List recent workspace-wide chat sessions for a workspace owned by user_id.

    Only workspace-scoped sessions (doctwin_id is null) are included so the session
    history matches the routed workspace chat surface rather than individual twins.
    """
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise NotFoundError(f"Workspace {workspace_id} not found")
    if workspace.owner_id != user_id:
        raise ForbiddenError("You do not own this workspace")

    sessions_result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.workspace_id == workspace_id,
            ChatSession.doctwin_id.is_(None),
            ChatSession.user_id == user_id,
        )
        .order_by(ChatSession.created_at.desc())
        .limit(limit)
    )
    sessions = list(sessions_result.scalars().all())
    return await _summarize_sessions(sessions, db)


# ─── History ──────────────────────────────────────────────────────────────────

async def get_history(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[Message]:
    """Return all messages in a session. Verifies ownership."""
    session = await _load_session(session_id, db)
    _assert_session_access(session, user_id)

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())


async def list_public_sessions(
    public_slug: str,
    visitor_id: str,
    db: AsyncSession,
    limit: int = 30,
) -> list[dict]:
    """
    List recent anonymous sessions for a share surface and visitor id.

    Used by public pages so visitors can resume prior chats when they reuse the same
    opaque visitor_id (stored locally, not personal data).
    """
    surface = await _load_active_surface(public_slug, db)

    conditions = [
        ChatSession.user_id.is_(None),
        ChatSession.visitor_id == visitor_id,
    ]
    if surface.doctwin_id is not None:
        conditions.append(ChatSession.doctwin_id == surface.doctwin_id)
    else:
        if surface.workspace_id is None:
            return []
        conditions.append(ChatSession.workspace_id == surface.workspace_id)
        conditions.append(ChatSession.doctwin_id.is_(None))

    sessions_result = await db.execute(
        select(ChatSession)
        .where(*conditions)
        .order_by(ChatSession.created_at.desc())
        .limit(limit)
    )
    sessions = list(sessions_result.scalars().all())
    return await _summarize_sessions(sessions, db)


async def get_public_history(
    public_slug: str,
    session_id: uuid.UUID,
    visitor_id: str,
    db: AsyncSession,
) -> list[Message]:
    """Load messages for a public session; requires matching visitor_id on the session."""
    surface = await _load_active_surface(public_slug, db)
    session = await _load_session(session_id, db)
    if session.user_id is not None:
        raise ForbiddenError("Session is not a public anonymous session")
    if not _session_belongs_to_surface(session, surface):
        raise ForbiddenError("Session does not match this share link")
    if session.visitor_id is None or session.visitor_id != visitor_id:
        raise ForbiddenError("Invalid visitor id for this session")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())


async def _summarize_sessions(
    sessions: list[ChatSession],
    db: AsyncSession,
) -> list[dict]:
    if not sessions:
        return []

    session_ids = [s.id for s in sessions]

    count_rows = await db.execute(
        select(Message.session_id, func.count(Message.id).label("cnt"))
        .where(Message.session_id.in_(session_ids))
        .group_by(Message.session_id)
    )
    counts: dict[uuid.UUID, int] = {r.session_id: r.cnt for r in count_rows}

    last_rows = await db.execute(
        select(Message.session_id, func.max(Message.created_at).label("last_at"))
        .where(Message.session_id.in_(session_ids))
        .group_by(Message.session_id)
    )
    last_at: dict[uuid.UUID, object] = {r.session_id: r.last_at for r in last_rows}

    preview_rows = await db.execute(
        select(Message.session_id, Message.content)
        .where(
            Message.session_id.in_(session_ids),
            Message.role == MessageRole.user,
        )
        .distinct(Message.session_id)
        .order_by(Message.session_id, Message.created_at)
    )
    previews: dict[uuid.UUID, str] = {}
    for row in preview_rows:
        if row.session_id not in previews:
            previews[row.session_id] = row.content[:120]

    return [
        {
            "session_id": str(session.id),
            "created_at": session.created_at.isoformat(),
            "last_message_at": last_at.get(session.id).isoformat() if last_at.get(session.id) else None,
            "message_count": counts.get(session.id, 0),
            "preview": previews.get(session.id),
        }
        for session in sessions
    ]


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _load_session(session_id: uuid.UUID, db: AsyncSession) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundError(f"Chat session {session_id} not found")
    return session


def _assert_session_access(session: ChatSession, user_id: uuid.UUID | None) -> None:
    """
    Verify access to a session.

    - Authenticated users must own the session (user_id matches).
    - Anonymous sessions (user_id=None) are accessible only via public routes
      which pass user_id=None explicitly.
    """
    if session.user_id is None:
        # Public session — anonymous access is fine
        return
    if user_id is None:
        raise ForbiddenError("Authentication required for this session")
    if session.user_id != user_id:
        raise ForbiddenError("You do not own this session")


async def _load_doctwin_with_workspace(doctwin_id: uuid.UUID, db: AsyncSession) -> Twin | None:
    result = await db.execute(
        select(Twin)
        .options(selectinload(Twin.workspace))
        .where(Twin.id == doctwin_id)
    )
    return result.scalar_one_or_none()


async def _load_doctwin_config(doctwin_id: uuid.UUID, db: AsyncSession) -> TwinConfig | None:
    result = await db.execute(
        select(TwinConfig).where(TwinConfig.doctwin_id == doctwin_id)
    )
    return result.scalar_one_or_none()


async def _load_active_surface(public_slug: str, db: AsyncSession) -> ShareSurface:
    result = await db.execute(
        select(ShareSurface).where(
            ShareSurface.public_slug == public_slug,
            ShareSurface.is_active.is_(True),
        )
    )
    surface = result.scalar_one_or_none()
    if surface is None:
        raise NotFoundError(f"No active share surface for slug: {public_slug}")
    return surface


async def _build_message_history(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """
    Load recent message history for multi-turn LLM context.

    Returns the last _MAX_HISTORY_TURNS turns as dicts with 'role' and 'content'.
    System messages are excluded — they're handled by the generator.
    """
    result = await db.execute(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role != MessageRole.system,
        )
        .order_by(Message.created_at.desc())
        .limit(_MAX_HISTORY_TURNS * 2)  # user + assistant per turn
    )
    messages = list(reversed(result.scalars().all()))

    # Apply character budget oldest-first: truncate verbose messages then drop
    # whole turns until total fits within _MAX_HISTORY_CHARS.
    budget = _MAX_HISTORY_CHARS
    result_msgs: list[dict] = []
    for m in reversed(messages):
        content = m.content
        if len(content) > _MAX_MESSAGE_CHARS:
            content = content[:_MAX_MESSAGE_CHARS] + " …[truncated]"
        if budget - len(content) < 0:
            break
        budget -= len(content)
        result_msgs.append({"role": m.role.value, "content": content})

    return list(reversed(result_msgs))


def _get_doctwin_display_name(
    session: ChatSession,
    doctwin_config: TwinConfig | None,
) -> str:
    """Return the display name for a twin, defaulting to 'This Project'."""
    if doctwin_config and doctwin_config.display_name:
        return doctwin_config.display_name
    return "This Project"


def _format_source_status_summary(sources: list[dict]) -> str:
    if not sources:
        return "no sources attached"
    return ", ".join(
        f"{src.get('name', 'Unnamed')} ({src.get('status', 'unknown')})"
        for src in sources
    )


async def _load_workspace_summary(
    workspace_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    result = await db.execute(
        select(Workspace)
        .options(
            selectinload(Workspace.twins).selectinload(Twin.config),
            selectinload(Workspace.twins).selectinload(Twin.sources),
        )
        .where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        return {
            "workspace_name": "this workspace",
            "total_twins": 0,
            "active_twins": 0,
            "ready_twins": 0,
            "twins": [],
        }

    twins_summary: list[dict] = []
    for twin in sorted(workspace.twins, key=lambda item: item.created_at):
        real_sources = [source for source in twin.sources if source.name != "__memory__"]
        ready_sources = [source for source in real_sources if source.status == SourceStatus.ready]
        twins_summary.append(
            {
                "id": twin.id,
                "slug": twin.slug,
                "canonical_name": twin.name,
                "name": twin.config.display_name if twin.config and twin.config.display_name else twin.name,
                "description": twin.description,
                "is_active": twin.is_active,
                "source_count": len(real_sources),
                "ready_source_count": len(ready_sources),
                "ready_source_names": [source.name for source in ready_sources],
            }
        )

    return {
        "workspace_name": workspace.name,
        "total_twins": len(twins_summary),
        "active_twins": sum(1 for twin in twins_summary if twin["is_active"]),
        "ready_twins": sum(1 for twin in twins_summary if twin["ready_source_count"] > 0),
        "twins": twins_summary,
    }


def _build_workspace_scope_response(query: str, workspace_summary: dict) -> str | None:
    # Greetings and self-intros ("Hi, my name is …") must go through the LLM so the model
    # can use conversation history and twin context — never short-circuit them here.
    if not (_is_source_query(query) or _is_workspace_coverage_query(query)):
        return None

    twins = workspace_summary.get("twins") or []
    total_twins = int(workspace_summary.get("total_twins") or 0)
    ready_twins = int(workspace_summary.get("ready_twins") or 0)
    active_twins = int(workspace_summary.get("active_twins") or 0)

    if total_twins == 0:
        return (
            "This workspace currently has **0 twins**, so there's nothing I can route across yet. "
            "Add a twin first, then I can answer workspace-wide questions."
        )

    doctwin_lines: list[str] = []
    for twin in twins:
        detail = twin["description"] or (
            f"Ready sources: {', '.join(twin['ready_source_names'])}"
            if twin["ready_source_names"]
            else "No description yet."
        )
        availability = (
            f"{twin['ready_source_count']} ready source"
            f"{'' if twin['ready_source_count'] == 1 else 's'}"
            if twin["ready_source_count"] > 0
            else "no ready sources yet"
        )
        active_note = "" if twin["is_active"] else " Inactive."
        doctwin_lines.append(f"- **{twin['name']}** — {detail} ({availability}).{active_note}")

    summary_line = (
        f"This workspace currently has **{total_twins} twin{'s' if total_twins != 1 else ''}**. "
        f"**{ready_twins}** {'have' if ready_twins != 1 else 'has'} ready sources I can answer from right now, "
        f"and **{active_twins}** {'are' if active_twins != 1 else 'is'} marked active."
    )

    heading = "## Workspace coverage" if _is_workspace_coverage_query(query) else "## Available twins"
    return (
        f"{summary_line}\n\n"
        f"{heading}\n"
        + "\n".join(doctwin_lines)
    )


def _normalise_workspace_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _workspace_doctwin_aliases(twin: dict) -> list[str]:
    aliases = {
        str(twin.get("name") or "").strip(),
        str(twin.get("canonical_name") or "").strip(),
        str(twin.get("slug") or "").replace("-", " ").strip(),
    }
    expanded: set[str] = set()
    for alias in aliases:
        if not alias:
            continue
        expanded.add(alias)
        lowered = alias.lower()
        if lowered.endswith(" twin"):
            expanded.add(alias[:-5].strip())
        if lowered.endswith(" project"):
            expanded.add(alias[:-8].strip())
    return sorted((alias for alias in expanded if alias), key=len, reverse=True)


def _resolve_workspace_doctwin_from_query(query: str, workspace_summary: dict) -> dict | None:
    twins = workspace_summary.get("twins") or []
    normalised_query = f" {_normalise_workspace_match(query)} "
    best_match: tuple[int, dict] | None = None

    for twin in twins:
        for alias in _workspace_doctwin_aliases(twin):
            normalised_alias = _normalise_workspace_match(alias)
            if len(normalised_alias) < 3:
                continue
            if normalised_alias in _WORKSPACE_ROUTE_ALIAS_STOPWORDS:
                continue
            if f" {normalised_alias} " not in normalised_query:
                continue
            score = len(normalised_alias)
            if best_match is None or score > best_match[0]:
                best_match = (score, twin)

    return best_match[1] if best_match else None


def _workspace_project_status_note(project: dict) -> str:
    ready_count = int(project.get("ready_source_count") or 0)
    total_sources = int(project.get("source_count") or 0)
    if ready_count <= 0:
        if total_sources <= 0:
            return "no sources attached"
        return "sources attached, but none are ready yet"
    return (
        f"{ready_count} ready source{'' if ready_count == 1 else 's'}"
        + ("" if project.get("is_active", True) else "; twin is currently inactive")
    )


def _workspace_topic_label(query: str) -> str:
    if _AUTH_TOPIC_RE.search(query):
        return "authentication implementation"
    return "this topic"


def _build_workspace_topic_gap_response(
    query: str,
    workspace_name: str,
    project_contexts: list[dict],
) -> str:
    topic_label = _workspace_topic_label(query)
    intro = (
        f"I checked **{len(project_contexts)}** project"
        f"{'' if len(project_contexts) == 1 else 's'} in **{workspace_name}** for {topic_label}."
    )
    sections: list[str] = []
    for project in project_contexts:
        if int(project.get("ready_source_count") or 0) <= 0:
            body = "This project does not have any ready sources yet, so I can't verify its implementation."
        else:
            body = (
                f"I couldn't find grounded evidence for {topic_label} in this project's available memory, "
                "so I won't claim an implementation that isn't supported."
            )
        sections.append(f"## {project['name']}\n{body}")
    return intro + "\n\n" + "\n\n".join(sections)


async def _answer_across_workspace(
    *,
    session: ChatSession,
    workspace_id: uuid.UUID,
    query: str,
    history: list[dict],
    analysis: QueryAnalysis,
    workspace_summary: dict,
    db: AsyncSession,
    trace_id: str | None,
    pipeline_trace_id: str | None = None,
) -> tuple[LLMResponse, list[dict], dict]:
    project_summaries = workspace_summary.get("twins") or []
    workspace_name = workspace_summary.get("workspace_name") or "this workspace"
    per_doctwin_top_k = 6 if _is_broad_query(query) else 4
    lowered_query = query.lower()
    if any(
        token in lowered_query
        for token in (
            "auth",
            "authentication",
            "authorization",
            "login",
            "logout",
            "refresh token",
            "session",
            "dashboard",
            "code snippet",
        )
    ):
        per_doctwin_top_k = max(per_doctwin_top_k, 8)
    retrieval_started_at = perf_counter()
    generation_elapsed_ms = 0.0
    verification_elapsed_ms = 0.0
    retry_requested = False

    project_contexts: list[dict] = []
    merged_chunks: list[dict] = []
    seen_chunk_ids: set[str] = set()

    for project in project_summaries:
        ready_source_count = int(project.get("ready_source_count") or 0)
        project_chunks: list[dict] = []
        project_packet = None
        if ready_source_count > 0 and project.get("id"):
            doctwin_id = str(project["id"])
            inventory = await _load_structure_inventory(doctwin_id, db)
            guaranteed_refs = _resolve_refs_from_inventory(analysis.path_hints, inventory)
            project_config = await _load_doctwin_config(uuid.UUID(doctwin_id), db)
            project_packet = await retrieve_packet_for_twin(
                query=query,
                doctwin_id=doctwin_id,
                allow_code_snippets=bool(
                    project_config.allow_code_snippets if project_config else False
                ),
                db=db,
                top_k=per_doctwin_top_k,
                intent=analysis.intent,
                path_hints=analysis.path_hints,
                guaranteed_refs=guaranteed_refs,
                expanded_query=analysis.expanded_query,
                pipeline_trace_id=pipeline_trace_id,
            )
            project_chunks = project_packet.chunks
            for chunk in project_chunks:
                chunk_id = chunk.get("chunk_id")
                if chunk_id and chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk_id)
                    merged_chunks.append(chunk)

        project_contexts.append(
            {
                "name": project["name"],
                "description": project.get("description"),
                "ready_source_count": ready_source_count,
                "ready_source_names": project.get("ready_source_names") or [],
                "status_note": _workspace_project_status_note(project),
                "chunks": project_chunks,
                "evidence_packet": project_packet,
            }
        )

    if not any(project["chunks"] for project in project_contexts):
        retrieval_elapsed_ms = (perf_counter() - retrieval_started_at) * 1000
        logger.info(
            "workspace_topic_no_grounding",
            workspace_id=str(workspace_id),
            query_length=len(query),
            projects_checked=len(project_contexts),
        )
        answer = LLMResponse(
                content=_build_workspace_topic_gap_response(query, workspace_name, project_contexts),
                model="deterministic-workspace-topic-gap",
                input_tokens=0,
                output_tokens=0,
        )
        quality_metrics = build_workspace_quality_metrics(
            answer=answer.content,
            project_contexts=project_contexts,
            verification=verify_workspace_answer(
                answer=answer.content,
                workspace_name=workspace_name,
                project_contexts=project_contexts,
                allow_retry=False,
                query=query,
            ),
            retry_requested=False,
        )
        latency_report = build_chat_latency_report(
            retrieval_ms=retrieval_elapsed_ms,
            generation_ms=0.0,
            verification_ms=0.0,
            total_ms=retrieval_elapsed_ms,
            workspace_scope=True,
        )
        logger.info(
            "workspace_answer_quality_metrics",
            workspace_id=str(workspace_id),
            **quality_metrics.to_log_dict(),
        )
        logger.info(
            "workspace_chat_latency_metrics",
            workspace_id=str(workspace_id),
            **latency_report.to_log_dict(),
        )
        if latency_report.budget_exceeded:
            logger.warning(
                "workspace_chat_latency_budget_exceeded",
                workspace_id=str(workspace_id),
                **latency_report.to_log_dict(),
            )
        return answer, merged_chunks, {
            "retrieval_ms": retrieval_elapsed_ms,
            "generation_ms": 0.0,
            "verification_ms": 0.0,
            "quality_metrics": quality_metrics,
        }

    retrieval_elapsed_ms = (perf_counter() - retrieval_started_at) * 1000
    logger.info(
        "workspace_aggregate_retrieval_complete",
        workspace_id=str(workspace_id),
        projects_checked=len(project_contexts),
        projects_with_hits=sum(1 for project in project_contexts if project["chunks"]),
        chunks_returned=len(merged_chunks),
    )
    workspace_memory_text = await get_workspace_synthesis(str(workspace_id), db)
    generation_started_at = perf_counter()
    answer = await generate_workspace_answer(
        workspace_name=workspace_name,
        query=query,
        project_contexts=project_contexts,
        conversation_history=history,
        trace_id=trace_id,
        workspace_memory=workspace_memory_text,
    )
    generation_elapsed_ms += (perf_counter() - generation_started_at) * 1000
    verification_started_at = perf_counter()
    verification = verify_workspace_answer(
        answer=answer.content,
        workspace_name=workspace_name,
        project_contexts=project_contexts,
        allow_retry=True,
        query=query,
    )
    verification_elapsed_ms += (perf_counter() - verification_started_at) * 1000
    if verification.retry_hint:
        retry_requested = True
        logger.info(
            "workspace_answer_verifier_retry_requested",
            workspace_id=str(workspace_id),
            issues=verification.issues,
        )
        generation_started_at = perf_counter()
        answer = await generate_workspace_answer(
            workspace_name=workspace_name,
            query=query,
            project_contexts=project_contexts,
            conversation_history=history,
            trace_id=trace_id,
            regeneration_hint=verification.retry_hint,
            workspace_memory=workspace_memory_text,
        )
        generation_elapsed_ms += (perf_counter() - generation_started_at) * 1000
        verification_started_at = perf_counter()
        verification = verify_workspace_answer(
            answer=answer.content,
            workspace_name=workspace_name,
            project_contexts=project_contexts,
            allow_retry=False,
            query=query,
        )
        verification_elapsed_ms += (perf_counter() - verification_started_at) * 1000

    answer.content = verification.content

    from app.core.config import get_settings as _ws_gate_settings
    from app.domains.evaluation.quality_gate import apply_workspace_aggregate_quality_gate

    if _ws_gate_settings().chat_quality_gate_enabled and not answer.model.startswith(
        "deterministic"
    ):
        answer, qg_gen_ms, qg_ver_ms = await apply_workspace_aggregate_quality_gate(
            answer=answer,
            query=query,
            merged_chunks=merged_chunks,
            workspace_name=workspace_name,
            project_contexts=project_contexts,
            conversation_history=history,
            workspace_memory=workspace_memory_text,
            trace_id=trace_id,
            workspace_id=workspace_id,
        )
        generation_elapsed_ms += qg_gen_ms
        verification_elapsed_ms += qg_ver_ms
        verification = verify_workspace_answer(
            answer=answer.content,
            workspace_name=workspace_name,
            project_contexts=project_contexts,
            allow_retry=False,
            query=query,
        )
        answer.content = verification.content

    quality_metrics = build_workspace_quality_metrics(
        answer=answer.content,
        project_contexts=project_contexts,
        verification=verification,
        retry_requested=retry_requested,
    )
    logger.info(
        "workspace_answer_verifier_complete",
        workspace_id=str(workspace_id),
        verified=verification.verified,
        rewritten=verification.rewritten,
        issues=verification.issues,
        retried=retry_requested,
    )
    logger.info(
        "workspace_answer_quality_metrics",
        workspace_id=str(workspace_id),
        **quality_metrics.to_log_dict(),
    )
    latency_report = build_chat_latency_report(
        retrieval_ms=retrieval_elapsed_ms,
        generation_ms=generation_elapsed_ms,
        verification_ms=verification_elapsed_ms,
        total_ms=retrieval_elapsed_ms + generation_elapsed_ms + verification_elapsed_ms,
        workspace_scope=True,
    )
    logger.info(
        "workspace_chat_latency_metrics",
        workspace_id=str(workspace_id),
        **latency_report.to_log_dict(),
    )
    if latency_report.budget_exceeded:
        logger.warning(
            "workspace_chat_latency_budget_exceeded",
            workspace_id=str(workspace_id),
            **latency_report.to_log_dict(),
        )
    return answer, merged_chunks, {
        "retrieval_ms": retrieval_elapsed_ms,
        "generation_ms": generation_elapsed_ms,
        "verification_ms": verification_elapsed_ms,
        "quality_metrics": quality_metrics,
    }


def _build_no_grounding_response(
    *,
    query: str,
    scope_name: str,
    sources: list[dict],
    has_context_chunks: bool,
    has_memory_brief: bool,
    is_workspace_scope: bool,
) -> str | None:
    """
    Return a deterministic fallback when no grounded project knowledge is available.

    This prevents the LLM from fabricating project details when both retrieval
    and memory brief injection are empty.
    """
    if has_context_chunks or has_memory_brief:
        return None

    scope_label = "this workspace" if is_workspace_scope else scope_name
    ready_sources = [s for s in sources if s.get("status") == "ready"]

    if not sources:
        if _is_greeting(query):
            return (
                f"Hi! I don't have any knowledge sources attached to {scope_label} yet, "
                "so I can't answer project-specific questions just yet. Add a source and "
                "once it finishes processing, I can help."
            )
        if _is_source_query(query):
            return (
                f"I don't have any knowledge sources attached to {scope_label} yet. "
                "Add a Drive file, document, PDF, website, or notes source and once it finishes "
                "processing I can answer questions from it."
            )
        return (
            f"I don't have any grounded project knowledge available for {scope_label} yet "
            "because no sources are attached. Add a source and once it finishes processing, "
            "ask again."
        )

    if not ready_sources:
        source_summary = _format_source_status_summary(sources)
        if _is_greeting(query):
            return (
                f"Hi! I can see sources attached to {scope_label}, but none are ready yet: "
                f"{source_summary}. Once processing finishes, I can answer grounded questions "
                "about the project."
            )
        if _is_source_query(query):
            return (
                f"I can see attached sources for {scope_label}, but none are ready yet: "
                f"{source_summary}. Once at least one source is ready, I can answer questions "
                "from it."
            )
        return (
            f"I can see sources attached to {scope_label} but none are ready yet: "
            f"{source_summary}. Once processing finishes, ask again."
        )

    if _is_source_query(query):
        return (
            f"I have attached sources for {scope_label}: {_format_source_status_summary(sources)}. "
            "I couldn't retrieve enough grounded project context for that question, so I won't guess. "
            "Try a more specific question or re-run processing if this persists."
        )

    if _is_greeting(query):
        return None

    return (
        f"I don't have enough indexed content available for {scope_label} to answer "
        "that right now. Try a more specific question, or retry "
        "once indexing finishes."
    )


async def _load_sources_for_twin(
    doctwin_id: uuid.UUID | None,
    db: AsyncSession,
) -> list[dict]:
    """
    Return a lightweight list of source records attached to a twin.

    Used to give the LLM awareness of what knowledge sources exist, so it
    can confirm "yes, I have your resume" even when resume chunks don't score
    highly enough for the current query vector.

    Returns an empty list when doctwin_id is None (workspace-wide sessions without
    a resolved twin don't have a single source list to reference).

    Phase 0: each row includes index_mode and summary index_health fields so
    answer diagnostics can attribute weakness to ingest/index state.
    """
    if doctwin_id is None:
        return []
    try:
        result = await db.execute(
            select(Source)
            .where(Source.doctwin_id == doctwin_id)
            .order_by(Source.created_at)
        )
        sources = result.scalars().all()
        out: list[dict] = []
        for s in sources:
            health = s.index_health or {}
            impl = health.get("implementation_index") or {}
            contract = health.get("contract") or {}
            out.append(
                {
                    "name": s.name,
                    "source_type": s.source_type.value,
                    "status": s.status.value,
                    "index_mode": s.index_mode.value,
                    "strict_evidence_ready": health.get("strict_evidence_ready"),
                    "strict_evidence_supported": health.get("strict_evidence_supported"),
                    "parser_coverage_ratio": impl.get("parser_coverage_ratio"),
                    "strict_coverage_ratio": contract.get("strict_coverage_ratio"),
                }
            )
        return out
    except Exception as exc:
        logger.warning("load_sources_for_doctwin_failed", doctwin_id=str(doctwin_id), error=str(exc))
        return []


async def _load_source_orms_for_twin(
    doctwin_id: uuid.UUID | None,
    db: AsyncSession,
) -> list[Source]:
    """Full Source rows for Phase 0 twin-level evidence health aggregation."""
    if doctwin_id is None:
        return []
    try:
        result = await db.execute(
            select(Source)
            .where(Source.doctwin_id == doctwin_id)
            .order_by(Source.created_at)
        )
        return list(result.scalars().all())
    except Exception as exc:
        logger.warning("load_source_orms_for_doctwin_failed", doctwin_id=str(doctwin_id), error=str(exc))
        return []
