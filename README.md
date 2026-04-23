# docubase

A multi-tenant SaaS platform for creating shareable AI twins for any knowledge source — repositories, resumes, portfolios, projects, or documents.

Users create a twin, attach sources, and share a link. Visitors can chat with the twin and get intelligent answers grounded in approved knowledge — without exposing raw code, secrets, or sensitive implementation details.

---

## What it does

- **Create twins** backed by GitHub repos, PDFs, markdown, URLs, or manual content
- **Chat with a twin** — answers grounded in indexed knowledge, not raw code dumps
- **Share a twin** — public link at `/t/:slug`, embeddable widget for any website
- **Career twin** — connect your resume, repos, and portfolio. Recruiters chat with your twin instead of reading a PDF.
- **Workspace chat** — ask across all your twins; the system routes to the right one automatically

## Privacy model

Three tiers, always enforced:

| Tier | Default | Configurable |
|------|---------|-------------|
| Always blocked: `.env`, keys, secrets, credentials | Blocked | Never |
| Code snippets (scoped sections only) | Off | User can enable per twin |
| Structure, docs, summaries, architecture, dependencies | On | Always available |

---

## Local development

**Prerequisites:** Docker, Docker Compose

```bash
git clone https://github.com/<your-account>/docubase.git
cd docubase
./scripts/setup.sh
```

Then:
- Backend: http://localhost:8000
- Frontend: http://localhost:5173
- API docs: http://localhost:8000/api/docs

See `Makefile` for all available commands:

```bash
make help
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 + FastAPI |
| Frontend | React 18 + TypeScript + Vite |
| Database | PostgreSQL + pgvector |
| Cache / Jobs | Redis + ARQ |
| LLM | OpenAI (abstracted — swappable) |
| Local dev | Docker Compose |

---

## Project structure

See `docs/workspace.md` for the full directory guide.

```
docubase/
├── backend/          Python + FastAPI
├── frontend/         React + TypeScript
├── infra/            Docker, migrations, scripts
├── docs/             Architecture, ADRs
└── scripts/          Dev utilities
```

---

## Architecture

See `docs/architecture.md` for the full domain model and data flow.
See `docs/repo-intelligence-roadmap.md` for the canonical repo intelligence
roadmap and implementation guide.

Key principle: **Repo is not the top-level concept.** A GitHub repository is one `Source` of type `github_repo`. The `Twin` is the primary product abstraction.

---

## Contributing

- All config in `.env` (copy from `.env.example`, never commit `.env`)
- Run `make check-secrets` before pushing
- Run `make test` before opening a PR
- New architectural decisions get an ADR in `docs/adr/`

---

## License

Private — all rights reserved.


