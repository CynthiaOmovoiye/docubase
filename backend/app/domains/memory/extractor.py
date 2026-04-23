"""
LLM-based extraction functions for the Engineering Memory domain.

Each function receives already-policy-filtered chunks (no raw source files,
no secrets) and calls the LLM to synthesise structured knowledge.

Design principles:
  - Every function wraps LLM calls in try/except — malformed JSON or API errors
    return empty lists/strings, never raise. Callers should treat empty returns
    as graceful degradation.
  - Input chunks are filtered and capped before being passed to the LLM to
    stay within context window limits.
  - Uses get_llm_provider() from the answering domain — no new provider dependency.
  - Generated chunk dicts use source_ref = "__memory__/{twin_id}" to distinguish
    them from file-derived chunks.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from app.core.logging import get_logger
from app.domains.answering.llm_provider import get_llm_provider
from app.domains.memory.prompts import (
    ARCHITECTURE_EXTRACTION_SYSTEM,
    CHANGE_ENTRY_SYSTEM,
    MEMORY_BRIEF_SYSTEM,
    RISK_EXTRACTION_SYSTEM,
)

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Chunk types used as inputs to architecture extraction
_ARCH_INPUT_TYPES = {"module_description", "documentation", "dependency_signal", "architecture_summary"}
# Chunk types used as inputs to risk extraction
_RISK_INPUT_TYPES = {"module_description", "code_snippet"}

# Path prefixes that are noise for architecture/risk extraction.
# Migrations describe schema history, not application design.
# Build artefacts and lock files add no architectural signal.
_NOISE_PREFIXES = (
    "alembic/",
    "migrations/",
    "frontend/dist/",
    "frontend/node_modules/",
    "node_modules/",
    ".git/",
)
_NOISE_SUFFIXES = (
    ".lock",
    "-lock.json",
    ".pyc",
)

def _is_architecture_relevant(chunk: dict) -> bool:
    ref = chunk.get("source_ref", "").lower()
    if any(ref.startswith(p) for p in _NOISE_PREFIXES):
        return False
    if any(ref.endswith(s) for s in _NOISE_SUFFIXES):
        return False
    return True

# Max chunks / approximate token budget per LLM call.
# GPT-4o and most modern models have 128k context; we use up to ~20k tokens
# of input so the model can see the full breadth of a large codebase.
_MAX_INPUT_CHUNKS = 200
_MAX_INPUT_CHARS = 80_000  # ~20k tokens

# source_ref prefix for all LLM-generated chunks
def _memory_ref(twin_id: str) -> str:
    return f"__memory__/{twin_id}"


# ── JSON parsing helpers ───────────────────────────────────────────────────────

def _parse_json_object(text: str) -> dict:
    """Extract and parse a JSON object from LLM output, stripping markdown fences."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)


def _parse_json_array(text: str) -> list:
    """Extract and parse a JSON array from LLM output, stripping markdown fences."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)


def _select_chunks(
    all_chunks: list[dict],
    allowed_types: set[str],
    max_chunks: int = _MAX_INPUT_CHUNKS,
    max_chars: int = _MAX_INPUT_CHARS,
    diverse: bool = False,
) -> list[dict]:
    """
    Filter chunks to the allowed types, then cap by count and total char length.

    When diverse=True (used for architecture extraction), chunks are sampled
    proportionally across top-level directory prefixes before applying the
    global cap.  This ensures the LLM sees coverage of every major part of
    the codebase — engine/, connectors/, integrations/, core/, etc. — rather
    than being dominated by whichever directory sorts first alphabetically.

    Priority within each group: module_description > dependency_signal >
    architecture_summary > documentation > code_snippet.
    """
    filtered = [c for c in all_chunks if c.get("chunk_type") in allowed_types]

    priority = {
        "module_description": 0,
        "dependency_signal": 1,
        "architecture_summary": 2,
        "documentation": 3,
        "code_snippet": 4,
    }
    filtered.sort(key=lambda c: priority.get(c.get("chunk_type", ""), 99))

    if not diverse or len(filtered) <= max_chunks:
        # Simple path: no diversity needed
        selected: list[dict] = []
        total_chars = 0
        for chunk in filtered[:max_chunks]:
            content = chunk.get("content", "")
            if total_chars + len(content) > max_chars:
                break
            selected.append(chunk)
            total_chars += len(content)
        return selected

    # Diverse path: group by top-level directory prefix, then distribute slots.
    # Prefix = first path segment (e.g. "backend", "frontend", "scaffold").
    # Falls back to "" for flat files.
    by_prefix: dict[str, list[dict]] = defaultdict(list)
    for chunk in filtered:
        ref = chunk.get("source_ref", "")
        prefix = ref.split("/")[0] if "/" in ref else ""
        by_prefix[prefix].append(chunk)

    prefixes = list(by_prefix.keys())
    # Allocate at least 2 slots per prefix, distribute remainder proportionally
    base = max(2, max_chunks // max(len(prefixes), 1))
    quota: dict[str, int] = {}
    for p in prefixes:
        quota[p] = min(base, len(by_prefix[p]))

    # Fill remaining quota from largest groups first
    allocated = sum(quota.values())
    remaining = max_chunks - allocated
    if remaining > 0:
        for p in sorted(prefixes, key=lambda x: len(by_prefix[x]), reverse=True):
            available = len(by_prefix[p]) - quota[p]
            give = min(available, remaining)
            quota[p] += give
            remaining -= give
            if remaining <= 0:
                break

    # Build final list: take quota[p] from each prefix in priority order
    selected = []
    total_chars = 0
    for p in prefixes:
        for chunk in by_prefix[p][:quota[p]]:
            content = chunk.get("content", "")
            if total_chars + len(content) > max_chars:
                break
            selected.append(chunk)
            total_chars += len(content)
        if total_chars >= max_chars:
            break

    return selected


def _chunks_to_context(chunks: list[dict]) -> str:
    """Format chunk list into a context string for an LLM call."""
    parts = []
    for c in chunks:
        ref = c.get("source_ref", "")
        ctype = c.get("chunk_type", "")
        content = c.get("content", "")
        parts.append(f"[{ctype}] {ref}\n{content}")
    return "\n\n---\n\n".join(parts)


def _select_module_samples_by_group(
    existing_chunks: list[dict],
    max_groups: int = 20,
    max_chars: int = 6000,
) -> list[dict]:
    """
    Select at least one module_description chunk per top-level group.
    """
    relevant = [
        c for c in existing_chunks
        if c.get("chunk_type") == "module_description" and _is_architecture_relevant(c)
    ]
    if not relevant:
        return []

    by_group: dict[str, list[dict]] = defaultdict(list)
    for chunk in relevant:
        ref = chunk.get("source_ref", "")
        group = ref.split("/")[0] if "/" in ref else "_root"
        by_group[group].append(chunk)

    selected: list[dict] = []
    total_chars = 0
    for group in sorted(by_group.keys()):
        chunk = by_group[group][0]
        content = chunk.get("content", "")
        if total_chars + len(content) > max_chars:
            break
        selected.append(chunk)
        total_chars += len(content)
        if len(selected) >= max_groups:
            break
    return selected


def _format_structure_overview(structure_overview: list[dict]) -> str:
    lines = []
    for entry in structure_overview:
        dir_path = entry.get("dir_path", "_root")
        label = f"{dir_path}/" if dir_path != "_root" else "_root"
        file_paths = entry.get("file_paths") or []
        shown = ", ".join(f"`{path}`" for path in file_paths[:8])
        suffix = ""
        if len(file_paths) > 8:
            suffix = f" + {len(file_paths) - 8} more"
        lines.append(
            f"{label} ({entry.get('file_count', len(file_paths))} files) — {shown}{suffix}".rstrip()
        )
    return "\n".join(lines)


# ── Extraction functions ───────────────────────────────────────────────────────


async def extract_architecture_chunks(
    twin_id: str,
    existing_chunks: list[dict],
    trace_id: str | None = None,
) -> list[dict]:
    """
    Analyse module descriptions, docs, and dependency signals to extract:
      - One architecture_summary chunk (overall design)
      - N decision_record chunks (inferred design decisions)
      - N hotspot chunks (key modules worth knowing about)

    All returned chunks have source_ref = "__memory__/{twin_id}".
    Returns [] on any error.
    """
    relevant = [c for c in existing_chunks if _is_architecture_relevant(c)]
    selected = _select_chunks(relevant, _ARCH_INPUT_TYPES, diverse=True)
    if not selected:
        logger.info("memory_arch_extraction_skip_no_chunks", twin_id=twin_id)
        return []

    context = _chunks_to_context(selected)
    provider = get_llm_provider()

    try:
        response = await provider.complete(
            system_prompt=ARCHITECTURE_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": context}],
            max_tokens=4000,
            temperature=0.1,
            trace_id=trace_id,
            generation_name="memory_extraction_architecture",
        )
        data = _parse_json_object(response.content)
    except Exception as exc:
        logger.warning("memory_arch_extraction_failed", twin_id=twin_id, error=str(exc))
        return []

    ref = _memory_ref(twin_id)
    chunks: list[dict] = []

    # ── Architecture summary — one chunk ───────────────────────────────────────
    # Field names match the updated ARCHITECTURE_EXTRACTION_SYSTEM prompt schema:
    #   repo_type, repo_type_reasoning, summary, structure, technologies,
    #   notable_patterns, design_decisions
    # (old schema used: architecture_summary, tech_stack, key_modules, integration_points)
    repo_type = data.get("repo_type") or "unknown"
    repo_type_reasoning = data.get("repo_type_reasoning") or ""
    summary_text = data.get("summary") or ""
    technologies = data.get("technologies") or []
    notable_patterns = data.get("notable_patterns") or []

    if summary_text or repo_type != "unknown":
        # Lead with repo_type so the memory brief generation pass knows
        # what kind of repository it is before choosing section headings.
        full_text = f"**Repo Type:** {repo_type}"
        if repo_type_reasoning:
            full_text += f"\n**Reasoning:** {repo_type_reasoning}"
        if summary_text:
            full_text += f"\n\n{summary_text}"
        if technologies:
            full_text += "\n\n**Technologies:**\n" + "\n".join(f"- {t}" for t in technologies)
        if notable_patterns:
            full_text += "\n\n**Notable Patterns:**\n" + "\n".join(f"- {p}" for p in notable_patterns)
        chunks.append({
            "chunk_type": "architecture_summary",
            "content": full_text,
            "source_ref": ref,
            "chunk_metadata": {
                "extraction": "architecture",
                "repo_type": repo_type,
                "technologies": technologies,
            },
        })

    # Structure entries → hotspot chunks (new schema: "structure" not "key_modules")
    for entry in (data.get("structure") or [])[:10]:
        path = entry.get("path", "")
        role = entry.get("role", "")
        if path and role:
            chunks.append({
                "chunk_type": "hotspot",
                "content": f"**{path}**\n{role}",
                "source_ref": ref,
                "chunk_metadata": {"extraction": "hotspot", "module_path": path},
            })

    # Design decisions → decision_record chunks
    for dec in (data.get("design_decisions") or [])[:8]:
        decision = dec.get("decision", "")
        rationale = dec.get("rationale", "")
        if decision:
            chunks.append({
                "chunk_type": "decision_record",
                "content": f"**Decision:** {decision}\n**Rationale:** {rationale}",
                "source_ref": ref,
                "chunk_metadata": {"extraction": "decision"},
            })

    logger.info(
        "memory_arch_extraction_complete",
        twin_id=twin_id,
        chunks=len(chunks),
    )
    return chunks


async def extract_risk_chunks(
    twin_id: str,
    existing_chunks: list[dict],
    trace_id: str | None = None,
) -> list[dict]:
    """
    Analyse module descriptions and code snippets to identify:
      - N risk_note chunks (specific fragility or risk areas)

    All returned chunks have source_ref = "__memory__/{twin_id}".
    Returns [] on any error.
    """
    relevant = [c for c in existing_chunks if _is_architecture_relevant(c)]
    selected = _select_chunks(relevant, _RISK_INPUT_TYPES, diverse=True)
    if not selected:
        logger.info("memory_risk_extraction_skip_no_chunks", twin_id=twin_id)
        return []

    context = _chunks_to_context(selected)
    provider = get_llm_provider()

    try:
        response = await provider.complete(
            system_prompt=RISK_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": context}],
            max_tokens=2000,
            temperature=0.1,
            trace_id=trace_id,
            generation_name="memory_extraction_risk",
        )
        risks = _parse_json_array(response.content)
    except Exception as exc:
        logger.warning("memory_risk_extraction_failed", twin_id=twin_id, error=str(exc))
        return []

    ref = _memory_ref(twin_id)
    chunks: list[dict] = []
    for risk in risks[:10]:
        title = risk.get("title", "")
        description = risk.get("description", "")
        severity = risk.get("severity", "medium")
        affected = risk.get("affected_paths") or []
        if title and description:
            content = f"**{title}** ({severity.upper()})\n{description}"
            if affected:
                content += "\n\nAffected: " + ", ".join(f"`{p}`" for p in affected)
            chunks.append({
                "chunk_type": "risk_note",
                "content": content,
                "source_ref": ref,
                "chunk_metadata": {
                    "extraction": "risk",
                    "severity": severity,
                    "affected_paths": affected,
                },
            })

    logger.info(
        "memory_risk_extraction_complete",
        twin_id=twin_id,
        risks=len(chunks),
    )
    return chunks


async def extract_change_entry_chunks(
    twin_id: str,
    commit_history: list[dict],
    trace_id: str | None = None,
) -> list[dict]:
    """
    Convert raw commit metadata into change_entry chunks grouped by week.

    commit_history: list of {sha, message, author_name, author_date, files_changed,
                              additions, deletions}
    All returned chunks have source_ref = "__memory__/{twin_id}".
    Returns [] if commit_history is empty or on any error.
    """
    if not commit_history:
        return []

    # Cap input to avoid huge prompts
    commits_to_use = commit_history[:100]
    context = json.dumps(commits_to_use, indent=2)

    provider = get_llm_provider()

    try:
        response = await provider.complete(
            system_prompt=CHANGE_ENTRY_SYSTEM,
            messages=[{"role": "user", "content": context}],
            max_tokens=1500,
            temperature=0.1,
            trace_id=trace_id,
            generation_name="memory_extraction_changes",
        )
        entries = _parse_json_array(response.content)
    except Exception as exc:
        logger.warning("memory_change_extraction_failed", twin_id=twin_id, error=str(exc))
        return []

    ref = _memory_ref(twin_id)
    chunks: list[dict] = []
    for entry in entries[:12]:  # max 12 weeks = 3 months
        period = entry.get("period", "")
        summary = entry.get("summary", "")
        files_touched = entry.get("files_touched") or []
        commit_count = entry.get("commit_count", 0)
        themes = entry.get("themes") or []
        if period and summary:
            content = f"**{period}** ({commit_count} commit{'s' if commit_count != 1 else ''})\n{summary}"
            if files_touched:
                shown = files_touched[:8]
                content += "\n\nFiles: " + ", ".join(f"`{f}`" for f in shown)
                if len(files_touched) > 8:
                    content += f" + {len(files_touched) - 8} more"
            chunks.append({
                "chunk_type": "change_entry",
                "content": content,
                "source_ref": ref,
                "chunk_metadata": {
                    "extraction": "change_history",
                    "period": period,
                    "commit_count": commit_count,
                    "files_touched": files_touched[:20],
                    "themes": themes,
                },
            })

    logger.info(
        "memory_change_extraction_complete",
        twin_id=twin_id,
        entries=len(chunks),
    )
    return chunks


async def generate_memory_brief(
    twin_id: str,
    architecture_text: str | None,
    arch_chunk_dicts: list[dict],
    risk_chunks: list[dict],
    change_chunks: list[dict],
    existing_chunks: list[dict],
    feature_chunks: list[dict] | None = None,
    auth_flow_chunks: list[dict] | None = None,
    onboarding_chunks: list[dict] | None = None,
    structure_overview: list[dict] | None = None,
    graph_context: str | None = None,
    implementation_fact_digest: str | None = None,
    topic_artifact_digest: str | None = None,
    trace_id: str | None = None,
) -> str:
    """
    Synthesise the full Project Memory Brief markdown document.

    Assembles all extracted facts and calls the LLM to produce the final narrative.
    Returns a markdown string. Does NOT write to the DB — caller is responsible.
    Returns empty string on any error.
    """
    # Build a context document from the extracted facts
    sections: list[str] = []

    if structure_overview:
        sections.append(
            "## Structure Overview (EVERY directory must appear in output)\n\n"
            + _format_structure_overview(structure_overview)
        )

    if implementation_fact_digest and implementation_fact_digest.strip():
        sections.append(implementation_fact_digest.strip())

    if topic_artifact_digest and topic_artifact_digest.strip():
        sections.append(topic_artifact_digest.strip())

    logger.info("Architecture text: in generate_memory_brief in extractor.py", architecture_text=architecture_text)
    if architecture_text:
        sections.append(f"## Architecture Facts\n\n{architecture_text}")

    hotspot_lines = [
        c["content"]
        for c in arch_chunk_dicts
        if c.get("chunk_type") == "hotspot" and c.get("content")
    ]
    if hotspot_lines:
        sections.append("## Module Structure (from architecture extraction)\n\n" + "\n\n".join(hotspot_lines))

    if feature_chunks:
        feature_lines = [c["content"] for c in feature_chunks if c.get("content")]
        if feature_lines:
            sections.append("## Feature Coverage\n\n" + "\n\n".join(feature_lines))

    if auth_flow_chunks:
        auth_lines = [c["content"] for c in auth_flow_chunks if c.get("content")]
        if auth_lines:
            sections.append("## Authentication / Authorization Signals\n\n" + "\n\n".join(auth_lines))

    if onboarding_chunks:
        onboarding_lines = [c["content"] for c in onboarding_chunks if c.get("content")]
        if onboarding_lines:
            sections.append("## Onboarding Map\n\n" + "\n\n".join(onboarding_lines))

    if risk_chunks:
        risk_lines = [c["content"] for c in risk_chunks]
        sections.append("## Risk Areas\n\n" + "\n\n".join(risk_lines))

    if change_chunks:
        change_lines = [c["content"] for c in change_chunks]
        sections.append("## Recent Changes\n\n" + "\n\n".join(change_lines))

    # Add a sample of module descriptions for the "Where to Start" section
    module_chunks = _select_module_samples_by_group(existing_chunks)
    if module_chunks:
        module_lines = [
            f"`{c.get('source_ref', '')}` — {c.get('content', '')[:200]}"
            for c in module_chunks
        ]
        sections.append("## Module Inventory\n\n" + "\n".join(module_lines))

    if graph_context:
        sections.append(f"## Entity Relationship Graph\n\n{graph_context}")

    if not sections:
        logger.warning("memory_brief_no_context", twin_id=twin_id)
        return ""

    context = "\n\n---\n\n".join(sections)
    provider = get_llm_provider()

    try:
        response = await provider.complete(
            system_prompt=MEMORY_BRIEF_SYSTEM,
            messages=[{"role": "user", "content": context}],
            max_tokens=4000,
            temperature=0.2,
            trace_id=trace_id,
            generation_name="memory_brief_generation",
        )
        brief = response.content.strip()
        brief = re.sub(r"```mermaid\n.*?```", "", brief, flags=re.DOTALL).strip()
        logger.info(
            "memory_brief_generated",
            twin_id=twin_id,
            length=len(brief),
        )
        return brief
    except Exception as exc:
        logger.warning("memory_brief_generation_failed", twin_id=twin_id, error=str(exc))
        return ""
