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
  - Generated chunk dicts use source_ref = "__memory__/{doctwin_id}" to distinguish
    them from file-derived chunks.
"""

from __future__ import annotations

import json
import re

from app.core.logging import get_logger
from app.domains.answering.llm_provider import get_llm_provider
from app.domains.memory.prompts import MEMORY_BRIEF_SYSTEM

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Max chunks / approximate token budget per LLM call.
# GPT-4o and most modern models have 128k context; we use up to ~20k tokens
# of input so the model can see the full breadth of a large codebase.
_MAX_INPUT_CHUNKS = 200
_MAX_INPUT_CHARS = 80_000  # ~20k tokens

# source_ref prefix for all LLM-generated chunks
def _memory_ref(doctwin_id: str) -> str:
    return f"__memory__/{doctwin_id}"


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
    max_chunks: int = _MAX_INPUT_CHUNKS,
    max_chars: int = _MAX_INPUT_CHARS,
) -> list[dict]:
    """
    Cap chunks by count and total character length for LLM context budget.
    """
    selected: list[dict] = []
    total_chars = 0
    for chunk in all_chunks[:max_chunks]:
        content = chunk.get("content", "")
        if total_chars + len(content) > max_chars:
            break
        selected.append(chunk)
        total_chars += len(content)
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



async def generate_memory_brief(
    doctwin_id: str,
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

    # Add actual document content — full text, not truncated summaries.
    # This is the primary input for person/document briefs (resumes, profiles, etc.)
    # Include all non-memory chunks up to a reasonable char budget.
    content_chunks = [
        c for c in existing_chunks
        if not str(c.get("source_ref", "")).startswith("__memory__/")
        and c.get("content")
    ]
    full_doc_chunk_count = 0
    full_doc_chars = 0
    if content_chunks:
        content_budget = 60_000  # ~15k tokens — enough for a full resume or several docs
        content_parts: list[str] = []
        total = 0
        for c in content_chunks:
            text = c.get("content", "")
            ref = c.get("source_ref", "")
            ctype = c.get("chunk_type", "")
            label = f"[{ref}]" if ref else f"[{ctype}]"
            entry = f"{label}\n{text}"
            if total + len(entry) > content_budget:
                break
            content_parts.append(entry)
            total += len(entry)
            full_doc_chunk_count += 1
        full_doc_chars = total
        if content_parts:
            joined = "\n\n---\n\n".join(content_parts)
            sections.append(
                "## Full Document Content (extract all facts from this)\n\n" + joined
            )

    if graph_context:
        sections.append(f"## Entity Relationship Graph\n\n{graph_context}")

    if not sections:
        logger.warning("memory_brief_no_context", doctwin_id=doctwin_id)
        return ""

    context = "\n\n---\n\n".join(sections)

    # Diagnostic: log what's being assembled for the brief (section sizes + source coverage)
    section_labels = []
    for s in sections:
        first_line = s.split("\n")[0][:80]
        section_labels.append(f"{first_line} ({len(s)} chars)")
    non_memory = [
        c for c in existing_chunks
        if not str(c.get("source_ref", "")).startswith("__memory__/")
    ]
    ref_roots: dict[str, int] = {}
    for c in non_memory:
        ref = str(c.get("source_ref") or "") or "(empty_ref)"
        root = ref.split("/")[0] if "/" in ref else ref
        ref_roots[root] = ref_roots.get(root, 0) + 1
    arch_preview = (architecture_text or "")[:400]
    logger.info(
        "memory_brief_context_assembled",
        doctwin_id=doctwin_id,
        total_chars=len(context),
        section_count=len(sections),
        sections=section_labels,
        content_chunks_total=len(non_memory),
        full_document_section_chunks=full_doc_chunk_count,
        full_document_section_chars=full_doc_chars,
        source_ref_root_counts=ref_roots,
        architecture_text_len=len(architecture_text or ""),
        architecture_text_preview=arch_preview,
    )
    if content_chunks:
        first = next(
            (c for c in content_chunks if not str(c.get("source_ref", "")).startswith("__memory__/")),
            content_chunks[0],
        )
        logger.info(
            "memory_brief_first_content_chunk",
            doctwin_id=doctwin_id,
            source_ref=first.get("source_ref", ""),
            chunk_type=first.get("chunk_type", ""),
            content_len=len(first.get("content", "")),
            content_preview=(first.get("content") or "")[:300],
        )

    provider = get_llm_provider()

    try:
        response = await provider.complete(
            system_prompt=MEMORY_BRIEF_SYSTEM,
            messages=[{"role": "user", "content": context}],
            max_tokens=6000,
            temperature=0.15,
            trace_id=trace_id,
            generation_name="memory_brief_generation",
        )
        brief = response.content.strip()
        brief = re.sub(r"```mermaid\n.*?```", "", brief, flags=re.DOTALL).strip()
        logger.info(
            "memory_brief_generated",
            doctwin_id=doctwin_id,
            length=len(brief),
        )
        return brief
    except Exception as exc:
        logger.warning("memory_brief_generation_failed", doctwin_id=doctwin_id, error=str(exc))
        return ""
