# ADR 002 — Phase 2 Hybrid Retrieval And Evidence Packets

**Date:** 2026-04-22  
**Status:** Accepted

---

## Context

Phase 1 gave docubase deterministic file, symbol, relationship, and git indexes,
but retrieval was still primarily chunk-vector driven. That left three product
gaps:

- implementation questions could still miss exact files or symbols
- workspace chat still behaved too much like routed chunk search
- answer generation still received loose chunk lists instead of structured
  evidence packets

The canonical roadmap requires Phase 2 to make retrieval hybrid, planned, and
namespace-safe.

---

## Decision

We adopt a **hybrid retrieval architecture** with these rules:

1. **Query planning is explicit**
   Every retrieval turn builds a deterministic plan that chooses a retrieval
   mode, search layers, and evidence budgets.

2. **PostgreSQL FTS is the lexical search substrate**
   We use Postgres full-text search for:
   - chunk content + source refs
   - indexed file paths + framework roles
   - indexed symbol names + qualified names + signatures

   This keeps lexical search inside the existing tenant-aware relational stack.

3. **Candidate fusion happens before reranking**
   Retrieval now merges:
   - vector candidates
   - lexical chunk candidates
   - file-derived candidates
   - symbol-derived candidates
   - path-hint candidates
   - graph-guided candidates

4. **Chat consumes evidence packets**
   Retrieval returns structured evidence packets that carry:
   - chunks
   - files
   - symbols
   - hydrated spans
   - searched layers
   - negative-evidence scope
   - namespace identity (`twin_id`, `source_id`, `snapshot_id`)

5. **Workspace retrieval is policy-aware**
   Workspace routing still scopes evidence per twin, but final retrieval now
   respects the routed twin's snippet policy instead of bluntly disabling
   snippets.

---

## Consequences

- Retrieval is now more precise for implementation and onboarding questions.
- Workspace chat can stay grounded without silently losing allowed code evidence.
- Later phases can verify claims against packets instead of raw chunk blobs.
- Postgres becomes the explicit lexical substrate for Phase 2, so index
  maintenance is now part of schema rollout.

---

## Alternatives Considered

| Option | Rejected because |
|--------|------------------|
| Keep vector-only retrieval | Too weak for code intelligence questions |
| Add an external search engine now | Extra infrastructure before proving need |
| Push packet verification into prompts only | Too weak for trust and auditability |

