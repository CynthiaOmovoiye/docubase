"""
LLM-as-judge response evaluator.

Runs ASYNCHRONOUSLY after the assistant response has already been sent to
the user — it never adds latency to the chat path.

Evaluation dimensions:
  - completeness   (1-5): Does the answer fully address what was asked?
  - groundedness   (1-5): Every claim is supported by the retrieved context.
  - technical_depth (1-5): Appropriate depth for a developer/recruiter audience.
  - format_quality  (1-5): Well-structured, readable, uses markdown appropriately.
  - usefulness      (1-5): Actionable and genuinely helpful for the stated user/task.

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
You are a quality evaluator for an AI assistant that answers technical questions
about software projects. Your job is to score a given response on six dimensions.

Scoring rubric (1 = very poor, 5 = excellent):

completeness    — Does the response fully address the question? 5 means nothing
  important was left out; 1 means the response barely touches the question.

groundedness    — Is every factual claim supported by the provided context chunks?
  5 means every statement is directly traceable to the context (no hallucination);
  1 means significant speculation or invention is present.

technical_depth — Is the level of technical detail appropriate for developers and
  technical recruiters? 5 means specific, precise, and insightful; 1 means vague or generic.

format_quality  — Is the response well-structured and easy to read? 5 means it uses
  appropriate markdown (headers, tables, code blocks) and is clearly organised;
  1 means it is a wall of unformatted text.

context_precision — Of the retrieved context chunks provided, how many were actually
  relevant and useful to answering this question? 5 means every chunk was on-topic;
  1 means nearly all chunks were irrelevant noise.

faithfulness    — Are all factual claims in the response directly supported by the
  retrieved context (not general knowledge or invention)? 5 means every claim can be
  traced to a specific chunk; 1 means the response relies heavily on information not
  present in the context.

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
QUESTION:
{query}

CONTEXT PROVIDED TO THE ASSISTANT (retrieved chunks):
{context}

ASSISTANT RESPONSE TO EVALUATE:
{response}
"""

# Minimum score below which we emit a warning log
_WARN_THRESHOLD = 2.5


async def evaluate_response_async(
    query: str,
    context_chunks: list[dict],
    response: str,
    twin_name: str,
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
        twin_name:      Display name of the twin being evaluated.
        trace_id:       Langfuse trace ID to attach scores to, if any.
    """
    try:
        scores = await _run_evaluation(query, context_chunks, response)
    except Exception as exc:
        logger.warning("evaluation_failed", twin_name=twin_name, error=str(exc))
        return

    numeric_scores = [value for key, value in scores.items() if key != "reasoning"]
    avg = sum(numeric_scores) / len(numeric_scores) if numeric_scores else 0.0

    logger.info(
        "evaluation_complete",
        twin_name=twin_name,
        trace_id=trace_id,
        **{k: v for k, v in scores.items() if k != "reasoning"},
        average=round(avg, 2),
        reasoning=scores.get("reasoning", ""),
    )

    if avg < _WARN_THRESHOLD:
        logger.warning(
            "evaluation_low_quality",
            twin_name=twin_name,
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
