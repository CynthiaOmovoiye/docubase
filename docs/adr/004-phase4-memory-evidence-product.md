# ADR 004 — Phase 4 Memory As Evidence Product

**Date:** 2026-04-22  
**Status:** Accepted

---

## Context

Earlier memory extraction gave docbase useful summaries, but the memory layer
was still too dependent on free-form synthesis over retrieved chunks. That left
two gaps:

- memory artifacts were not consistently tied back to deterministic files,
  symbols, relationships, and git activity
- workspace-level memory had no first-class storage model, so workspace
  synthesis could not evolve cleanly

The canonical roadmap requires Phase 4 to rebuild memory on top of the
deterministic evidence layer from Phases 0–3.

---

## Decision

We adopt an **evidence-backed memory product** with these rules:

1. **Twin memory starts from deterministic evidence**
   Memory extraction now loads indexed files, indexed symbols, indexed
   relationships, structure inventory, and git activity before producing new
   artifacts.

2. **New twin memory artifacts are first-class chunks**
   The system now writes:
   - `feature_summary`
   - `auth_flow`
   - `onboarding_map`

   Existing `risk_note`, `change_entry`, and `memory_brief` remain, but they are
   now produced or enriched from the deterministic evidence bundle and include
   provenance metadata.

3. **Workspace synthesis gets its own table**
   Workspace-wide synthesis is stored in `workspace_memory_artifacts` instead of
   being attached to a twin. This keeps workspace memory aligned with the
   product model.

4. **Workspace chat may consume workspace synthesis**
   Workspace answering now receives the stored workspace synthesis artifact as an
   extra memory block when available.

---

## Consequences

- Memory artifacts are more traceable and more suitable for downstream
  retrieval.
- Memory brief generation now depends less on raw chunk prose and more on
  deterministic code intelligence.
- Workspace memory becomes a real product asset rather than a side effect.

---

## Alternatives Considered

| Option | Rejected because |
|--------|------------------|
| Keep memory chunk-only with no provenance upgrade | Too weak for trust and auditability |
| Store workspace synthesis on a twin | Breaks the workspace abstraction |
| Make Phase 4 entirely LLM-free | Too rigid for the narrative brief, though deterministic evidence remains the base |
