# System intelligence master plan (0 → 100)

**Audience:** founders, PMs, and engineers executing in Cursor phase-by-phase.
**Companion:** technical evidence-lineage and hydration detail remain in [repo-intelligence-roadmap.md](./repo-intelligence-roadmap.md). This document is the sequenced product and architecture path from today’s stack to full-system, engineer-grade answers.

**Naming:** the product is referred to internally as *docbase* in some docs, while the repository is the *docbase*. Treat both as the same product surface unless you intentionally separate brand and implementation later.

---

## 1. Executive summary

The chat model is not the primary bottleneck. The current system is mostly behaving honestly: it answers from retrieved evidence and memory, and it becomes cautious when implementation evidence is too thin to support a confident answer.

### Current state

Before Phase 1, connectors fetched raw source content, but the platform primarily persisted **derived knowledge artifacts** such as chunks, embeddings, and implementation index rows.

As of **Phase 1 v1**, the platform also persists a canonical mirror of **policy-cleared, retrievable text files** by `source_id + snapshot_id`, so strict evidence can hydrate from docbase-owned storage instead of provider refetches or stale chunk text. Future hardening should expand this into richer retention policy states for blocked/high-risk files where product policy allows.

### Target state

To move from **0 → 100**, the evidence substrate must change:

1. **Persist a canonical mirror of every retrievable file** per source revision, with strong security, tenant isolation, and revision identity.
2. **Derive structured implementation intelligence from that mirror** — facts, routes, flows, graphs, capability maps, and status signals — rather than relying mainly on lossy `module_description` and optional bounded snippets.
3. **Separate “the system knows the code” from “the user sees code.”** Internal reasoning should operate over the full source mirror. Output policy should determine whether code is exposed in answers.
4. **Retrieve and compose by question type** — product surface, user journey, implementation detail, gaps, and project status — instead of treating most questions as generic top-K chunk retrieval.
5. **Measure each phase** with evals, source health, and degraded-mode signals so every architectural change proves lift.

**Sequencing rule (non-negotiable):** do **not** start with prompt rewrites, bigger models, global `top_k` increases, or more auth-shaped heuristics. Start with **truth in storage**, then **facts**, then **retrieval/composition**, then **memory**, then **answer polish**, with evals wrapped around the whole system.

---

## 2. Product north star (what “100” means)

This is **not** an onboarding-only twin and **not** an auth-only explainer. It is a **general software intelligence layer** over attached documents and code-oriented sources (Drive, PDFs, URLs, markdown), with room to add more connectors later.

The product should be able to answer grounded questions about:

* what exists in the product,
* how users move through it,
* how individual flows are implemented,
* where the flow stops or is incomplete,
* what appears done versus pending,
* and how to drill down from product view to file-level detail.

### 2.1 Question classes the product must support

| Class | Example questions | What “good” looks like |
| --- | --- | --- |
| **Product surface** | “What can a user do in this app?” | A grounded capability map based on observable code structure: pages, features, engines, jobs, integrations, and major actions. |
| **User journey** | “What happens after sign-in?” “How is the dashboard loaded?” | A step-by-step trace: UI entry → handler → API client → route → validation → service → persistence → side effects, with explicit gaps where the chain stops. |
| **Implementation** | “How does registration work?” “How does the Intake engine work?” | File/symbol anchors plus behavior grounded in facts or hydrated source spans, not guessed architecture. |
| **Gap / completeness** | “Is signup implemented?” “What runs after auth?” | An explicit statement of what exists and what does not, for example: login exists, signup page/route is not grounded in the repo, and the observable flow currently stops after session establishment. |
| **Deep subsystem** | “Explain the five engines and how they connect.” | A subsystem map tied to modules, routes, orchestration code, persistence boundaries, and missing edges where applicable. |
| **Project status** | “Where are we?” “What’s next?” | A grounded status view that combines observable product surface, detected incomplete wiring, and recent change signals from commits or PRs. |

### 2.2 Reference behavior (Scaffold-style)

When true in the repository, the assistant should be able to say things like:

* there is no signup page and login is the current entry point,
* after login, the observable user-facing branches include project creation, brief upload, document generation, teams, tasks, verification, audit, and integrations, but only where the code supports those links,
* and when drilling into an engine, the explanation should cover entrypoints, orchestration, persistence, and where the implementation ends.

### 2.3 Relationship to “Cursor-level” understanding

Cursor succeeds in the IDE because it has full buffer context and rich indexing close to the code. In chat, docbase must reproduce that effect with:

* a canonical file store and line-addressable source,
* parser/tree-sitter or AST-driven structural intelligence,
* implementation facts,
* flow packets,
* and strict grounding with explainability.

The goal is not to imitate IDE context windows with thin chunks. The goal is to build a persistent internal system model that the chat interface can query.

---

## 3. Current architecture (honest baseline)

### Today, in simplified form

1. **Connectors fetch content.**
2. The **knowledge pipeline** builds derived `Chunk` rows such as documentation chunks, `module_description`, and optional bounded `code_snippet` chunks, alongside embeddings and an implementation index.
3. **Memory extraction** synthesizes higher-level artifacts from chunk and graph signals, including feature, auth, onboarding, risk, and change summaries, plus a memory brief.
4. **Chat** analyzes intent, retrieves a hybrid evidence packet, generates under strict grounding contracts, verifies the answer, and may fall back deterministically when grounded implementation detail is insufficient.
5. **Retrieval** currently includes specialized auth and engine heuristics, which make certain domains feel unusually strong compared to generic repos.

### Current strengths

The existing architecture already has useful foundations:

* ingestion jobs and source lifecycle,
* hybrid retrieval,
* implementation indexing,
* memory orchestration,
* strict answer contracts,
* verification,
* and early golden/eval direction.

### Current limitations

The most important limitation is that the current system compresses code into derived artifacts too early. That is acceptable for cautious summarization, but it is not enough for full-system software intelligence across arbitrary journeys, features, gaps, and project-status questions.

### Known inconsistency to fix early

`_load_doctwin_chunks()` in `backend/app/domains/memory/service.py` does not currently filter `Source.status` the same way strict retrieval does for `ready` evidence, which means memory can theoretically ingest chunks from sources that the chat path would not treat as fully answerable. That should be corrected before deeper architectural changes.

---

## 4. Core architectural correction

### 4.1 Two different meanings of “snapshot”

These two ideas should be kept separate:

* **`snapshot_id` / `snapshot_root_hash` today:** revision identity and integrity metadata for indexed artifacts. These are necessary and valuable, but they are **not** the same as storing the full repository text in a durable internal mirror.
* **Canonical source mirror target:** durable storage of normalized file tree plus full file text per source revision, suitable for hydration, diffing, re-parse, and span-accurate answers.

### 4.2 Internal fidelity vs external exposure

| Concern | Current state | Target behavior |
| --- | --- | --- |
| **Ingest** | Connectors fetch raw content, but the pipeline persists derived knowledge artifacts rather than a full canonical mirror. | Store full text per revision, subject to legal, tenant, and storage policy; classify binary/text; record content hash, line count, and language. |
| **Secrets** | Secret-flagged files are currently prevented from normal chunk processing in the knowledge pipeline. | Distinguish internal retention policy from user-visible exposure policy. Support “exists but redacted/high-risk” reasoning where product policy allows, without weakening security. |
| **`allow_code_snippets`** | Currently affects extraction/retrieval behavior as well as answer-time output. | Govern user-visible code exposure and optional retrieval convenience only, not whether the platform may internally reason over the source. |

### 4.3 What to keep from the current stack

Keep incrementally:

* connectors and jobs,
* `Source` lifecycle and snapshot metadata,
* hybrid retrieval concepts,
* verifier discipline,
* memory orchestration pattern,
* golden/eval harness direction,

while replacing the underlying evidence substrate beneath them.

---

## 5. Target layered model (end state)

Use these layers in documentation and implementation, and map tables/modules to them over time.

| Layer | Role |
| --- | --- |
| **A — Canonical source mirror** | Full files per `source_id` + `snapshot_id`, with hashes, paths, policy flags, and line-addressable content. This becomes the single internal source of truth for code text. |
| **B — Structural index** | Files, symbols, imports/exports, route maps, component maps, and relationships derived parser-first where possible. |
| **C — Implementation facts** | Normalized records of actual behavior: routes, handlers, API calls, validation boundaries, auth checks, service/repo/model edges, frontend→backend links, and other implementation facts, each tied to source spans. |
| **D — Product / flow / status model** | Capability graph (what users can do), journey graph (ordered steps and branches), and status graph (implemented / partial / missing / recently changed), derived mostly from layers A + C and optionally summarized with provenance. |
| **E — Retrieval-ready artifacts** | Embeddings over facts and selective chunk types, lexical indices, graph artifacts, memory artifacts, and other search-optimized structures. Hydration should prefer Layer A for authoritative source spans. |
| **F — Answer composition** | Query-type router → flow/status/capability packet assembly → deterministic scaffold where useful → LLM prose → verifier over spans, facts, and negative claims. |
| **G — SaaS governance** | Encryption, retention, reindex controls, tenant-aware cost, observability, and authority/degraded modes in the UI. |

---

## 6. Phased roadmap (execute in order)

Each phase has exit criteria so the team knows when the next phase can begin.

### Hotfix — evidence consistency (days)

**Goal:** memory and chat agree on which sources are eligible.

**Work:**

* change `_load_doctwin_chunks()` to include only chunks from `ready` sources unless a broader policy is explicitly documented,
* add unit tests for mixed `ready` / `processing` / `failed` twins,
* document the invariant.

**Exit:** tests are green and memory synthesis uses the same source eligibility policy as strict retrieval.

---

### Phase 0 — Foundations: truth, measurement, degraded modes (1–2 weeks)

**Goal:** be able to tell *why* an answer failed.

**Work:**

* formalize invariants around lineage, spans, hashes, namespace (`doctwin_id`, `source_id`, `snapshot_id`),
* extend source/index health telemetry,
* expand eval suites beyond auth,
* define `authority_level` and `degraded_reason` for UI and debugging,
* add per-answer or per-session debug views that attribute weakness to ingest, parsing, retrieval, or composition.

**Exit:** the team can diagnose failure sources rather than calling everything “retrieval quality.”

**Implemented (v1):**

* **Invariants:** `app/domains/evidence/invariants.py` documents `EVIDENCE_NAMESPACE_KEYS` and `STRICT_FILE_BACKED_CHUNK_KEYS`; `evidence.py` references it.
* **Twin rollup:** `GET /twins/{doctwin_id}/evidence-health` → `TwinEvidenceHealthResponse` via `build_doctwin_evidence_health_summary()` (`app/domains/evaluation/doctwin_evidence_health.py`).
* **Per-answer diagnosis:** `build_answer_authority_diagnosis()` logs `answer_authority_diagnosis` (structured); Langfuse trace metadata includes `authority_level` and `authority_degraded_reasons`. Optional API: `SendMessageRequest.include_answer_diagnostics` + `MessageResponse.answer_diagnostics`.
* **Richer source list for chat:** `_load_sources_for_twin` now includes `index_mode`, strict flags, parser / strict coverage ratios for the diagnosis ingest stage.
* **Test defaults:** `backend/tests/conftest.py` sets minimal env so unit tests can import the app without a preloaded shell `.env`.
* **Unit tests:** `tests/unit/test_phase0_*.py` cover authority levels and twin rollup. Golden suite already spans non-auth personas; filter or extend by `case_id` as needed.

---

### Phase 1 — Canonical source mirror (4–8+ weeks depending on storage/compliance)

**Goal:** retain the full repository text per revision, not only derived chunks.

**Deliverables:**

* `source_snapshots`
* `source_files`
* optional `source_file_spans` later, with v1 able to slice spans directly from stored file text

**Pipeline change:**

1. connector fetch
2. transactional write into Layer A
3. policy classification over canonical files
4. derived extraction/indexing/fact generation reading from Layer A

**Exit:** arbitrary line ranges can be hydrated from platform storage without re-fetching the source provider.

**Implemented (v1):**

* **Canonical tables:** `source_snapshots` and `source_files` via Alembic revision `0017`. Each mirrored file is namespaced by source, twin, snapshot, path, content hash, line count, language/file role, and policy state.
* **Domain service:** `app/domains/knowledge/source_mirror.py` writes full snapshots, carries unchanged files forward on delta syncs, deletes removed paths in the new snapshot, and exposes exact line-span hydration from stored text.
* **Pipeline write path:** `process_connector_result()` now writes policy-cleared source text into the canonical mirror before derived chunk/index rows are persisted. Source `index_health.canonical_mirror` records mirror readiness, mirrored file count, carried-forward count, changed count, and deleted count.
* **Retrieval hydration:** strict deterministic hydration now checks the source mirror first and only falls back to legacy provider/local-content hydration when a source has not been mirrored.
* **Evidence health UI/API signals:** twin evidence health now rolls up `canonical_mirror_ready_count` and `canonical_mirror_file_count`.
* **Compatibility:** legacy chunk hydration still works for sources not yet backfilled into Layer A.

**Phase 1 verification:**

```bash
cd backend
APP_SECRET_KEY=phase1-test-secret-key-minimum-32 \
DATABASE_URL=postgresql+asyncpg://doctwin_user:doctwin_pass@localhost:5434/doctwin_db \
JWT_SECRET_KEY=phase1-test-jwt-secret-key-minimum-32 \
EMBEDDING_DIMENSIONS=1024 \
uv run pytest tests/integration/test_phase1_source_mirror.py -v --tb=short
```

Pass criteria: the integration test proves full snapshot writes, delta carry-forward/delete behavior, exact line-span reads, ingestion-to-mirror writes, and retrieval hydration from the mirror.

---

### Phase 2 — Implementation facts + chunk compatibility (4–8 weeks, parallelizable after Phase 1)

**Goal:** create deterministic, queryable behavior edges.

**Work:**

* add an `implementation_facts` store,
* define fact taxonomy for routes, handlers, API calls, auth checks, service/repo/model edges, UI actions, and other flow steps,
* emit fact-backed chunk types so existing vector/lexical retrieval improves during migration,
* wire fact coverage into source health.

**Exit:** fixture repos can answer questions like “which route handles X?” and “what happens after this handler?” without relying on auth-specific heuristics.

**Implemented (v2):**

* **Fact store:** Alembic revision `0018` adds `implementation_facts` with tenant/source/snapshot namespace, `fact_key`, `fact_type`, subject/predicate/object, symbol/span anchors, summary, confidence, evidence hash, and metadata.
* **Fact taxonomy:** `app/models/implementation_fact.py` defines route, handler, auth check, API call, call, data model, dependency, UI action, service edge, and model edge fact types.
* **Deterministic emitters:** `app/domains/knowledge/implementation_facts.py` derives facts from the canonical mirror + implementation inspection. Python emits routes, handlers, auth checks, calls, service delegation, model/persistence edges, dependencies, and data-model facts. TS/JS emits API calls, route/session guard signals, UI event handlers, and navigation actions.
* **Chunk compatibility:** fact rows with spans also emit `implementation_fact` chunks so existing vector/lexical retrieval benefits before Phase 4 flow packets exist.
* **Hydration:** `app/domains/retrieval/hydration.py` hydrates `implementation_fact` chunks from `implementation_facts` by `fact_key`, not stale chunk text.
* **Retrieval compatibility:** implementation/onboarding/workspace retrieval modes boost `implementation_fact` and down-rank broad docs/memory where code-grounded facts are expected.
* **Health and lifecycle:** source `index_health.implementation_index` reports `facts_indexed` and `fact_schema_version` (incrementing as taxonomy grows; v4 after validation-constraint facts); no-op full sync refuses to short-circuit older fact schemas so existing sources are rebuilt when fact emitters change.
* **Evidence health:** twin evidence health includes `implementation_fact_count` so owners/debug tooling can see fact coverage.
* **Dev backfill:** existing Cynthia sources were rebuilt on the dev database. `scaffold_proj` now has 3,190 implementation facts and 2,579 fact chunks; `alex` has 2,830 facts and 2,291 fact chunks; all owned sources are `ready` with fact schema `2`.

**Phase 2 verification:**

```bash
cd backend
uv run pytest tests/unit/ -q --tb=short
uv run pytest tests/integration/test_phase1_source_mirror.py -v --tb=short
uv run pytest tests/integration/test_phase2_implementation_facts.py -v --tb=short
uv run pytest tests/integration/test_memory_load_doctwin_chunks_ready_filter.py -v --tb=short
APP_SECRET_KEY=phase2-test-secret-key-minimum-32 \
DATABASE_URL=postgresql+asyncpg://doctwin_user:doctwin_pass@localhost:5434/doctwin_db \
JWT_SECRET_KEY=phase2-test-jwt-secret-key-minimum-32 \
EMBEDDING_DIMENSIONS=1024 \
uv run alembic current
```

Pass criteria: unit tests are green; Phase 1 mirror and memory eligibility regressions remain green; Phase 2 integration proves fact rows, fact-backed chunks, source health, embeddings, and deterministic fact hydration; Alembic reports `0018 (head)`.

**Operational note:** after adding a new `ChunkType`, restart long-lived API/worker processes before running memory extraction. A stale worker can hold the old SQLAlchemy enum in memory and fail when it reads `implementation_fact` rows.

---

### Phase 3 — Language & framework extraction V2 (ongoing; prioritize Python + TS/JS)

**Goal:** reduce “unknown wiring” holes in modern backends and frontends.

**Work:**

* Python: AST route extraction, DI, pydantic validation boundaries, service/repo/model edges, job enqueue, external clients
* TS/JS: tree-sitter or equivalent for components, hooks, handlers, client calls, router configs, and frontend flow wiring
* expand framework roles beyond the current coarse categories

**Exit:** fact density crosses an agreed threshold on representative React + FastAPI-style repos and other priority architectures.

**Implemented (v3–v4 — tree-sitter + deterministic heuristics):**

* **Taxonomy:** Alembic `0019` adds `hook_binding`, `route_config`, `background_job`, and `injection_site`; Alembic `0020` adds `validation_constraint`. Emitters live in `app/domains/knowledge/implementation_facts.py`.
* **Python:** `Depends(...)` injection sites, `BackgroundTasks`, Celery `.delay(...)` / worker line hints, and **narrow Pydantic `Field(...)` facts** (only keywords that imply runtime validation: `ge`/`gt`/`le`/`lt`, lengths, `pattern`, collection bounds, `multiple_of`, `strict` when true, `frozen`) capped at **12 facts per class**.
* **TS/JS (tree-sitter):** `tree-sitter` + `tree-sitter-typescript` wheels (no local compile). `app/domains/knowledge/ts_tree_sitter.py` parses `.ts`/`.tsx`/`.js`/`.jsx`; `implementation_index` uses the AST for imports, export-aware symbols (with real line spans), and optional program-level declarations, with **regex fallback** if the parse root is unhealthy. `implementation_facts` walks `call_expression` nodes for `fetch`, `axios.*`, generic `*.get/post/...` client calls, and React/TanStack-style hooks.
* **TS/JS (regex layer):** Next App Router path inference, TanStack `createFileRoute`, React Router object/path wiring, BullMQ-style queue hints, and `@/services/` import service edges remain as complementary line/heuristic signals.
* **Framework roles:** `implementation_index` adds hints such as `next_app_router`, `next_pages_router`, `react_router`, `react_hooks_module`, and `edge_middleware` where path patterns match. File metadata includes `ts_tree_sitter` / `ts_tree_sitter_symbols` when the tree path was used.
* **Lifecycle:** `index_health.implementation_index.fact_schema_version` is **`4`** after `0020`; strict no-op full sync requires it so sources pick up validation emitters after migration.

**Phase 3 verification (local DB):**

```bash
cd backend
APP_SECRET_KEY=... JWT_SECRET_KEY=... DATABASE_URL=... EMBEDDING_DIMENSIONS=1024 uv run alembic upgrade head
uv run pytest tests/unit/ -q --tb=short
uv run pytest tests/integration/test_phase2_implementation_facts.py -v --tb=short
```

**Optional live user check (deployed API; credentials via env only):**

```bash
cd backend
LIVE_DEV_API_BASE=https://your-api-host LIVE_DEV_EMAIL=... LIVE_DEV_PASSWORD=... \\
  uv run pytest tests/integration/test_phase3_live_dev_api.py -v --tb=short
```

---

### Phase 4 — Retrieval V2: flow packets + query-type routing (4–6 weeks)

**Status:** **v1 shipped** (fact layer, labels, packet fields, diversity, golden assertions). Remaining backlog: richer flow/capability packets beyond histograms, stronger auth/engine shortcut demotion behind metrics, formal golden exit tracking.

**Goal:** stop shipping only bags of chunks for implementation and flow questions.

**Work:**

* add fact search as a first-class retrieval layer,
* build flow/status/capability packets,
* add multi-label query decomposition,
* broaden recall with diversity for broad questions,
* progressively demote auth/engine-specific shortcut logic to fallback status once generic fact/flow retrieval proves itself.

**Exit:** flow-style golden prompts improve without increasing unsupported claims or hallucination.

**Implemented (v1 slice — fact layer + packet + diversity):**

* **Fact search:** `search_implementation_facts_for_twin` (`fact_retrieval.py`) joins `ImplementationFact` to ready `Source` rows and ILIKE-matches planner terms (from `search_terms_from_query`).
* **Planner:** `query_labels` via `decompose_query_labels`, per-mode `fact_budget`, `searched_layers` includes `facts` when the budget is non-zero; `fact_hits` is set after the SQL pass.
* **Evidence packet:** `facts`, `query_labels`, `flow_outline` (type histogram); `layer_hits["facts"]` when rows exist.
* **Router:** runs the fact pass before scoring; **diversity** `_demote_surplus_same_source` for `RetrievalMode.general` when `len(query_labels) >= 4`; **progressive demotion** trims auth chunk boosts slightly when `fact_hits >= 8` in implementation-like modes.
* **Answering:** `<evidence_index>` lists `query_labels`, `flow_outline`, and a compact `facts` line; `<knowledge>` prepends an **Implementation facts** section (workspace per-project blocks too).
* **Golden harness:** `repo_intelligence_suite.json` can require `query_labels` / `flow_outline` / `facts` substrings parsed from the rendered `<evidence_index>` (twin + per-project workspace). `golden_harness` seeds a few `ImplementationFact` rows so those assertions hit real SQL. Fact SQL budgets live in `planner._FACT_BUDGET_BY_MODE`; same-source diversity uses `router._SURPLUS_SAME_SOURCE_DEMOTION_FACTOR`.

---

### Phase 5 — Memory & graph V2 (3–6 weeks)

**Status:** **v0.2 shipped in repo** — facts-first deterministic graph, topic artifact digest, memory brief wiring, CI exit signals.

**Goal:** make memory a compression of facts and canonical inventory rather than thin module summaries.

**Work:**

* rebuild graph deterministically from facts first,
* use capability/journey/status signals as memory inputs,
* generate topic artifacts with provenance: auth/session, API surface, onboarding path, permissions, jobs, integrations, and other stable views,
* keep LLM graph/memory generation as enrichment rather than primary structure.

**Exit:** memory brief disagreement with strict retrieval drops, and brief quality rises with fact coverage rather than prompt tweaking alone.

**CI exit test (measurable proxy):** `evaluate_phase5_memory_brief_exit_signals` in `app/domains/evaluation/phase5_exit.py` — when implementation facts exist for the twin, the brief pipeline must produce both the implementation digest header and the topic-views header (fed via `run_memory_extraction` → `generate_memory_brief`). Unit coverage: `tests/unit/test_phase5_exit.py`. Stats: `stats["phase5_exit"]` on extraction completion.

**Implemented:**

* **Facts-first graph:** `build_deterministic_graph` loads ready `ImplementationFact` rows (`knowledge/implementation_facts_access.py`) and merges file/subject (and optional `object_ref` call) edges before indexed file/symbol/relationship rows (`graph/deterministic.py`).
* **Memory brief context:** one ordered fact load in `run_memory_extraction` → `format_implementation_fact_digest_markdown` + `build_topic_artifact_digest` (`memory/fact_digest.py`, `memory/topic_artifacts.py`) passed into `generate_memory_brief` (`memory/extractor.py`). `load_implementation_fact_digest_for_memory` remains for callers that only need the flat digest string.
* **Stats/logs:** `fact_digest_chars`, `topic_digest_chars`, `implementation_fact_rows`, `phase5_exit` (and `phase5_exit_pass` in completion log).
* **Indexed graph:** deterministic merge from indexed files/symbols/relationships still runs on the same structures after fact integration.

---

### Phase 6 — Answering V2 (2–4 weeks)

**Status:** **v0.2 shipped in repo** — scaffold + richer flow outline + fact/flow contradiction checks + gap/bounds messaging + observability signals. Formal product exit still uses human side-by-side evals.

**Goal:** produce engineer-grade narrative with the same safety bar.

**Work:**

* generate a deterministic scaffold from the question packet,
* let the model turn that scaffold into polished prose,
* extend the verifier to check fact and flow consistency,
* improve bounded-uncertainty phrasing when the chain ends or a feature is missing.

**Exit:** side-by-side evals prefer the new answerer while preserving the “do not invent code” standard.

**CI / observability (proxy for exit):**

* `evaluate_phase6_retrieval_packet_signals` / `evaluate_phase6_verification_exit_signals` in `app/domains/evaluation/phase6_exit.py`; retrieval `phase6` block on `build_answer_authority_diagnosis`; after single-twin verification, `stage_signals["verification"]["phase6_verification"]` on the same diagnosis. Tests: `tests/unit/test_phase6_exit.py`.

**Implemented:**

* **Scaffold:** `app/domains/answering/scaffold.py` — `build_answer_scaffold`, `build_workspace_answer_scaffold`; wired in `generator.py` after the answer contract (single-twin and workspace system prompts). Contract rules in `contracts.py` (scaffold, `missing_evidence`, `flow_outline` structural segment).
* **Richer flow outline:** `build_flow_outline(facts, graph_edges=...)` in `fact_retrieval.py` appends `|| structural: …` (graph edges + path-grouped fact anchors); `build_evidence_packet` passes `graph_edges`. Preserves histogram prefix so existing golden substring checks (e.g. `auth_check`) still match.
* **Verifier — fact/flow vs negatives:** `_line_denies_present_fact_types` + `_FACT_TYPE_DENIAL_PHRASES` inside `_has_contradicted_absence_claim` (single-project and workspace section paths). **Bounded gaps:** `_append_negative_bounds` appends `## Grounded gaps (from retrieval)` from `packet.missing_evidence`.
* **Prompt — gaps:** hard rules in `generator.py` for surfacing `missing_evidence` with bounded phrasing.
* **Verifier (v0.1 carryover):** `packet.facts` paths, subjects, and file-like `object_ref` merge into `_build_allowed_refs`; `_packet_text` / ref-allowlisting include fact fields.
* **Tests:** `test_answer_scaffold.py`, `test_answer_generator.py`, `test_answer_verifier.py`, `test_retrieval_packets.py` (structural flow), `test_phase6_exit.py`, `test_phase0_answer_authority.py` (implicit `stage_signals.retrieval.phase6`).

---

### Phase 7 — SaaS hardening (continuous)

**Status:** **in progress (v0.1)** — superuser admin stats + twin maintenance APIs + shared ARQ enqueue helpers; structured `admin_*` audit logs. Remaining: mirror/facts/graph rebuild endpoints, cost controls, encryption/audit persistence, shadow evals.

**Goal:** make the system operable and safe at product scale.

**Work:**

* admin operations: re-sync, rebuild mirror, rebuild facts/graph/memory, compare snapshots
* cost controls: incremental parse, selective embed, compression, dedupe by content hash
* security: encryption at rest for Layer A, audit logs for span access, retention/deletion guarantees
* shadow evals in production for risky changes

**Exit:** the architecture is stable enough for real tenant use and continuous iteration.

**Implemented (v0.1):**

* **`GET /api/v1/admin/stats`** — counts for users, workspaces, twins, sources (totals + by `SourceStatus`). `app/domains/ops/platform_stats.py`.
* **`GET /api/v1/admin/ingestion-logs`** — empty placeholder payload with note (no job table yet).
* **`POST /api/v1/admin/twins/{doctwin_id}/memory/rebuild`** — enqueue memory extraction for any existing twin (superuser; bypasses workspace ownership). Uses `app/domains/ops/doctwin_memory_queue.py`.
* **`POST /api/v1/admin/twins/{doctwin_id}/sources/resync`** — set all twin sources `pending`, clear `last_error`, enqueue `ingest_source` per id. `app/domains/ops/doctwin_source_resync.py` + `arq_enqueue.py`.
* **Refactor:** owner `POST /twins/{id}/memory/generate` and source creation/sync enqueue paths call shared `enqueue_ingest_source_job` / `enqueue_memory_brief_for_twin` (`app/api/v1/twins.py`, `app/api/v1/sources.py`).
* **Audit:** `logger.info` with `admin_platform_stats`, `admin_doctwin_memory_rebuild`, `admin_doctwin_sources_resync`, `admin_ingestion_logs_view` (operator id + twin ids).
* **Tests:** `tests/unit/test_platform_stats.py`, `tests/unit/test_doctwin_source_resync.py`.

---

## 7. Sprint mapping (Cursor-friendly)

Use vertical slices. Every sprint should include tests.

| Sprint | Focus | Key outputs |
| --- | --- | --- |
| **S0** | Hotfix + Phase 0 starter | `_load_doctwin_chunks` filter, health-metric stubs, eval cases for journeys and status |
| **S1** | Phase 1 slice 1 | `source_snapshots` + `source_files`, mirror write path, hydration read API |
| **S2** | Phase 1 slice 2 | extractors reading from mirror while legacy chunk path still works |
| **S3** | Phase 2 slice 1 | `implementation_facts`, migrations, one language family (Python) fact emitters |
| **S4** | Phase 2 slice 2 | fact-backed chunks, retrieval joins, fact coverage metrics |
| **S5** | Phase 3 | TS/JS parser-based fact emitters, framework role expansion |
| **S6** | Phase 4 | flow packet builder, query-type router, eval expansion |
| **S7** | Phase 5–6 | memory/graph V2 plus answering V2 |
| **S8+** | Phase 7 | product hardening, shadow mode, cost dashboards |

---

## 8. Explicit non-goals (do not do first)

Do **not** start by:

* rewriting prompts to sound smarter without new evidence,
* raising `top_k` globally without structure and diversity,
* adding more domain-specific SQL shortcuts before generic fact/flow retrieval exists,
* loosening the verifier to reduce fallbacks,
* storing secrets in cleartext or embedding flagged secret content.

---

## 9. What “0 → 100” actually requires

You are building an internal compiler and query engine over repositories: canonical bytes, deterministic facts, capability/journey/status graphs, flow-shaped retrieval, and disciplined answer composition. The chat model is the speaker; the substrate must carry engineer-grade truth. When that substrate exists, the strict verifier becomes a strength because it proves depth and boundaries, rather than merely surfacing absence.

---

## 10. Optional inputs to tailor execution

If you want this plan mapped file-by-file to the repo in Cursor tasks, prioritize sharing or linking:

* `Chunk`, `Source`, `TwinConfig`, and implementation index models
* `process_connector_result` and connector interfaces
* `retrieve_packet_for_twin`, `build_evidence_packet`, and hydration logic
* memory extraction entrypoints
* current golden JSON suites

The codebase already contains strong hooks for several later phases. The largest net-new work is the **canonical source mirror**, the **implementation facts layer**, and the **flow/status/capability packet model**.
