"""
Routing and query-shape heuristics for workspace + twin chat.

Kept free of imports from ``service`` / ``verifier`` to avoid cycles.
"""

from __future__ import annotations

import re

# Aliases that appear inside normal English questions — never use them to route a
# workspace message to a named twin (prevents e.g. "walk **through** …" matching a slug).
WORKSPACE_ROUTE_ALIAS_STOPWORDS: frozenset[str] = frozenset(
    {
        "walk",
        "through",
        "tell",
        "give",
        "show",
        "have",
        "has",
        "had",
        "you",
        "your",
        "me",
        "my",
        "we",
        "our",
        "they",
        "their",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
        "who",
        "how",
        "when",
        "where",
        "why",
        "from",
        "with",
        "into",
        "onto",
        "over",
        "about",
        "after",
        "also",
        "any",
        "are",
        "was",
        "were",
        "been",
        "the",
        "and",
        "but",
        "not",
        "for",
        "can",
        "may",
        "will",
        "all",
        "each",
        "every",
        "some",
        "such",
        "than",
        "then",
        "too",
        "very",
        "just",
        "only",
        "same",
        "both",
        "few",
        "more",
        "most",
        "other",
        "work",
        "works",
        "like",
        "help",
        "need",
        "want",
        "know",
        "get",
        "project",
        "projects",
    }
)


def query_prefers_workspace_aggregate_over_single_twin(query: str) -> bool:
    """
    True for questions about several / all workspace projects.

    Used to route workspace sessions to aggregate answering. The same shape of
    question on a **single-twin** session should not be forced through the
    implementation-style grounded-anchor verifier (resume twins have no code symbols).
    """
    lowered = (query or "").strip().lower()
    if not lowered:
        return False
    if re.search(
        r"\b(your|all|any|each|every|what|which|how many)\s+projects\b",
        lowered,
    ):
        return True
    if re.search(r"\bprojects\s+you(\s+have|\s+'ve|'ve)?\b", lowered):
        return True
    if re.search(r"\blist\s+(your\s+)?projects\b", lowered):
        return True
    return False
