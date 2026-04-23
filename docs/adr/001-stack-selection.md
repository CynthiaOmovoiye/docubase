# ADR 001 — Stack Selection

**Date:** 2026-04-15
**Status:** Accepted

---

## Context

We are building a multi-tenant SaaS platform for AI-powered digital twins. The platform needs to support:
- Multi-user workspaces with isolated data
- Background ingestion pipelines for various source types
- Semantic search and LLM-based answer generation
- Public share pages and embeddable widgets
- Clean domain separation between ingestion, retrieval, and generation

The team is early-stage. We need fast iteration speed without sacrificing production integrity.

---

## Decision

**Backend: Python + FastAPI**

Python is the natural home for LLM integrations, vector search, and ML tooling. FastAPI gives us async support, automatic OpenAPI docs, and strong Pydantic typing for schema validation. The alternative was Node/TypeScript for backend uniformity, but the ML ecosystem advantage of Python outweighs the convenience of a single language stack.

**Frontend: React + TypeScript**

React has the widest component ecosystem and developer pool. TypeScript is non-negotiable for a product with complex domain models — it catches contract mismatches early. Vite is used as the build tool for fast local development.

**Primary Database: PostgreSQL**

The domain model has relational integrity requirements: users belong to workspaces, twins belong to workspaces, sources attach to twins. A relational model is the right fit. PostgreSQL also supports `pgvector` for vector embeddings, allowing us to defer a separate vector database at early stage.

**Vector Storage: pgvector (initially)**

At early stage, running a separate vector database (Qdrant, Pinecone, Weaviate) adds operational overhead without meaningful benefit. pgvector keeps the stack simple. The retrieval domain is abstracted behind a clean interface, so migrating to a dedicated vector store later requires only a swap in one module.

**Cache and Job Queue Backend: Redis**

Redis serves dual purpose: session/cache store and job queue backend (via ARQ). This avoids introducing a separate message broker at early stage. If job volume grows, the ARQ/Redis combination can be replaced with Celery + RabbitMQ or a cloud queue without touching business logic.

**Job Queue: ARQ**

ARQ is a lightweight async Python job queue built on Redis. It is simpler than Celery and async-native, which fits our FastAPI stack. Adequate for ingestion workloads at early stage.

**LLM: OpenAI API (abstracted)**

We start with OpenAI because it has the most capable models and widest adoption. The answering domain wraps all LLM calls behind an `LLMProvider` interface, making provider swaps or multi-provider routing possible later without touching the rest of the product.

**Local Development: Docker Compose**

A single `docker-compose.yml` brings up Postgres, Redis, the backend, and the frontend. No manual database setup. No environment drift between developers.

---

## Consequences

- The backend and frontend are separate applications in a monorepo. They communicate via a versioned REST API.
- pgvector must be installed as a Postgres extension. The migration system handles this.
- All LLM calls are isolated in the `answering` domain. No LLM calls in connectors, ingestion, or retrieval logic.
- If we need to support self-hosted LLMs or switch providers, only `app/domains/answering/llm_provider.py` changes.
- The stack requires familiarity with async Python patterns. This is a deliberate choice for performance and simplicity over synchronous patterns.

---

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| Node.js backend | Weaker ML/LLM ecosystem |
| Django | Too much convention overhead for an API-first product |
| Next.js full-stack | Blurs backend/frontend separation; harder to scale API independently |
| Separate vector DB from day one | Premature operational complexity |
| Celery + RabbitMQ | Heavier than needed at early stage |
