# ADR 005 — Phase 5 Trust, Evaluation, And SLOs

**Date:** 2026-04-22  
**Status:** Accepted

---

## Context

Phases 0 through 4 gave docbase strict evidence contracts, deterministic
implementation indexes, hybrid retrieval, evidence-bound answering, and
evidence-backed memory. The remaining gap was operational trust:

- owners could not clearly see freshness, parser coverage, or stale sources
- chat quality signals were mostly implicit in logs and verifier behavior
- latency budgets existed in the roadmap but were not enforced or monitored
- evaluation coverage by persona and query mode was not captured in a canonical
  suite

The roadmap requires Phase 5 to make repo intelligence measurable, visible, and
auditable.

---

## Decision

We adopt a **trust and evaluation layer** with these rules:

1. **Source trust state is owner-visible**
   Source responses now enrich index health with dynamic freshness, stale
   detection, and parser coverage percentages. The owner sources UI surfaces
   strict vs legacy state, freshness, stale warnings, and implementation index
   density.

2. **Chat logs deterministic quality metrics**
   The chat path now emits structured metrics for:
   - grounded anchor presence
   - citation count
   - verifier catches / rewrites
   - bounded-negative handling
   - workspace section completeness and leakage detection

3. **Latency budgets are explicit**
   Retrieval, generation, verification, and total-turn budgets are configured
   and checked at runtime. Budget overruns are logged as dedicated warnings
   instead of being buried in generic latency numbers.

4. **Golden evaluation suites are first-class artifacts**
   A canonical repo-intelligence golden suite now exists for engineer,
   recruiter, PM, and workspace-comparison questions. The suite is loadable and
   machine-checkable so coverage stays explicit.

5. **Usefulness joins the async evaluator**
   The background LLM judge now scores usefulness in addition to grounding,
   depth, format, and faithfulness.

---

## Consequences

- Owners can tell when a source is fresh, stale, parser-rich, or still legacy.
- Runtime quality becomes observable without waiting for an offline review.
- Latency regressions become visible as budget violations instead of vague slow
  chat complaints.
- Evaluation coverage is easier to expand as new product personas and question
  modes are added.

---

## Alternatives Considered

| Option | Rejected because |
|--------|------------------|
| Keep trust signals only in backend logs | Owners would still lack product-visible confidence cues |
| Add a heavy online LLM judge to every response | Too expensive and too risky for latency budgets |
| Treat source freshness as a static stored field only | It would drift without request-time enrichment |
| Rely on ad hoc test prompts instead of a golden suite | Coverage would stay implicit and fragile |
