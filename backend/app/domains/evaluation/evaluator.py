"""
LLM-as-judge response evaluator (passive / dimensional scores).

Runs ASYNCHRONOUSLY after the assistant response has already been sent to
the user — it never adds latency to the chat path.

When ``chat_quality_gate_enabled`` is true in settings, ``send_message`` uses
``quality_gate`` instead for an active accept/reject + regeneration path and
this module's async task is skipped for that request.

Evaluation dimensions (1–5 each):
  - completeness, groundedness, technical_depth, format_quality, context_precision,
    faithfulness, usefulness — see system rubric in ``_EVAL_SYSTEM_PROMPT``.

Scores are logged to Langfuse (if configured) and to the application log.
When Langfuse is unavailable, evaluation still runs and scores are logged
as structured log entries — useful during local development.

Design notes:
  - Uses the same LLM provider as the main generator to avoid extra config.
  - A dedicated fast/cheap model can be added via EVALUATOR_MODEL env var
    without touching this code — it will fall through to the default.
  - Errors are swallowed — a failed evaluation must never surface to the user.
"""

from __future__ import annotations

import json
import re

from app.core.logging import get_logger
from app.core.observability import get_langfuse
from app.domains.answering.llm_provider import get_llm_provider

logger = get_logger(__name__)

_EVAL_SYSTEM_PROMPT = """\
You are a quality evaluator for Docbase: a document-grounded assistant (DocTwin). Users \
attach files and sources (resumes, policies, product docs, meeting notes, repositories, \
Google Drive folders, etc.). The assistant must answer from retrieved context chunks and \
optional system-level summaries — not invent facts.

Score the assistant response on seven dimensions (1 = very poor, 5 = excellent).

completeness — Does the answer fully address what the user asked? 5 = nothing important \
omitted; 1 = barely engages the question.

groundedness — Are factual claims supported by the provided context chunks? 5 = claims \
traceable to chunks; 1 = clear hallucination or speculation beyond the evidence.

technical_depth — Is the level of detail right for the question? Judge against the *query*, \
not only "engineering": a resume or policy question may warrant concrete names, dates, or \
obligations rather than deep stack traces. 5 = appropriately specific; 1 = vague or \
off-topic depth (e.g. generic product talk when the user asked a personal factual question).

format_quality — Readable and well structured? 5 = clear paragraphs or markdown where \
helpful; 1 = unreadable wall of text.

context_precision — Of the retrieved chunks shown, how many were relevant to answering \
this question? 5 = on-topic; 1 = mostly noise.

faithfulness — Same axis as groundedness: no facts drawn from outside the supplied \
context unless the user asked for general advice and the answer stays clearly separated \
from document claims.

usefulness — Would this answer help the user accomplish their goal (find a fact, decide, \
or understand) given the evidence available?

In "reasoning", name the lowest-scoring dimension and why (one sentence).

Respond ONLY with a valid JSON object, no commentary:
{
  "completeness": <int 1-5>,
  "groundedness": <int 1-5>,
  "technical_depth": <int 1-5>,
  "format_quality": <int 1-5>,
  "context_precision": <int 1-5>,
  "faithfulness": <int 1-5>,
  "usefulness": <int 1-5>,
  "reasoning": "<one sentence explaining the lowest score>"
}
"""

_EVAL_USER_TEMPLATE = """\
USER QUESTION:
{query}

RETRIEVED CONTEXT (chunks the assistant was given):
{context}

ASSISTANT RESPONSE TO SCORE:
{response}
"""

# Minimum score below which we emit a warning log
_WARN_THRESHOLD = 2.5


async def evaluate_response_async(
    query: str,
    context_chunks: list[dict],
    response: str,
    doctwin_name: str,
    trace_id: str | None = None,
) -> None:
    """
    Run LLM-as-judge evaluation and log scores.

    Designed to be fired with asyncio.create_task() — never awaited on
    the hot path.  All exceptions are caught and logged.

    Args:
        query:          The user's question.
        context_chunks: Chunks that were passed to the generator.
        response:       The assistant's response text.
        doctwin_name:      Display name of the twin being evaluated.
        trace_id:       Langfuse trace ID to attach scores to, if any.
    """
    try:
        scores = await _run_evaluation(query, context_chunks, response)
    except Exception as exc:
        logger.warning("evaluation_failed", doctwin_name=doctwin_name, error=str(exc))
        return

    numeric_scores = [value for key, value in scores.items() if key != "reasoning"]
    avg = sum(numeric_scores) / len(numeric_scores) if numeric_scores else 0.0

    logger.info(
        "evaluation_complete",
        doctwin_name=doctwin_name,
        trace_id=trace_id,
        **{k: v for k, v in scores.items() if k != "reasoning"},
        average=round(avg, 2),
        reasoning=scores.get("reasoning", ""),
    )

    if avg < _WARN_THRESHOLD:
        logger.warning(
            "evaluation_low_quality",
            doctwin_name=doctwin_name,
            trace_id=trace_id,
            average=round(avg, 2),
            reasoning=scores.get("reasoning", ""),
        )

    # Push scores to Langfuse
    lf = get_langfuse()
    if lf and trace_id:
        _push_scores_to_langfuse(lf, trace_id, scores)


async def _run_evaluation(
    query: str,
    context_chunks: list[dict],
    response: str,
) -> dict:
    """Call the LLM and parse the evaluation JSON."""
    # Summarise context for the evaluator prompt (don't send full chunks — too long)
    context_summary = "\n\n".join(
        f"[{i+1}] {c.get('source_ref', 'unknown')}: {c['content'][:400]}"
        for i, c in enumerate(context_chunks[:8])
    )

    user_message = _EVAL_USER_TEMPLATE.format(
        query=query,
        context=context_summary or "(no context retrieved)",
        response=response[:3000],  # cap — evaluator doesn't need the full response
    )

    provider = get_llm_provider()
    llm_response = await provider.complete(
        system_prompt=_EVAL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=256,
        temperature=0.0,
    )

    return _parse_scores(llm_response.content)


def _parse_scores(raw: str) -> dict:
    """
    Extract the JSON scores block from the LLM response.

    Falls back gracefully if the model wraps the JSON in markdown fences.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

    # Find the first { ... } block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in evaluator response: {raw[:200]}")

    data = json.loads(match.group(0))

    # Validate and clamp numeric scores
    result: dict = {}
    for key in (
        "completeness",
        "groundedness",
        "technical_depth",
        "format_quality",
        "context_precision",
        "faithfulness",
        "usefulness",
    ):
        val = data.get(key)
        if val is not None:
            result[key] = max(1, min(5, int(val)))

    result["reasoning"] = str(data.get("reasoning", ""))
    return result


def _push_scores_to_langfuse(lf, trace_id: str, scores: dict) -> None:
    """Push individual dimension scores to an existing Langfuse trace."""
    try:
        for name, value in scores.items():
            if name == "reasoning":
                continue
            lf.score(
                trace_id=trace_id,
                name=name,
                value=float(value),
                comment=scores.get("reasoning") if name == min(
                    scores, key=lambda k: scores[k] if k != "reasoning" else 999
                ) else None,
            )
    except Exception as exc:
        logger.warning("langfuse_score_push_failed", trace_id=trace_id, error=str(exc))
