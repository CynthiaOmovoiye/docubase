# docbase

**Grounded AI twins over curated knowledge** — a multi-tenant platform where owners group **workspaces** and **twins**, attach **sources** (Google Drive, PDFs, URLs, markdown, manual notes), and expose **public chat** that answers from indexed context — not from raw secrets, bulk code dumps, or unbounded speculation.



---

## 1. Problem, scope, and AI fit

**Problem:** Knowledge lives in heterogeneous places (Drive folders, resumes, internal docs). Teams and individuals need a **single conversational surface** that stays **on-policy**, **traceable**, and **grounded**, while still feeling like a person or product — not a generic chatbot that leaks filenames, internal evidence scaffolds, or invented facts.

**Scope (intentionally bounded):**

- Multi-tenant **users → workspaces → twins → sources → chunks (pgvector)**.
- **Twin chat** (one twin) and **workspace chat** (route or aggregate across twins).
- **Share surfaces** — slug-based public twin or workspace pages with anonymous, rate-limited sessions.
- **Memory layer** — synthesized **Memory Brief** and memory-derived chunks for “why / what changed / risk” style questions, separate from owner-edited persona text.

**Why this is a strong AI fit:** The product is **RAG plus explicit guardrails** — retrieval, intent hints, deterministic **evidence verification**, and an optional **LLM-as-judge gate** with **Pydantic-validated** structured output and **bounded regeneration** before a reply is saved. That is closer to **production LLM systems** than a single-shot `complete()` demo.

---

## 2. Architecture and design trade-offs

| Concern | Design | Trade-off |
|--------|--------|-----------|
| Primary abstraction | **Twin** owns sources and chat identity — not “a repo” or “a folder” | More UX/product modeling; clearer tenancy and sharing |
| Ingestion vs chat | Connectors pull bytes/text; normalization and chunking are **offline / job-driven** | Latency shifted off the hot path; eventual consistency |
| Retrieval | Vector + lexical + structured hints; **intent-aware** boosts in SQL | Additive boosts, not hard filters — avoids empty results when memory types are sparse |
| Answering | **Twin** and **workspace** system prompts in `backend/app/domains/answering/generator.py` — persona, brief, chunks, conversation memory | Two prompt contracts to maintain |
| Safety | **Policy** tiering (always block secrets; code snippets opt-in per twin) at ingest, retrieve, and pre-LLM | Stricter pipeline; more code paths to test |
| Evidence | **Verifier** enforces grounded references and workspace section discipline | Conversational turns need **explicit exceptions** so natural prose is not replaced by internal “evidence dump” templates |
| Quality | **Active gate** (sync judge + regen) vs **passive** dimensional judge (async) — configurable | Active path adds latency and cost; improves answer quality under rubric-style review |

**Domain layout (modular monolith):** `backend/app/domains/{chat,answering,retrieval,policy,memory,twins,connectors,evaluation,...}` with **API surface** under `backend/app/api/v1/`. Frontend: React + TypeScript + Vite in `frontend/`.

Deeper diagrams and data flow: [`docs/architecture.md`](docs/architecture.md).

---

## 3. Prompt, model interaction, and structured output (technical depth — prompts & control)

- **Twin answers:** Owner notes + Memory Brief + retrieved chunks + source list awareness; sanitised injection and regeneration hints on verifier retry.
- **Workspace aggregate answers:** Multi-project context blocks; instructions to avoid “workspace admin” tone and internal routing dumps for visitor-facing chat.
- **Structured judge output:** `backend/app/domains/evaluation/quality_gate.py` defines `ResponseQualityGate` (`pydantic`, `extra="forbid"`) with `is_acceptable: bool` and `feedback: str`. Judge JSON is extracted and validated with **`model_validate_json`** — invalid shapes fail closed to logging, not to user-visible stack traces (gate errors **fail open** to the last draft).
- **Passive rubric scoring:** When the active gate is **off**, `evaluate_response_async` runs after persist and can push multi-axis scores to **Langfuse** — useful for dashboards without blocking chat.

---

## 4. Orchestration and control flow (technical depth — orchestration)

Simplified **authenticated / public chat** path (`send_message` in `backend/app/domains/chat/service.py`):

1. **Trace** — Langfuse trace when keys are configured.
2. **Intent** — `analyse_query` for retrieval boosts and routing hints.
3. **Retrieve** — per-twin packet, **workspace aggregate** (multi-twin retrieval + merge), or **routed** single twin inside a workspace.
4. **Generate** — `generate_answer` or `generate_workspace_answer`.
5. **Verify** — `verify_single_project_answer` or `verify_workspace_answer` (reference safety, workspace headers, code fences).
6. **Quality gate (optional)** — If `chat_quality_gate_enabled`, **synchronous** judge + up to `chat_quality_gate_max_regenerations` extra generations with explicit feedback, then **re-verify**. Workspace aggregate runs this inside `_answer_across_workspace` after the workspace verifier.
7. **Persist** — message row + chunk id audit fields; authority / latency diagnostics logged.

This is **branching orchestration** (retrieve modes × verifier retries × gate loops), not a single LLM call — deliberate for **correctness over raw fluency**.

---

## 5. Engineering practices (code, errors, tests, observability)

| Rubric axis | How docbase addresses it |
|-------------|----------------------------|
| **Code structure** | Domain-driven `app/domains/*`, thin API routers, Pydantic settings in `app/core/config.py` |
| **Logging & errors** | Structured logger usage; evaluation/gate failures logged without echoing secrets or full chunk bodies |
| **Tests** | `backend/tests/unit/` — includes chat routing, **verifier**, **quality gate JSON**, generators with mocked LLM provider; integration tests where DB is available |
| **Observability** | Langfuse generations (`answer_generation`, `response_quality_gate`, …), trace metadata (`workspace_id`, `doctwin_id`), latency budget warnings (`chat_*_latency_budget_ms`, `workspace_chat_total_latency_budget_ms`) |

Local dev: Docker Compose, `./scripts/setup.sh`, `make help` / `make test`. API docs: `/api/docs` when the API is running.

---

## 6. Production readiness (feasibility, evaluation, deployment)

**Feasibility:** The stack is deliberately boring-operable: **PostgreSQL + pgvector**, **Redis + ARQ** for jobs, **FastAPI**, containerized local path, and documented AWS-oriented deploy for the static frontend ([`docs/DEPLOY_SETUP_GUIDE.md`](docs/DEPLOY_SETUP_GUIDE.md)).

**Evaluation strategy (rubric-aligned):**

| Layer | What it proves |
|-------|----------------|
| **Unit / integration tests** | Regressions on routing, verifier, gate parsing, and prompt contracts |
| **Deterministic verifier** | Grounded references and workspace answer shape |
| **Active LLM-as-judge + Pydantic** | Binary accept + textual feedback driving **bounded** regeneration **before** the user sees the message |
| **Passive judge + Langfuse** | Dimensional scores when the active gate is disabled — baseline for experiments |

Configure via `.env` / `CHAT_QUALITY_GATE_*` (see `.env.example`).

**Deployment / CI:** GitHub Actions workflows under [`.github/workflows/`](.github/workflows/) (e.g. `deploy.yml`, `destroy.yml`) for automated delivery patterns.

---

## 7. Product surfaces (presentation — what to demo)

- **Owner experience:** Twin configuration, sources, memory brief status, workspace chat, share link management.
- **Public experience:** Twin share (`/t/:slug`) and workspace share (`/w/:slug`) — anonymous chat against **active** share surfaces only.

Public UI is intentionally calm: scope of who you are talking to should be obvious; technical internals belong in logs and owner tools, not in visitor copy.

---

## 8. Repository map

```
docbase/
├── backend/       FastAPI app, domains, jobs, tests
├── frontend/      React + TypeScript + Vite
├── docs/          Architecture, deploy guides, ADRs
├── infra/         Docker and supporting infra
├── scripts/       Developer setup helpers
└── .github/       CI/CD workflows
```

Layout details: [`docs/workspace.md`](docs/workspace.md).

---

## 9. Agent / contributor entry points

- [`CLAUDE.md`](CLAUDE.md) — Claude Code session rules for this repository.
- [`AGENTS.md`](AGENTS.md) — Codex / agent session rules (aligned with Claude).

---

## 10. Future Directions
- Finishing compatibility for code snippets

## License

Private — all rights reserved.
