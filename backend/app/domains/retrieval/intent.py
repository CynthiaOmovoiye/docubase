"""
Query intent classification for intent-aware retrieval.

`analyse_query()` is the primary entry point — it calls the LLM for a
structured classification and falls back to `classify_intent()` (regex) on
any error.  The LLM path adds path_hints extraction and an expanded_query
rewrite in a single <100ms round-trip (max_tokens=150, low-temperature).

`classify_intent()` is the pure-regex fallback — no LLM, no network, no DB.
It returns a `QueryIntent` enum value that the retrieval router uses to boost
preferred chunk types in the SQL score computation.

Design:
  - analyse_query() runs concurrently with the embedder in the chat service
  - LLM failure (timeout, parse error, invalid JSON) silently degrades to regex
  - Ties go to the more specific / earlier-listed intent (regex path)
  - Chunk type boosts are defined in the router, not here
  - The general intent is a catch-all for anything that doesn't match

Intent → typical chunk types boosted:
  change_query  → change_entry
  risk_query    → risk_note
  architecture  → architecture_summary, decision_record, hotspot
  onboarding    → memory_brief, hotspot, module_description
  file_specific → code_snippet, module_description (with path match)
  general       → no boost (standard cosine ranking)
"""

from __future__ import annotations

import json
import re
from enum import StrEnum

from pydantic import BaseModel, field_validator

from app.core.logging import get_logger

logger = get_logger(__name__)


class QueryIntent(StrEnum):
    change_query  = "change_query"   # "what changed", "last week", "recent commits"
    risk_query    = "risk_query"     # "risky", "fragile", "could break"
    architecture  = "architecture"   # "architecture", "overview", "how is this structured"
    onboarding    = "onboarding"     # "explain for new engineer", "where to start"
    file_specific = "file_specific"  # query contains a path or file extension
    general       = "general"        # catch-all


# ── Compiled patterns ─────────────────────────────────────────────────────────

_CHANGE_RE = re.compile(
    r"\b("
    r"what\s+changed|recent\s+changes?|last\s+week|last\s+month|"
    r"commits?|what['']?s\s+new|recently\s+updated|latest\s+updates?|"
    r"this\s+week|past\s+(week|month)|change\s+history|what\s+was\s+(added|removed|modified)|"
    r"git\s+log|activity"
    r")\b",
    re.IGNORECASE,
)

_RISK_RE = re.compile(
    r"\b("
    r"risks?|risky|fragile|dangerous|could\s+break|unstable|"
    r"technical\s+debt|TODO|FIXME|HACK|concern|worry|"
    r"weak\s+point|failure\s+point|anti.pattern|poorly|"
    r"warning|watch\s+out|careful|problematic|issue|bug.prone"
    r")\b",
    re.IGNORECASE,
)

_ARCHITECTURE_RE = re.compile(
    r"\b("
    r"architecture|overview|structure|how.?s\s+it\s+built|"
    r"system\s+design|high.level|walk\s+me\s+through|how\s+does\s+.+\s+work|"
    r"design\s+decision|tech\s+stack|dependencies|data\s+flow|"
    r"data\s+model|"
    r"how\s+is\s+.+\s+(structured|organized|built)|"
    r"what\s+(is|are)\s+the\s+(main|key|core)\s+(components?|modules?|parts?|layers?|domains?)"
    r")\b",
    re.IGNORECASE,
)

_ONBOARDING_RE = re.compile(
    r"\b("
    r"onboarding|new\s+(engineer|developer|hire|contributor)|"
    r"intern|joining|joined|"
    r"where\s+(do\s+i|should\s+i)\s+start|getting\s+started|"
    r"introduce\s+me|summarize\s+(for|this)|first\s+step|"
    r"orient|primer|beginner|just\s+joined|new\s+to\s+(this|the\s+project)"
    r")\b",
    re.IGNORECASE,
)

# File-specific: token with "/" (path separator) or known code file extension
_FILE_PATH_RE = re.compile(
    r"(?:^|\s)(?:\S+/\S+|\S+\.(?:py|ts|tsx|js|jsx|go|rs|rb|java|kt|swift|c|cpp|h|md|yaml|yml|json|toml|sql))\b",
    re.IGNORECASE,
)

# Path-hint: explicit reference to a named section/directory in the repo.
# Matches "week 3", "week3", "finale", "guides", "community contributions".
# Used to extract a source_ref prefix for guaranteed path-prefix retrieval
# that supplements the main vector search.
_PATH_HINT_RE = re.compile(
    r"\b(week\s*\d+|finale|guides?|community[_\s]contributions?)\b",
    re.IGNORECASE,
)


# ── Public API ────────────────────────────────────────────────────────────────

def classify_intent(query: str) -> QueryIntent:
    """
    Classify a user query into a QueryIntent category.

    Pure regex — no LLM, no I/O. Returns in O(1) relative to query length.
    Evaluation order determines precedence when multiple patterns match.
    """
    q = query.strip()

    if _CHANGE_RE.search(q):
        return QueryIntent.change_query

    if _RISK_RE.search(q):
        return QueryIntent.risk_query

    if _ARCHITECTURE_RE.search(q):
        return QueryIntent.architecture

    if _ONBOARDING_RE.search(q):
        return QueryIntent.onboarding

    if _FILE_PATH_RE.search(q):
        return QueryIntent.file_specific

    return QueryIntent.general


def extract_path_hint(query: str) -> str | None:
    """
    Extract a source_ref path prefix from the query, if one is mentioned.

    Returns a normalised lowercase string suitable for use as a LIKE prefix
    in a SQL query (e.g. "week3", "finale", "guides").  Returns None if no
    recognisable path hint is found.

    Examples:
      "what is week 3 about?"     → "week3"
      "walk me through the finale" → "finale"
      "tell me about the guides"   → "guides"
      "what changed last week?"    → None  (no section reference)
    """
    m = _PATH_HINT_RE.search(query.strip())
    if not m:
        return None
    # Normalise: remove internal spaces, lowercase ("week 3" → "week3")
    return m.group(1).lower().replace(" ", "")


# ── LLM-based query analysis ──────────────────────────────────────────────────

class QueryAnalysis(BaseModel):
    """Structured output from the LLM query analyser."""

    intent: QueryIntent
    path_hints: list[str] = []
    expanded_query: str = ""

    @field_validator("path_hints", mode="before")
    @classmethod
    def normalise_path_hints(cls, v: object) -> list[str]:
        """Normalise hints: lowercase, strip spaces, drop empties."""
        if not isinstance(v, list):
            return []
        return [str(h).lower().replace(" ", "") for h in v if h]

    @field_validator("intent", mode="before")
    @classmethod
    def coerce_intent(cls, v: object) -> QueryIntent:
        """Accept string values from LLM JSON output."""
        if isinstance(v, QueryIntent):
            return v
        try:
            return QueryIntent(str(v))
        except ValueError:
            return QueryIntent.general


_ANALYSE_SYSTEM = """\
You are a query analyser for Docbase: a document-grounded assistant. Attached materials may be \
resumes, policies, product docs, personal notes, or software repositories (code, architecture \
notes, change history, risk assessments, onboarding guides).

Given a user query, return ONLY a JSON object — no markdown fences, no prose.

Schema:
{
  "intent": "<change_query | risk_query | architecture | onboarding | file_specific | general>",
  "path_hints": ["<directory or section name explicitly mentioned in the query>"],
  "expanded_query": "<1-2 sentence rewrite that makes the query more precise for semantic search>"
}

Intent definitions:
  change_query  — asks about recent changes, commits, what was added/removed/modified
  risk_query    — asks about risks, fragility, technical debt, bugs, things to watch out for
  architecture  — asks about system design, structure, how components fit together, tech stack
  onboarding    — asks where to start, how to get oriented, explains for a new contributor
  file_specific — mentions a specific file path, directory, or file extension (.py, .ts, etc.)
  general       — anything that doesn't clearly fit the above

path_hints rules:
  - Only include directory/section names EXPLICITLY mentioned in the query
    (e.g. "week3", "finale", "src/api", "guides", "community_contributions")
  - Normalise: lowercase, no spaces ("week 3" → "week3")
  - Return [] if no path is mentioned

expanded_query rules:
  - Rewrite the query to be more specific and descriptive for semantic search
  - Keep it short: 1-2 sentences, no bullet points
  - Do not add information that isn't implied by the original query
  - For identity or biographical questions (name, role, education, resume, "who are you"), \
set expanded_query to "" (empty string). Do not reframe such questions as about a software product.

Return ONLY the JSON. Nothing else."""

# Fast path: skip LLM expansion that previously steered embeddings toward "software system" wording.
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


async def analyse_query(query: str) -> QueryAnalysis:
    """
    Classify a user query using the LLM and return a structured QueryAnalysis.

    This is the primary entry point for query analysis. It calls the LLM with a
    tight structured prompt (max_tokens=150) and falls back silently to the
    regex classifier on any error (timeout, invalid JSON, network failure).

    The call is lightweight (~100ms) and intended to run concurrently with the
    query embedding to avoid adding net latency to the retrieval pipeline.
    """
    stripped = query.strip()
    if _PROFILE_OR_IDENTITY_RE.search(stripped):
        rh = extract_path_hint(stripped)
        return QueryAnalysis(
            intent=QueryIntent.general,
            path_hints=[rh] if rh else [],
            expanded_query="",
        )

    from app.domains.answering.llm_provider import get_llm_provider

    try:
        provider = get_llm_provider()
        response = await provider.complete(
            system_prompt=_ANALYSE_SYSTEM,
            messages=[{"role": "user", "content": query.strip()}],
            max_tokens=150,
            temperature=0.0,
            generation_name="query_analysis",
        )
        # Strip accidental markdown fences
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", response.content.strip(), flags=re.MULTILINE
        )
        data = json.loads(cleaned)
        analysis = QueryAnalysis.model_validate(data)

        # Regex path_hint extraction as a safety net: if LLM missed an obvious
        # path hint that the regex would catch, add it.
        regex_hint = extract_path_hint(query)
        if regex_hint and regex_hint not in analysis.path_hints:
            analysis.path_hints.append(regex_hint)

        logger.debug(
            "query_analysis_llm",
            intent=analysis.intent.value,
            path_hints=analysis.path_hints,
        )
        return analysis

    except Exception as exc:
        logger.debug("query_analysis_llm_failed_falling_back", error=str(exc))
        # Graceful degradation: regex classifier + regex path hint
        regex_intent = classify_intent(query)
        regex_hint = extract_path_hint(query)
        return QueryAnalysis(
            intent=regex_intent,
            path_hints=[regex_hint] if regex_hint else [],
            expanded_query="",
        )
