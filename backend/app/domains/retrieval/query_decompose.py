"""
Lightweight query term extraction for retrieval planning.

Replaces the heavier repo-intelligence decomposer with a small tokenizer
sufficient for lexical / hybrid search hints.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[A-Za-z0-9_./+\-]{2,}")


def decompose_query_labels(query: str) -> list[str]:
    """Return salient tokens / labels from the user query (deduped, capped)."""
    if not query or not query.strip():
        return []
    seen: set[str] = set()
    labels: list[str] = []
    for m in _TOKEN_RE.finditer(query):
        t = m.group(0).strip().lower()
        if len(t) < 2 or t in seen:
            continue
        seen.add(t)
        labels.append(t)
        if len(labels) >= 16:
            break
    return labels


def search_terms_from_query(
    *,
    query: str,
    search_query: str,
    labels: list[str],
) -> list[str]:
    """Terms used for optional structured fact search (stub returns labels)."""
    base = search_query.strip() or query.strip()
    terms = list(labels)
    if base:
        terms.insert(0, base)
    # Dedupe preserving order
    out: list[str] = []
    seen: set[str] = set()
    for t in terms:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out[:24]
