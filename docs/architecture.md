# docbase — Architecture

High-level domain model and data flow. For a **reviewer-oriented** summary (problem, evaluation, deployment), see [`README.md`](../README.md). Directory layout: [`workspace.md`](workspace.md).

---

## What This Is

A multi-tenant platform for **AI twins**: each twin owns **sources** (Google Drive, PDFs, URLs, markdown, manual notes). Indexed knowledge is retrieved with **intent hints**, answers are **evidence-verified**, and an optional **active quality gate** (Pydantic-validated LLM judge + bounded regeneration) runs **before** assistant messages are persisted. Public **share surfaces** expose read-only chat — no owner credentials or raw source browsing.

---

## Core Domain Model

```
User
 └── Workspace
      ├── Twin (many per workspace)
      │    ├── Source (typed attachment; indexed into this twin)
      │    ├── TwinConfig (display name, persona, policy, memory brief, branding)
      │    └── ShareSurface (optional public twin link / embed)
      └── ShareSurface (optional workspace-wide public chat link)

ChatSession
 └── anchored to Workspace; optional doctwin_id (null = workspace-level routing)
      └── Message (user + assistant; chunk ids on assistant for audit)
```

**Key rule:** Sources attach to **twins**. The twin is the primary product abstraction — not a repo root or vendor folder.

---

## Domains and Responsibilities

### 1. Users & Auth
Registration, login, JWT, API keys. Owns `User`.

### 2. Workspaces
Container for twins; ownership and future multi-member boundaries. Workspace-level **share surfaces** for routed / aggregate public chat.

### 3. Twins
Named, configurable agents: CRUD, source attachment, `TwinConfig` (policy, `custom_context`, **Memory Brief** when ready), twin-scoped share links, routing metadata for workspace chat.

### 4. Sources
Typed origins: `google_drive`, `pdf`, `markdown`, `url`, `manual`. Owns connection config and sync triggers; **does not** own chunking/embeddings (Knowledge Processing).

**Ready** when file-derived chunks are embedded and indexing rules satisfied; intermediate `processing` excludes normal retrieval. **Memory Brief** generation is a separate job after ingest (see Memory).

### 5. Connectors
One integration per source type: auth, fetch bytes/text, return normalized stream to ingestion. **No persistence** inside connectors.

### 6. Knowledge Processing
Normalize, chunk, extract metadata, embeddings. **Profile-aware vectors** (provider/model) so retrieval only queries compatible spaces; failover and sticky profiles on partial syncs. No raw code storage unless policy allows snippet indexing.

### 7. Policy / Safety
Three tiers (always blocked secrets; opt-in code snippets; always-on structure/docs). Applied at **ingest**, **retrieve**, and **pre-LLM** answer assembly.

### 8. Retrieval / Routing
Hybrid retrieval: deterministic planning + pgvector + PostgreSQL full-text + path/symbol/graph signals where configured; hydration from source snapshots. **Workspace** paths: aggregate across twins with namespace safety, or route to one twin by query; **twin** paths: single evidence packet.

### 9. Answering
`generate_answer` / `generate_workspace_answer` in `domains/answering/generator.py`: owner notes, Memory Brief block, retrieved chunks, conversation history; sanitised injection; regeneration hints on verifier retry.

**Verifier** (`domains/answering/verifier.py`): grounded file/symbol references, workspace section discipline, bounded-negative phrasing. **Conversational workspace turns** (greetings, identity questions, etc.) skip strict per-project `##` headers so natural prose is not replaced by internal evidence templates.

### 9a. Memory
Engineering memory: evidence-backed extraction, memory-derived chunk types, provenance to files/symbols. **`memory_brief`** on `TwinConfig` — system-authored long summary injected into the answer prompt (not `custom_context`). Workspace synthesis as a first-class workspace artifact where implemented.

### 9b. Evaluation & quality gates
| Mechanism | When | Role |
|-----------|------|------|
| **Evidence verifier** | Every non-deterministic LLM path | Namespace-safe answers; workspace rewrite on violation |
| **Active quality gate** | `chat_quality_gate_enabled` (default on in `config`) | Sync judge → JSON → **`ResponseQualityGate`** (Pydantic) → if reject, bounded `generate_*` + re-verify **before persist**; workspace aggregate runs inside `_answer_across_workspace` |
| **Passive LLM judge** | Gate **disabled** | Async `evaluate_response_async` — dimensional scores + Langfuse |
| **Structured logs** | Always | Latency budgets, authority diagnosis, gate accept/reject, retrieval mode |

Configurable: `CHAT_QUALITY_GATE_*` in `.env` (see `.env.example`).

### 10. Sharing
Active share surfaces: per-twin (`/t/:slug`), per-workspace (`/w/:slug`), embed tokens. Revocation, rate limits on public chat APIs.

### 11. Embedding (product surface)
Embeddable widget + minimal JS; talks to versioned chat API.

### 12. Admin / owner UI
Dashboard: twins, sources, ingestion status, share links, workspace chat (authenticated).

### 13. Jobs
**ARQ** (async Redis queue): ingest on attach/update, re-sync (Drive, URLs), **memory brief** jobs, notifications. Idempotent workers.

---

## Chat request flow (conceptual)

```
User message
     │
     ▼
Langfuse trace (optional)
     │
     ▼
Intent / query analysis
     │
     ▼
Retrieve ──► twin packet | workspace aggregate | routed twin
     │
     ▼
Generate (twin or workspace prompt)
     │
     ▼
Verify (single-project or workspace verifier)
     │
     ▼
[Optional] Verifier-requested regeneration + verify again
     │
     ▼
Active quality gate? ──yes──► Judge (Pydantic JSON) → reject? → regen + verify (bounded)
     │              └──no──► (passive judge may run async after persist)
     ▼
Persist Message + chunk ids
     │
     ▼
Response to client
```

Deterministic fallbacks (no chunks, template workspace meta replies, etc.) **skip** the gate and passive judge where configured.

---

## Data flow (ingestion)

```
User attaches Source to Twin
        │
        ▼
Connector fetches raw content
        │
        ▼
Ingestion pipeline
        │
        ▼
Policy filters what may be indexed
        │
        ▼
Knowledge processing → chunks + embeddings
        │
        ▼
PostgreSQL + pgvector (+ lexical indexes as configured)
        │
        ▼
(Async) Memory extraction / Memory Brief job
```

---

## Privacy model

| Tier | Default | Configurable |
|------|---------|--------------|
| Always blocked | `.env`, secrets, keys, credentials | Never |
| Opt-in | Code snippets (scoped, never full files) | Per twin |
| Always available | Structure, docs, summaries, architecture | On |

Policy is enforced in the **platform** (twin config + policy engine), not via a single repo-local `.twinconfig` file for all source types.

---

## Technology stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| Frontend | React 18, TypeScript, Vite |
| DB | PostgreSQL + pgvector |
| Cache / queue | Redis + **ARQ** |
| LLM | OpenAI-compatible client (OpenRouter / OpenAI via `llm_provider`) |
| Auth | JWT + httpOnly cookies |
| Local | Docker Compose |

---

## API design

- Versioned under `/api/v1/`
- Async SQLAlchemy throughout
- Public share routes: anonymous chat only; ownership checks on owner APIs

---

## Security principles

- Chunks are derived, policy-filtered views — not raw file APIs
- Policy domain testable and not buried in unrelated modules
- Secret scanning at ingest
- Share surfaces read-only; embed tokens revocable
- Multi-tenant isolation on every query and retrieval scope
