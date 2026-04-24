"""
Query intent classification for document-aware retrieval.

Two intents only:
  specific — user references a named document, section, or file by name
  general  — everything else (semantic + lexical handles it)

`analyse_query()` is a thin async wrapper for callers that previously awaited it.
It runs no LLM — pure regex, no I/O. The LLM call was removed because it added
~100ms of latency per query and produced code-centric intent labels that actively
harmed document retrieval quality.

`extract_path_hint()` remains — it catches explicit section/document name mentions
and feeds guaranteed path-prefix retrieval in the router.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, field_validator

from app.core.logging import get_logger

logger = get_logger(__name__)


class QueryIntent(StrEnum):
    specific = "specific"  # query names a document, section, or topic explicitly
    general  = "general"   # catch-all — semantic + lexical ranking decides


# Signals that the user is referencing a specific named piece of content
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
# Matches "week 3", "week3", "finale", "guides", "community contributions".
_PATH_HINT_RE = re.compile(
    r"\b(week\s*\d+|finale|guides?|community[_\s]contributions?)\b",
    re.IGNORECASE,
)

# Identity/profile queries — skip query expansion so the embedding stays
# grounded in identity language rather than drifting toward "software system".
_PROFILE_OR_IDENTITY_RE = re.compile(
    r"\b("
    r"your\s+name|who\s+are\s+you|what(?:'s|\s+is)\s+your\s+name|"
    r"tell\s+me\s+about\s+yourself|your\s+(?:full\s+)?name|"
    r"how\s+(?:do\s+you|should\s+i)\s+call\s+you|"
    r"what(?:'s|\s+is)\s+your\s+(?:current\s+)?role|your\s+background|"
    r"your\s+education|(?:where\s+did\s+you|which\s+university)|\bresume\b|\bcv\b"
    r")\b",
    re.IGNORECASE,
)


# ── Public API ────────────────────────────────────────────────────────────────

def classify_intent(query: str) -> QueryIntent:
    """
    Classify a user query into a QueryIntent category.

    Pure regex — no LLM, no I/O. Returns in O(1) relative to query length.
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


async def analyse_query(query: str) -> QueryAnalysis:
    """
    Classify a user query and extract path hints.

    Async for API compatibility with callers that await it. Runs no LLM —
    pure regex, zero network I/O, zero latency overhead.
    """
    stripped = query.strip()
    intent = classify_intent(stripped)
    path_hint = extract_path_hint(stripped)
    return QueryAnalysis(
        intent=intent,
        path_hints=[path_hint] if path_hint else [],
        expanded_query="",
    )
