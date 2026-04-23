# ADR 003 — Phase 3 Evidence-Bound Answering

**Date:** 2026-04-22  
**Status:** Accepted

---

## Context

Phase 2 gave docubase structured retrieval evidence packets, but answer
generation still depended too heavily on prompt discipline. The remaining gaps
were:

- the model could still answer without tying itself to the packet mode
- explicit file and symbol references in answers were not being checked against
  the retrieved namespace
- absence claims were not consistently bounded to the searched layers
- workspace answers could still blur project boundaries if the model drifted

The canonical roadmap requires Phase 3 to make answers truthful by
construction, not only by prompt intent.

---

## Decision

We adopt an **evidence-bound answering path** with these rules:

1. **Answer generation gets an explicit contract**
   Single-project and workspace prompts now include an evidence contract that
   carries:
   - retrieval mode
   - searched layers
   - bounded negative-evidence scope
   - grounded files, symbols, and graph anchors

2. **Verification is cheap and deterministic by default**
   After generation, a lightweight verifier:
   - inspects explicit file and symbol references
   - checks them against the packet namespace
   - enforces workspace section labeling
   - bounds negative claims when they are too absolute

3. **At most one retry**
   If the verifier detects unsupported claims, it returns a regeneration hint.
   The answerer gets one retry only. If the second pass still fails, the system
   rewrites into a deterministic grounded fallback instead of returning an
   unsupported answer.

4. **Workspace leakage is a hard failure**
   Workspace answers must keep one project per labeled section. If the draft
   leaks evidence across projects or omits required labels, verification fails
   and the response falls back to a grounded per-project rewrite.

---

## Consequences

- Implementation answers are now forced to stay closer to retrieved files and
  symbols.
- Unsupported file and symbol references are filtered out before the user sees
  them.
- Absence claims become more trustworthy because they are explicitly bounded to
  searched layers.
- Workspace answers are stricter about project separation, which reduces
  cross-project contamination.

---

## Alternatives Considered

| Option | Rejected because |
|--------|------------------|
| Prompt-only grounding | Too weak for a trust-critical code intelligence product |
| Heavy LLM judge on every answer | Too expensive and slow for the default path |
| No deterministic fallback | Leaves unsupported claims visible when verification fails |
