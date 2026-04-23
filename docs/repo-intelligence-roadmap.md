# docbase Repo Intelligence Roadmap

## Status

Canonical roadmap and implementation guide for evolving docbase from a
chunk-first RAG system into a repository intelligence platform.

If this document conflicts with earlier notes, plans, or chat discussions,
this document wins.

### Companion: 0 → 100 execution plan

For a **sequenced master plan** that adds **canonical full-file persistence**, **implementation facts**, **capability/journey/status modeling**, **flow packets**, and **sprint-style execution**—while keeping this file’s evidence-lineage rules—see [SYSTEM_INTELLIGENCE_MASTER_PLAN.md](./SYSTEM_INTELLIGENCE_MASTER_PLAN.md).

---

## Why This Exists

docbase is not meant to be a generic summarizer over retrieved chunks.
It is meant to behave like an engineering intelligence layer that can answer:

- what exists in a project
- where behavior is implemented
- how a flow works
- what changed
- what is risky
- where an engineer should start
- what a user or candidate has built across projects

That requires stronger system layers than the current chunk-first retrieval
pipeline.

---

## Current System Reality

Today, the platform already has useful pieces:

- `sources.structure_index` gives a deterministic file-tree inventory
- the ingestion pipeline builds chunks and embeddings
- retrieval can use path hints and workspace routing
- memory extraction generates higher-level summaries
- graph extraction adds entity and relationship context

But the current stack still has important limits:

- `structure_index` is inventory only, not implementation semantics
- `chunks` mixes file-backed, synthetic, and memory-derived evidence in one table
- line spans are an optional metadata convention, not a hard invariant
- deterministic code extraction is shallow
- graph extraction is still LLM-over-chunks, not parser-first
- retrieval is still largely chunk-first
- workspace answers can still lose grounded code evidence
- generation is constrained by prompts, but not yet fully evidence-bound

This roadmap fixes those issues in a phased way.

---

## Core Product Decision

docbase should operate through four hard layers:

1. `Inventory`
   What files, directories, snapshots, and source segments exist.
2. `Implementation Index`
   Files, symbols, parser-derived relationships, and git metadata.
3. `Evidence Retrieval`
   Hybrid candidate search plus hydration from canonical snapshots.
4. `Evidence-Bound Answering`
   Answers, memory, and summaries constrained by grounded evidence.

`memory_brief` remains important, but it is a derived narrative layer, not the
source of truth for implementation behavior.

---

## Design Principles

- `structure_index` remains inventory only
- parser-first beats LLM-first for implementation truth
- chunks are not automatically canonical source-of-truth
- workspace intelligence must be policy-aware, not weakened
- every strong claim must be satisfiable by evidence in the same namespace
- cross-project comparisons must be explicit, never accidental
- verification must be cheap by default
- rollout must support legacy indexes during migration

---

## Key Terms

### Structure Index

`sources.structure_index` is the deterministic inventory layer.

Its job is to answer:

- what files and directories exist
- how they are grouped
- what snapshot or sync state they belong to
- how complete the known inventory is

Its job is not to answer:

- where authorization is implemented
- which function verifies a token
- what route loads the dashboard
- how a service calls into a model

### Canonical Snapshot

The authoritative version of source content used for hydration.

Examples:

- git commit snapshot for repo sources
- normalized PDF revision for PDF sources
- normalized HTML snapshot for crawled URLs
- normalized connector revision for Drive or similar sources

### Evidence Packet

A structured answer input assembled after retrieval. It should contain:

- in-scope project or twin identity
- files
- symbols
- hydrated spans or segments
- graph edges where relevant
- missing evidence
- searched layers for negative-evidence claims

---

## Evidence Model

The `chunks` table should continue to exist, but the platform must stop treating
every chunk as if it were the same kind of artifact.

Introduce explicit evidence lineage.

| Lineage | Meaning | Required Invariants | Hydration Rule |
|--------|---------|---------------------|----------------|
| `file_backed` | Derived from a file in a source snapshot | path, start line, end line, content hash, snapshot id, embedding profile | hydrate from canonical source snapshot |
| `connector_segment` | Derived from a non-git source segment | stable segment id, segment span, content hash, snapshot or revision id | hydrate from canonical connector snapshot |
| `synthetic_profile` | Career, skills, manual summaries, similar synthetic artifacts | normalized text hash, source identity | no git hydration required |
| `memory_derived` | `memory_brief`, `change_entry`, `risk_note`, similar memory artifacts | provenance refs when summarizing code | never primary source-of-truth for repo behavior |

### Important Rule

The strict span and hash contract applies to `file_backed` and
`connector_segment` evidence. It does not apply blindly to every `ChunkType`.

---

## Data Model Direction

### Extend Existing Tables

#### `sources`

Keep `structure_index`, but extend it with snapshot identity where available:

- commit SHA
- source snapshot id
- optional tree or root hash
- freshness metadata

Role:

- coverage
- routing hints
- sync correctness
- memory scaffolding

#### `chunks`

Keep `source_ref` for display and compatibility, but add first-class evidence
fields where lineage requires them:

- lineage
- snapshot id
- normalized path key or canonical segment id
- start line
- end line
- content hash
- embedding provider
- embedding model
- embedding dimensions
- optional embedding task id if needed

Important:

- repo line spans must move out of loose JSON conventions
- required invariants must be enforceable at schema and ingestion time

### Add New Indexes Or Tables

- file index
- symbol index
- deterministic relationship graph
- git metadata index
- embedding cache keyed by full embedding profile

---

## Canonical Hydration Rule

Retrieval must become two-stage:

1. `Candidate discovery`
   Find likely evidence using vector, lexical, path, symbol, and graph signals.
2. `Hydration`
   Materialize the winning evidence from canonical snapshots.

Hydration precedence:

1. canonical git snapshot or equivalent source snapshot
2. canonical normalized connector snapshot
3. stored `chunks.content` only as a temporary legacy fallback during migration

This is required so answers remain reproducible and auditable.

Every evidence packet should carry:

- `doctwin_id`
- `source_id`
- `snapshot_id`
- commit or revision identity where available

---

## Non-Git Segment Rules

Not every source is a repo, so non-git sources need first-class segment rules.

Examples:

- PDF: document id, page index, block id or char span
- URL: URL, content hash, section anchor or heading identity
- Drive: file id, revision id, segment identity

These segments should work exactly like repo evidence:

- candidate id first
- canonical hydration second
- hash validation before use in strict evidence mode

---

## Search And Retrieval Direction

Retrieval should no longer be single-mode dense search.

Use hybrid fusion:

- vector similarity
- lexical search
- path and filename search
- symbol search
- bounded graph expansion

An explicit search substrate decision is required:

- Postgres full-text search
- external search engine
- managed search service

This decision must cover:

- index rebuild on rechunk
- multi-tenant isolation
- latency budget
- operational complexity

---

## Namespace Safety

Every evidence item must carry namespace identity:

- `doctwin_id`
- `source_id`
- `snapshot_id`

Rules:

- no cross-project claim satisfaction by accident
- no blending evidence across twins in normal workspace answers
- comparisons must be explicit
- verifier must reject claims attributed to project A when only project B
  evidence exists

---

## Cheap Verification

Verification is required, but it should be cheap by default.

Default verifier behavior:

- extract claim-like entities, technologies, and implementation assertions
- compare them against the allowed evidence set
- enforce namespace rules
- strip or rewrite unsupported claims
- allow at most one retry
- stay within a bounded latency budget

A heavier LLM judge can remain optional and SLO-gated.

---

## Phased Implementation Plan

## P0: Trustworthy Indexing Foundation

Goal: make the index trustworthy before making it smarter.

Deliverables:

- content-addressed sync with per-file hashes
- optional directory Merkle summaries
- chunk lineage classification
- guaranteed spans and hashes for `file_backed` evidence
- canonical snapshot hydration
- candidate discovery to hydration split
- completeness and freshness telemetry
- strict vs legacy evidence mode
- owner-visible index health states
- backfill and rechunk migration path
- latency budgets for default chat flows

What this changes for the product:

- the system knows exactly what changed
- evidence becomes traceable to the right snapshot
- users can see whether a source is fully trustworthy or still on a legacy index

## P1: Deterministic Implementation Index

Goal: make the system know what code objects exist and where.

Deliverables:

- file index
- symbol index
- parser-based extraction for routes, handlers, middleware, guards, models,
  jobs, pages, loaders, and actions where feasible
- parser-first relationship graph
- git metadata index
- embedding cache keyed by full embedding profile

What this changes for the product:

- better answers to "where is this implemented?"
- better edit guidance
- better onboarding and architecture walkthroughs

## P2: Hybrid Retrieval And Evidence Planning

Goal: retrieve the right evidence for the right question type.

Deliverables:

- hybrid candidate fusion
- explicit lexical search substrate
- query planner by question mode
- evidence packets with project scope, files, symbols, hydrated spans,
  missing evidence, and negative-evidence scope
- per-project workspace packets
- policy-aware workspace evidence materialization

What this changes for the product:

- implementation questions stop getting broad summary answers
- workspace answers become project-aware and well labeled
- exact technical identifiers become easier to find

## P3: Evidence-Bound Answering

Goal: make the answerer truthful by construction.

Deliverables:

- answer modes aligned to planner modes
- claim-to-evidence alignment
- bounded negative-evidence discipline
- cheap default verifier
- cross-project leakage guard

What this changes for the product:

- fewer hallucinations
- fewer invented snippets
- more explicit and trustworthy uncertainty

## P4: Memory As Evidence Product

Goal: rebuild memory artifacts on top of deterministic evidence.

Deliverables:

- feature summaries
- auth flow summaries
- onboarding maps
- risk and change summaries
- workspace synthesis artifacts
- provenance links from memory bullets back to files, symbols, and spans

What this changes for the product:

- memory becomes more trustworthy
- memory becomes useful for engineering and recruiting flows
- `memory_brief` becomes a durable product asset, not a prompt crutch

## P5: Evaluation, UX Trust, And SLOs

Goal: make repo intelligence measurable and visible.

Deliverables:

- golden evaluation suites by user type and question mode
- metrics for grounding, citations, cross-project separation, verifier catches,
  false "not present" rate, freshness, and usefulness
- owner UI for strict vs legacy, freshness, parser coverage, and stale sources
- latency budgets and monitoring

What this changes for the product:

- quality becomes measurable
- trust becomes visible in the UI
- regressions become catchable before release

---

## Migration And Rollout Rules

- do not freeze the product during backfill
- legacy indexes remain readable during migration
- strict evidence mode turns on only when invariants are satisfied
- cut over by rolling flags, not by a single big-bang switch
- do not claim strict evidence behavior for sources that have not been backfilled

---

## Implementation Status

Phase 1 v1 now exists in the codebase:

- `source_snapshots` and `source_files` retain policy-cleared canonical text by source snapshot
- ingestion writes the source mirror before derived chunks and indexes
- retrieval hydration checks the mirror before legacy provider/local fallback
- evidence health reports canonical mirror readiness and mirrored file counts
- integration coverage verifies full snapshot writes, delta carry-forward, line-span reads, and mirror-backed hydration

Phase 2 v2 now exists in the codebase:

- `implementation_facts` stores deterministic behavior facts by source/twin/snapshot
- fact taxonomy covers routes, handlers, auth checks, API calls, calls, data models, dependencies, UI actions, service edges, and model edges
- ingestion emits fact rows from the canonical mirror and span-backed `implementation_fact` chunks for retrieval compatibility
- fact chunks hydrate from `implementation_facts` by `fact_key`
- source health reports `facts_indexed` and `fact_schema_version` (currently `4` after validation-constraint facts)
- retrieval boosts implementation facts for implementation/onboarding/workspace questions
- existing dev sources were rebuilt with the Phase 2 fact layer

The remaining roadmap still applies: the mirror and fact layer are the foundation, not the final intelligence layer. Phase 3 is in progress (v3 fact schema adds hook/route/job/DI fact types and deeper emitters); Phase 4+ must build flow/status/capability packets and memory from this canonical substrate.

---

## Open Decisions

These decisions should be resolved in an ADR or implementation memo before the
relevant phase begins:

1. lexical search substrate
2. git hydration path and rate-limit strategy
3. connector snapshot storage format per source type
4. strict evidence mode granularity: per source vs per twin
5. whether a heavy LLM verifier exists at all

---

## Recommended Critical Path

If phases need to be narrowed into the most important implementation order:

1. chunk lineage plus strict span and hash contract
2. canonical hydration and backfill strategy
3. file index plus symbol index
4. parser-first graph plus git metadata index
5. hybrid retrieval and search substrate
6. workspace evidence packets and namespace enforcement
7. cheap verifier
8. memory rebuild on deterministic evidence
9. evaluation harness and trust UX

---

## Success Standard

docbase should be able to answer questions like these with grounded,
software-engineering-level precision:

- how is authorization handled on Scaffold
- where do I add logout
- how is dashboard data loaded
- what changed recently in auth
- what projects use Python and how
- what is left to finish for week 6
- compare Scaffold and Production auth implementations

And it should do so by:

- using the correct project scope
- grounding claims in hydrated evidence
- labeling workspace results clearly
- refusing unsupported claims
- surfacing uncertainty honestly

---

## How To Use This Document

- use this roadmap as the canonical implementation guide for repo intelligence
- when planning or implementing a phase, update this file if scope changes
- when a decision affects schema, indexing, retrieval, or trust UX, add an ADR
- do not treat ad hoc chat plans as authoritative once they diverge from this file
