"""
Active LLM-as-judge gate: structured accept/reject + bounded regeneration.

Uses a Pydantic model to validate evaluator JSON, then optionally forces another
generation pass with explicit feedback (same pattern as the career_conversation demo).
"""

from __future__ import annotations

import re
from time import perf_counter
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domains.answering.generator import generate_answer, generate_workspace_answer
from app.domains.answering.llm_provider import LLMResponse, get_llm_provider
from app.domains.answering.verifier import verify_single_project_answer, verify_workspace_answer

logger = get_logger(__name__)


class ResponseQualityGate(BaseModel):
    """Structured output from the judge model — validated with Pydantic."""

    model_config = ConfigDict(extra="forbid")

    is_acceptable: bool
    feedback: str = Field(default="", max_length=6000)


_GATE_SYSTEM_PROMPT = """\
You are a strict quality gate for Docbase chat: answers must be grounded in the \
retrieved context, address the user's question, and be appropriate for a professional \
visitor-facing assistant.

Important: retrieved excerpts usually describe the **professional / project** the site \
represents (e.g. a resume). The **visitor** may state different facts about themselves in \
the chat transcript (e.g. their name). If the user asks about **their** name or other \
self-facts, an answer that follows the **conversation transcript** is acceptable even when \
it disagrees with a represented person's name in the excerpts.

Reject (is_acceptable=false) when ANY of these apply:
- The answer ignores the question, is mostly boilerplate, or refuses without cause.
- Factual claims clearly contradict or are unsupported by the provided excerpts **and** \
  the conversation excerpt (when both are provided) — inventing employers, dates, or tech \
  not in either.
- The answer is internal-looking: raw file lists, Drive IDs, "Negative-evidence scope", \
  "Grounded files:", xref/PDF junk, or other evidence-debug scaffolding meant for engineers.
- The answer is hostile, unsafe, or a jailbreak compliance.

Accept (is_acceptable=true) when the response is coherent, on-topic, and reasonably \
grounded in the excerpts and/or the conversation (brief professional small-talk or identity \
answers are fine if they fit the context).

Respond with ONLY a single JSON object (no markdown fences) matching exactly:
{"is_acceptable": <true|false>, "feedback": "<if false, concrete instructions to fix; \
if true, empty string or brief ok>"}
"""


def _conversation_excerpt_for_gate(history: list[dict], *, max_chars: int = 2500) -> str:
    """Compact recent turns for the judge — visitor-stated facts live here, not in RAG."""
    if not history:
        return ""
    lines: list[str] = []
    for msg in history[-14:]:
        role = str(msg.get("role") or "")
        body = str(msg.get("content") or "").strip().replace("\n", " ")
        if len(body) > 900:
            body = body[:900] + " …"
        lines.append(f"{role.upper()}: {body}")
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _parse_gate_json(raw: str) -> ResponseQualityGate:
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL)
    if not match:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in gate response: {raw[:240]!r}")
    return ResponseQualityGate.model_validate_json(match.group(0))


async def evaluate_response_gate(
    *,
    query: str,
    context_chunks: list[dict],
    response: str,
    trace_id: str | None = None,
    conversation_excerpt: str | None = None,
) -> ResponseQualityGate:
    context_summary = "\n\n".join(
        f"[{i + 1}] {c.get('source_ref', 'unknown')}: {str(c.get('content', ''))[:500]}"
        for i, c in enumerate(context_chunks[:12])
    )
    conv_block = ""
    excerpt = (conversation_excerpt or "").strip()
    if excerpt:
        conv_block = f"CONVERSATION TRANSCRIPT (recent turns):\n{excerpt}\n\n"
    user_message = (
        f"USER QUESTION:\n{query}\n\n"
        f"{conv_block}"
        f"RETRIEVED CONTEXT (excerpts the assistant was given):\n"
        f"{context_summary or '(none)'}\n\n"
        f"ASSISTANT RESPONSE TO JUDGE:\n{response[:6000]}"
    )
    provider = get_llm_provider()
    llm = await provider.complete(
        system_prompt=_GATE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=384,
        temperature=0.0,
        trace_id=trace_id,
        generation_name="response_quality_gate",
    )
    return _parse_gate_json(llm.content)


async def apply_workspace_aggregate_quality_gate(
    *,
    answer: LLMResponse,
    query: str,
    merged_chunks: list[dict],
    workspace_name: str,
    project_contexts: list[dict],
    conversation_history: list[dict],
    workspace_memory: str | None,
    trace_id: str | None,
    workspace_id: UUID,
) -> tuple[LLMResponse, float, float]:
    """
    Run gate + optional regenerations for workspace aggregate answers.

    Returns (possibly updated answer, extra_generation_ms, extra_verification_ms).
    """
    settings = get_settings()
    if not settings.chat_quality_gate_enabled or answer.model.startswith("deterministic"):
        return answer, 0.0, 0.0

    extra_gen = 0.0
    extra_verify = 0.0
    max_extra = max(0, settings.chat_quality_gate_max_regenerations)
    attempt = 0
    current = answer
    conv_excerpt = _conversation_excerpt_for_gate(conversation_history)

    while attempt <= max_extra:
        try:
            gate = await evaluate_response_gate(
                query=query,
                context_chunks=merged_chunks,
                response=current.content,
                trace_id=trace_id,
                conversation_excerpt=conv_excerpt,
            )
        except Exception as exc:
            logger.warning("quality_gate_eval_failed", error=str(exc), workspace=str(workspace_id))
            break

        logger.info(
            "quality_gate_workspace",
            workspace_id=str(workspace_id),
            attempt=attempt,
            is_acceptable=gate.is_acceptable,
            feedback_len=len(gate.feedback),
        )

        if gate.is_acceptable:
            break
        if attempt >= max_extra:
            logger.warning(
                "quality_gate_workspace_exhausted",
                workspace_id=str(workspace_id),
                feedback_preview=gate.feedback[:300],
            )
            break

        hint = (
            "Quality review rejected the previous draft. Revise using only the indexed "
            f"context; do not output internal evidence dumps or raw file inventories.\n\n"
            f"Feedback:\n{gate.feedback}\n\n"
            f"Rejected draft (do not repeat verbatim):\n{current.content[:2000]}"
        )
        t0 = perf_counter()
        regenerated = await generate_workspace_answer(
            workspace_name=workspace_name,
            query=query,
            project_contexts=project_contexts,
            conversation_history=conversation_history,
            trace_id=trace_id,
            regeneration_hint=hint,
            workspace_memory=workspace_memory,
        )
        extra_gen += (perf_counter() - t0) * 1000
        current.input_tokens += regenerated.input_tokens
        current.output_tokens += regenerated.output_tokens
        current.model = regenerated.model

        t1 = perf_counter()
        verification = verify_workspace_answer(
            answer=regenerated.content,
            workspace_name=workspace_name,
            project_contexts=project_contexts,
            allow_retry=False,
            query=query,
        )
        extra_verify += (perf_counter() - t1) * 1000
        current.content = verification.content
        attempt += 1

    return current, extra_gen, extra_verify


async def apply_twin_path_quality_gate(
    *,
    answer: LLMResponse,
    query: str,
    context_chunks: list[dict],
    doctwin_name: str,
    conversation_history: list[dict],
    custom_context: str | None,
    allow_code_snippets: bool,
    trace_id: str | None,
    sources: list[dict],
    memory_brief: str | None,
    retrieval_packet,
    pipeline_trace_id: str | None,
) -> tuple[LLMResponse, float, float]:
    """Gate + optional regenerations for single-twin (or routed workspace twin) answers."""
    settings = get_settings()
    if not settings.chat_quality_gate_enabled or answer.model.startswith("deterministic"):
        return answer, 0.0, 0.0

    extra_gen = 0.0
    extra_verify = 0.0
    max_extra = max(0, settings.chat_quality_gate_max_regenerations)
    attempt = 0
    current = answer
    conv_excerpt = _conversation_excerpt_for_gate(conversation_history)

    while attempt <= max_extra:
        try:
            gate = await evaluate_response_gate(
                query=query,
                context_chunks=context_chunks,
                response=current.content,
                trace_id=trace_id,
                conversation_excerpt=conv_excerpt,
            )
        except Exception as exc:
            logger.warning("quality_gate_eval_failed", error=str(exc), path="twin")
            break

        logger.info(
            "quality_gate_twin",
            doctwin_name=doctwin_name,
            attempt=attempt,
            is_acceptable=gate.is_acceptable,
            feedback_len=len(gate.feedback),
        )

        if gate.is_acceptable:
            break
        if attempt >= max_extra:
            logger.warning(
                "quality_gate_twin_exhausted",
                doctwin_name=doctwin_name,
                feedback_preview=gate.feedback[:300],
            )
            break

        hint = (
            "Quality review rejected the previous draft. Improve it using only grounded "
            f"context; fix the issues below.\n\nFeedback:\n{gate.feedback}\n\n"
            f"Rejected draft (reference only):\n{current.content[:2000]}"
        )
        t0 = perf_counter()
        regenerated = await generate_answer(
            doctwin_name=doctwin_name,
            query=query,
            context_chunks=context_chunks,
            conversation_history=conversation_history,
            custom_context=custom_context,
            allow_code_snippets=allow_code_snippets,
            trace_id=trace_id,
            sources=sources,
            memory_brief=memory_brief,
            regeneration_hint=hint,
            retrieval_packet=retrieval_packet,
            pipeline_trace_id=pipeline_trace_id,
        )
        extra_gen += (perf_counter() - t0) * 1000
        current.input_tokens += regenerated.input_tokens
        current.output_tokens += regenerated.output_tokens
        current.model = regenerated.model

        t1 = perf_counter()
        verification = verify_single_project_answer(
            answer=regenerated.content,
            doctwin_name=doctwin_name,
            packet=retrieval_packet,
            allow_retry=False,
        )
        extra_verify += (perf_counter() - t1) * 1000
        current.content = verification.content
        attempt += 1

    return current, extra_gen, extra_verify
