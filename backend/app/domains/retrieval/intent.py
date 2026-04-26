"""
Query intent classification for document-aware retrieval.

Two intents:
  specific — user references a named document, section, or topic by name
  general  — everything else (semantic + lexical ranking handles it)

`analyse_query()` makes a lightweight LLM call to classify intent, extract
named path hints, and produce an expanded query for better semantic recall.
A regex fallback fires automatically if the LLM call fails for any reason
(timeout, provider error, malformed JSON).

`extract_path_hint()` remains as a standalone utility for callers that need
a fast, synchronous path hint without a full analysis call.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum

from pydantic import BaseModel, field_validator

from app.core.logging import get_logger

logger = get_logger(__name__)


class QueryIntent(StrEnum):
    specific = "specific"  # query names a document, section, or topic explicitly
    general  = "general"   # catch-all — semantic + lexical ranking decides


# ── Regex fallback ────────────────────────────────────────────────────────────
# Used when the LLM call fails. Not the primary path.

_SPECIFIC_RE = re.compile(
    r"(?:"
    # Explicit document/file reference: "the Eshicare SA brief", "resume.pdf"
    r"(?:the\s+)?\S+\.(?:pdf|docx?|md|txt|pptx?|xlsx?|csv)\b"
    r"|"
    # Section or folder name reference: preposition + "the" + name
    r"\b(?:in|from|about|regarding|see|check|find)\s+the\s+[\"']?\w[\w\s-]{2,40}[\"']?"
    r")",
    re.IGNORECASE,
)

# Path-hint: explicit reference to a named section/document in the source.
_PATH_HINT_RE = re.compile(
    r"\b(week\s*\d+|finale|guides?|community[_\s]contributions?)\b",
    re.IGNORECASE,
)


# ── Public API ────────────────────────────────────────────────────────────────

def classify_intent(query: str) -> QueryIntent:
    """
    Regex-based intent classification. Used as fallback only.

    Pure regex — no LLM, no I/O. Returns in O(1) relative to query length.
    Prefer `analyse_query()` for the primary path.
    """
    q = query.strip()
    if _SPECIFIC_RE.search(q):
        return QueryIntent.specific
    return QueryIntent.general


def extract_path_hint(query: str) -> str | None:
    """
    Extract a source_ref path prefix from the query, if one is mentioned.

    Returns a normalised lowercase string suitable for use as a LIKE prefix
    in a SQL query (e.g. "week3", "finale", "guides"). Returns None if no
    recognisable path hint is found.
    """
    m = _PATH_HINT_RE.search(query.strip())
    if not m:
        return None
    return m.group(1).lower().replace(" ", "")


class QueryAnalysis(BaseModel):
    """Structured output from query analysis."""

    intent: QueryIntent
    path_hints: list[str] = []
    expanded_query: str = ""

    @field_validator("path_hints", mode="before")
    @classmethod
    def normalise_path_hints(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(h).lower().replace(" ", "") for h in v if h]

    @field_validator("intent", mode="before")
    @classmethod
    def coerce_intent(cls, v: object) -> QueryIntent:
        if isinstance(v, QueryIntent):
            return v
        try:
            return QueryIntent(str(v))
        except ValueError:
            return QueryIntent.general


_INTENT_SYSTEM_PROMPT = """\
You are a query classification assistant for a document retrieval system.

Classify the user's query and return a JSON object with exactly these fields:
- "intent": "specific" if the user explicitly names a document, file, section, or topic by name; \
"general" for everything else
- "path_hints": list of normalised slugs for any named documents or sections mentioned \
(lowercase, hyphens for spaces, empty list if none)
- "expanded_query": a concise rephrasing of the query (1–2 sentences max) optimised for \
semantic search — add relevant synonyms or context that would improve retrieval

Return ONLY valid JSON. No explanation. No markdown. No code blocks.

Examples:

Query: "what does the Eshicare SA brief say about pricing?"
{"intent":"specific","path_hints":["eshicare-sa-brief"],"expanded_query":"Eshicare SA brief pricing details cost structure"}

Query: "what projects have you built?"
{"intent":"general","path_hints":[],"expanded_query":"projects built portfolio work experience technical implementations"}

Query: "tell me about yourself"
{"intent":"general","path_hints":[],"expanded_query":"background profile identity skills experience summary"}

Query: "show me week 3"
{"intent":"specific","path_hints":["week3"],"expanded_query":"week 3 content curriculum materials"}
"""


def _regex_fallback(query: str) -> QueryAnalysis:
    """Synchronous regex-based fallback when the LLM call fails."""
    intent = classify_intent(query)
    path_hint = extract_path_hint(query)
    return QueryAnalysis(
        intent=intent,
        path_hints=[path_hint] if path_hint else [],
        expanded_query="",
    )


async def analyse_query(query: str) -> QueryAnalysis:
    """
    Classify a user query using an LLM call, with regex fallback.

    The LLM produces:
      - intent:         "specific" | "general"
      - path_hints:     named documents or sections the user referenced
      - expanded_query: a retrieval-optimised rephrasing of the query

    Falls back to regex classification automatically on any LLM error
    (provider failure, timeout, malformed JSON, validation error).
    """
    stripped = query.strip()
    if not stripped:
        return QueryAnalysis(intent=QueryIntent.general)

    try:
        # Import here to avoid circular imports at module load time.
        from app.domains.answering.llm_provider import get_llm_provider

        provider = get_llm_provider()
        response = await provider.complete(
            system_prompt=_INTENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": stripped}],
            max_tokens=150,
            temperature=0.0,
            generation_name="intent_classification",
        )

        raw = response.content.strip()
        # Strip accidental markdown fences if the model adds them
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()

        data = json.loads(raw)
        analysis = QueryAnalysis(
            intent=data.get("intent", "general"),
            path_hints=data.get("path_hints", []),
            expanded_query=data.get("expanded_query", ""),
        )
        logger.debug(
            "intent_classified",
            intent=analysis.intent,
            path_hints=analysis.path_hints,
            has_expansion=bool(analysis.expanded_query),
        )
        return analysis

    except Exception as exc:
        logger.warning(
            "intent_classification_llm_failed",
            error=str(exc),
            fallback="regex",
        )
        return _regex_fallback(stripped)
