# docbase — Architecture

For the canonical repo intelligence implementation roadmap, see
`docs/repo-intelligence-roadmap.md`.

## What This Is

A multi-tenant SaaS platform that lets users create interactive AI twins for any knowledge source: Drive folders, PDFs, resumes, portfolios, projects, or documents. Each twin is a safe, conversational interface grounded in approved knowledge — no raw code leakage, no secrets exposure.

---

## Core Domain Model

```
User
 └── Workspace (one per user initially, multi-workspace later)
      ├── Twin (many per workspace)
      │    ├── Source (one or many attached sources)
      │    ├── TwinConfig (visibility, policy, branding)
      │    └── PublicShareSurface (optional public link / embed)
      └── WorkspaceShareSurface (optional general public link)

ChatSession
 └── belongs to either a Twin or a Workspace
      ├── Messages
      └── RoutingDecision (which twin/source answered)
```

**Key modeling rule:** Sources attach to twins. Each `Source` (e.g. `google_drive`, `pdf`) is indexed into the twin the user chose. The `Twin` is the primary product abstraction.

---

## Domains and Responsibilities

### 1. Users & Auth
Handles registration, login, JWT issuance, API key management. Owns the `User` model.

### 2. Workspaces
A workspace is a user's container for twins. Handles workspace creation, settings, member access (future), and workspace-level public share surfaces.

### 3. Twins
The core product domain. A twin is a named, configurable AI agent grounded in one or more sources. Handles:
- Twin CRUD
- Source attachment
- Twin config (policy overrides, branding, visibility)
- Twin-level public share surfaces
- Twin routing metadata

### 4. Sources
Each source is a data origin attached to a twin. Sources are typed:
- `google_drive`
- `pdf`
- `markdown`
- `url`
- `manual`

The source domain owns the connection config and raw ingestion trigger. It does NOT own processing — that belongs to Knowledge Processing.

Operationally, a source is only considered **ready** when:
- its file-derived chunks are fully embedded with no null vectors
- the twin-level Memory Brief has been rebuilt successfully after the sync

Between chunk indexing and memory completion, sources remain in an intermediate
`processing` state and are excluded from normal retrieval.

### 5. Connectors
One connector per source type. Connectors are responsible for:
- Authenticating with the external system
- Fetching raw content
- Returning a normalized raw content stream to the ingestion pipeline

Connectors never store data — they fetch and hand off.

### 6. Knowledge Processing
Receives raw content from connectors. Responsible for:
- Content normalization (chunking, cleaning)
- Safe metadata extraction (structure, summaries, architecture signals)
- Feature/module description derivation
- Dependency and tooling signals
- NO raw code storage unless policy explicitly permits snippet indexing

Embedding is profile-aware. Each persisted vector set carries the provider/model
profile used to create it so retrieval can query matching vector spaces only.
Full syncs may fail over from the primary embedder to a configured backup
provider on rate limits; delta syncs keep the existing source profile sticky to
avoid mixing incompatible vector spaces inside a partially updated source.

### 7. Policy / Safety
Owns the rules for what can and cannot be surfaced. Applied at:
- Ingestion time (what gets indexed)
- Retrieval time (what chunks are eligible to return)
- Answer time (what the response can include)

Policy levels:
- **Always blocked:** `.env`, secrets, credentials, API keys, private keys
- **Off by default, user-enabled:** code snippets (scoped, never full files)
- **Always available:** structure, architecture, docs, summaries, dependencies

### 8. Retrieval / Routing
Given a user query, determines:
- Which twin is most relevant (workspace-level chat)
- Which evidence layers are relevant (vector, lexical, path, symbol, graph)
- Which source chunks are most relevant (twin-level chat)
- Returns structured evidence packets for answer generation

Phase 2 retrieval is now hybrid:
- deterministic query planning selects a retrieval mode and evidence budgets
- PostgreSQL full-text search is the lexical substrate for chunks, indexed files, and indexed symbols
- vector, lexical, path, symbol, and graph candidates are fused before reranking
- canonical hydration refreshes the winning spans from strict source snapshots
- workspace retrieval stays namespace-safe and respects each twin's snippet policy

### 9. Answering
Receives policy-filtered context + user query. Generates a grounded response using an LLM. Never allowed to speculate beyond approved context. Cites source when helpful.

Phase 3 answering is now evidence-bound:
- answer generation receives the retrieval packet mode and evidence index, not only loose chunks
- prompts include explicit answer contracts for implementation, onboarding, recruiter, status, and workspace modes
- a cheap verifier checks explicit file and symbol references against the packet namespace
- absence claims are rewritten or bounded to the searched layers when needed
- workspace answers must keep one project per labeled section; cross-project leakage falls back to a grounded rewrite
- the verifier can request at most one regeneration pass before rewriting deterministically

### 9a. Memory
The engineering memory layer is now evidence-backed:
- twin memory extraction loads deterministic evidence from indexed files, symbols, and relationships
- memory artifacts now include feature summaries, auth flow summaries, onboarding maps, risk summaries, and change summaries
- memory-derived chunks carry provenance metadata back to files and symbols
- workspace synthesis is stored as a first-class workspace memory artifact instead of being smuggled into a twin
- `memory_brief` remains the owner-visible long-form summary, but it is now assembled from the evidence-backed artifact set

### 9b. Trust, Evaluation, And SLOs
Phase 5 makes repo intelligence measurable and owner-visible:
- source responses now expose dynamic freshness state, stale warnings, strict-vs-legacy trust mode, and parser coverage derived from the deterministic implementation index
- chat runtime logs deterministic quality metrics such as grounded anchor presence, citation count, verifier catches, bounded-negative handling, and workspace label completeness
- chat runtime also logs latency reports against explicit retrieval, generation, verification, and total-turn budgets
- the asynchronous LLM evaluator now scores usefulness in addition to the earlier grounding/depth dimensions
- a golden evaluation suite exists for engineer, recruiter, PM, and workspace-comparison scenarios so question-mode coverage is explicit instead of implicit

### 10. Sharing
Manages public share surfaces:
- Per-twin public pages (`/t/{slug}`)
- Per-workspace public pages (`/w/{slug}`)
- Embed tokens and widget config

### 11. Embedding
Handles the embeddable widget surface. Generates embed codes. Provides a minimal JS widget that communicates with the chat API.

### 12. Admin
Owner dashboard. Twin management, source status, ingestion logs, usage stats.

### 13. Jobs
Background job system (Celery or ARQ). Handles:
- Source ingestion on attach or update
- Re-ingestion on config change
- Scheduled re-sync for live sources (Google Drive watch channels, URLs)
- Notification hooks

---

## Data Flow

```
User attaches Source to Twin
        │
        ▼
Connector fetches raw content
        │
        ▼
Ingestion pipeline receives raw stream
        │
        ▼
Policy/safety filters what can be indexed
        │
        ▼
Knowledge processing normalizes, chunks, extracts metadata
        │
        ▼
Vector index + structured metadata stored
        │
        ▼
User sends message to Twin (or Workspace)
        │
        ▼
Retrieval/routing identifies relevant twin + source chunks
        │
        ▼
Policy/safety and evidence hydration filter what chunks can be returned
        │
        ▼
Answering generates grounded response
        │
        ▼
Response returned to user via chat interface or embed widget
```

---

## Privacy Model

Three-tier content policy, enforced at ingestion and retrieval:

| Tier | Content | Default | Configurable |
|------|---------|---------|--------------|
| Always blocked | `.env`, secrets, keys, credentials | Blocked | Never |
| Opt-in | Code snippets (scoped sections, not full files) | Off | User can enable per twin |
| Always available | Structure, docs, summaries, architecture, dependencies | On | Cannot disable |

The config lives in a `.twinconfig` file at the repo root (for repo sources) or in the platform UI for other source types.

---

## Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend | Python + FastAPI | Async-friendly, strong typing with Pydantic, fast iteration |
| Frontend | React + TypeScript | Component ecosystem, type safety, wide hiring pool |
| Primary DB | PostgreSQL | Relational integrity for users/workspaces/twins/sources |
| Vector DB | pgvector (initially) | Keeps infra simple at early stage; swap to Qdrant/Pinecone at scale |
| Cache / Sessions | Redis | Fast session lookup, rate limiting, job queue backend |
| Job Queue | ARQ (async Redis queue) | Lightweight, Python-native, sufficient for v1 |
| LLM | OpenAI (abstracted) | Start with OpenAI, abstraction layer allows swap |
| Auth | JWT + httpOnly cookies | Secure defaults |
| Local Dev | Docker Compose | Single command local stack |

---

## API Design

- All API routes versioned under `/api/v1/`
- RESTful resource structure
- Async everywhere in the backend
- Public share pages served as SSR or static from frontend with API calls
- Embed widget served as a small standalone JS bundle

---

## Security Principles

- No raw source content stored in API-accessible tables
- Policy enforcement is a separate, auditable layer — not mixed into business logic
- Secret scanning runs at ingestion time before any content is indexed
- All public share surfaces are read-only
- Embed tokens are scoped and revocable
- API keys hashed at rest
