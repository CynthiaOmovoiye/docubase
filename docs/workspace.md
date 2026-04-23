# Workspace Structure

This document explains the layout of this monorepo and the purpose of every major directory.

---

## Top-Level Layout

```
docubase/
├── backend/               Python + FastAPI backend
├── frontend/              React + TypeScript frontend
├── infra/                 Docker, migrations, infrastructure scripts
├── docs/                  Architecture, ADRs, diagrams
├── scripts/               Dev and ops scripts
├── .env.example           Template for environment variables
├── docker-compose.yml     Local development stack
├── Makefile               Task runner for common commands
└── README.md              Project entry point
```

---

## Backend

```
backend/
├── app/
│   ├── api/
│   │   └── v1/            All API routes, versioned
│   │       ├── twins.py
│   │       ├── sources.py
│   │       ├── workspaces.py
│   │       ├── users.py
│   │       ├── chat.py
│   │       ├── sharing.py
│   │       └── admin.py
│   │
│   ├── domains/           Core business logic, one folder per domain
│   │   ├── twins/         Twin creation, config, management
│   │   ├── sources/       Source lifecycle, attach/detach, status
│   │   ├── workspaces/    Workspace management
│   │   ├── users/         User model, profile
│   │   ├── knowledge/     Processing pipeline, chunking, metadata extraction
│   │   ├── policy/        Safety rules, redaction, content filters
│   │   ├── retrieval/     Semantic search, twin routing
│   │   ├── answering/     LLM call, grounded response generation
│   │   ├── sharing/       Public share surfaces, slugs, tokens
│   │   ├── embedding/     Embed tokens, widget config
│   │   └── admin/         Admin views, usage, logs
│   │
│   ├── connectors/        One connector per source type
│   │   ├── github/
│   │   ├── gitlab/
│   │   ├── pdf/
│   │   ├── markdown/
│   │   ├── url/
│   │   └── manual/
│   │
│   ├── core/              Shared infrastructure (not business logic)
│   │   ├── config.py      Settings via pydantic-settings
│   │   ├── db.py          Database session
│   │   ├── redis.py       Redis client
│   │   ├── security.py    JWT, hashing
│   │   ├── logging.py     Structured logging setup
│   │   └── exceptions.py  Base exception classes
│   │
│   ├── jobs/              Background jobs (ARQ workers)
│   │   ├── ingestion.py
│   │   └── sync.py
│   │
│   ├── models/            SQLAlchemy ORM models
│   └── schemas/           Pydantic request/response schemas
│
├── tests/
│   ├── unit/              Unit tests per domain
│   ├── integration/       Integration tests (DB, connectors)
│   └── fixtures/          Shared test data and factories
│
├── pyproject.toml
└── Dockerfile
```

### Domain boundary rule

Each domain in `app/domains/` owns its own:
- Service layer (business logic)
- Repository layer (data access)
- Domain-specific exceptions

Domains may call each other's service layer. They must NOT reach directly into another domain's repository. Cross-domain data flows through service interfaces.

---

## Frontend

```
frontend/
├── src/
│   ├── app/               Root app, routing, providers
│   ├── features/          One folder per product feature
│   │   ├── auth/
│   │   ├── workspaces/
│   │   ├── twins/
│   │   ├── sources/
│   │   ├── chat/          Chat UI (single twin + workspace-wide)
│   │   ├── sharing/       Public twin and workspace pages
│   │   ├── embed/         Embeddable widget entry
│   │   └── admin/
│   ├── components/
│   │   ├── ui/            Primitive UI components (Button, Input, Modal, etc.)
│   │   └── layout/        Page shells, nav, sidebars
│   ├── lib/               Shared utilities: API client, auth helpers, formatters
│   ├── types/             Global TypeScript types and interfaces
│   └── public/            Static assets
│
├── package.json
├── tsconfig.json
├── vite.config.ts
└── Dockerfile
```

### Feature folder rule

Each feature in `src/features/` contains:
- `components/` — UI specific to that feature
- `hooks/` — data fetching and state hooks
- `api.ts` — API call definitions for that feature
- `types.ts` — local TypeScript types
- `index.ts` — public exports

No feature imports from another feature's internal components. Cross-feature data flows through shared `lib/` or global state.

---

## Connectors

Each connector in `backend/app/connectors/` follows this structure:

```
connectors/github/
├── __init__.py
├── connector.py       Implements BaseConnector interface
├── auth.py            OAuth / token handling for this source type
├── fetcher.py         Raw content fetch logic
└── README.md          What this connector does, auth requirements
```

All connectors implement `BaseConnector` from `app/connectors/base.py`. This ensures the ingestion pipeline can treat all source types uniformly.

---

## Infra

```
infra/
├── docker/
│   ├── backend.Dockerfile
│   └── frontend.Dockerfile
├── migrations/            Alembic migration files
└── scripts/               DB init, seed data, deployment helpers
```

---

## Docs

```
docs/
├── architecture.md        Full architecture overview
├── workspace.md           This file — workspace layout guide
├── adr/                   Architecture Decision Records
│   └── 001-stack-selection.md
└── diagrams/              Mermaid or draw.io source files
```

ADRs follow this format: `NNN-short-title.md`. Each records context, decision, and consequences. New architectural decisions that affect product direction should have an ADR.

---

## Scripts

```
scripts/
├── setup.sh               First-time local setup
├── seed.py                Seed dev database with test data
└── check-secrets.sh       Scan for accidental secret exposure
```

---

## Environment and Secrets

- `.env.example` committed to repo — all keys present, no real values
- `.env` never committed — gitignored
- All config loaded via `app/core/config.py` using pydantic-settings
- Secrets managed per-environment (local = .env, production = secret manager)
