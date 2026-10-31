# QAutos

**Security questionnaires, answered with proof.**

QAutos drafts answers to security questionnaires (SOC 2, CAIQ, SIG, HECVAT or your
customer's own spreadsheet) from your company's own policies and reports. Every
answer cites the document, page and section it came from and carries a confidence
score. When the evidence isn't there, QAutos doesn't guess: the question goes to a
person.

> **Status: work in progress.** Document upload, indexing, search with citations and
> the admin workspace work today. Questionnaire import and answer drafting are being
> built in phases (see [Roadmap](#roadmap)).

## How it works

1. **Upload your evidence.** Security policies, SOC 2 reports, continuity plans and
   past questionnaires (PDF, DOCX, XLSX).
2. **QAutos indexes it.** Text is extracted with real page numbers and section
   headings, split into passages that never cross a section, and embedded for search.
3. **Import a questionnaire** *(coming)*. Any format, including scanned PDFs and images.
4. **Get drafted answers** *(coming)*. Each one cites its sources and comes with a
   confidence score built from measurable signals (retrieval strength, an independent
   check of each claim, agreement with previously approved answers).
5. **Review and export** *(coming)*. Approve, edit or answer manually, then export in
   the original format. Approved answers go into a reusable Answer Library.

## Built for security teams

- **Your data stays yours.** Every organization is isolated at the database level
  with Postgres row-level security, and tests prove one organization can never
  retrieve another's documents or passages.
- **No training on customer data.** Use model providers on API terms that exclude
  training, and opt out where a provider offers it (see [Deployment](#deployment)).
- **Encrypted at rest** in object storage, with downloads through short-lived
  signed links.
- **Audit log** of who uploaded, downloaded, approved or deleted what.
- **No customer content in logs.** Logging uses an allowlist of safe fields.
- **Roles:** owner, editor, viewer.

## Tech stack

| Layer | Technology |
|---|---|
| Web | Next.js 16, React 19, TypeScript, Tailwind CSS v4, TanStack Query |
| Auth | Clerk (organizations + roles) |
| API | FastAPI, SQLAlchemy 2 (async), Pydantic |
| Worker | arq on Redis |
| Database | PostgreSQL + pgvector (HNSW), row-level security |
| Documents | PyMuPDF, LibreOffice (DOCX → PDF), openpyxl |
| Embeddings | Voyage AI or any OpenAI-compatible API (swappable) |
| LLM | Claude API *(answer drafting, coming)* |
| Storage | S3-compatible (Cloudflare R2, AWS S3) |
| Hosting | Railway (web, api, worker, Postgres, Redis) |

## Repository layout

| Path | What |
|---|---|
| `apps/api` | FastAPI API and the background worker |
| `apps/web` | Next.js app: marketing site and workspace |
| `infra/postgres` | Database role setup |
| `docs/adr` | Architecture decision records |

## Getting started

Prerequisites: Docker, or Node 24 + pnpm 9 and Python 3.12+ with
[uv](https://docs.astral.sh/uv/), plus Postgres (with pgvector) and Redis.

```sh
cp .env.example .env      # fill in Clerk keys; see comments in the file
docker compose up --build
```

Open http://localhost:3000. API docs are at http://localhost:8000/docs.

Without Docker:

```sh
cd apps/api
uv sync
uv run alembic upgrade head
uv run uvicorn sqa.main:create_app --factory --reload
uv run arq sqa.worker.settings.WorkerSettings      # in a second terminal

cd apps/web
pnpm install
pnpm dev
```

For local development, `EMBEDDINGS_PROVIDER=hash` and `STORAGE_BACKEND=local` need
no API keys or bucket. Both are refused in production.

### Demo workspace

Set `NEXT_PUBLIC_DEMO_MODE=1` (web, at build time) and the same `DEMO_JWT_SECRET`
(32+ characters) on web and api. **Try the demo** then opens a shared sample
organization, "Northwind (Demo)", with seeded members and documents, without an
account. Demo sessions are locked to that organization by the API.

## Testing

```sh
cd apps/api
uv run pytest                     # unit tests
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres uv run pytest
                                  # + tenant isolation tests against a real Postgres
cd apps/web
pnpm test && pnpm typecheck && pnpm lint
```

CI runs all of it and fails if the isolation tests can't reach a database or if
retrieval quality drops below the benchmark floor. To benchmark a configuration
(for example with Voyage embeddings and reranking) against the demo documents:

```sh
uv run python scripts/eval_retrieval.py
```

## Deployment

### Website preview (GitHub Pages)

The marketing site and its scripted live demo are published to GitHub Pages by
`.github/workflows/pages.yml` on every push to `main` that touches `apps/web`.
It builds with `NEXT_PUBLIC_STATIC_PREVIEW=1`: a static export without the
workspace, sign-in or demo endpoints, since Pages has no server. One-time setup:
**Settings → Pages → Build and deployment → Source: GitHub Actions**.

### Full application

QAutos is set up for [Railway](https://railway.com) with five services: web, api,
worker, Postgres (pgvector) and Redis. Each app service has a config file
(`apps/api/railway.api.json`, `apps/api/railway.worker.json`, `apps/web/railway.json`),
migrations run before every API deploy, and all settings are listed in
`.env.example`.

Before going live: create the database app role (`infra/postgres/create_app_role.sql`),
use a private bucket, set `ENVIRONMENT=production`, and opt out of training in your
embedding provider's dashboard.

## Roadmap

- [x] Multi-tenant foundation: auth, roles, row-level security, audit log
- [x] Document upload and indexing with page-level citations
- [x] Search with citations, and a retrieval quality benchmark
- [ ] Questionnaire import from any format, including scans
- [ ] Answer drafting with an evidence gate and confidence scores
- [ ] Review workflow and export to the original format
- [ ] Answer Library

## Architecture decisions

- [0001 Tenancy](docs/adr/0001-tenancy.md): how organizations are isolated
- [0002 Confidence and extraction](docs/adr/0002-confidence-and-extraction.md):
  how answers are scored and questionnaires are read
- [0003 Ingestion](docs/adr/0003-ingestion.md): how documents become cited passages
- [0004 Retrieval](docs/adr/0004-retrieval.md): hybrid search and how it is measured
