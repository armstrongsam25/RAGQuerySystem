# Implementation Plan: RAG System Boilerplate

**Branch**: `001-rag-boilerplate` | **Date**: 2026-05-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-rag-boilerplate/spec.md`

## Summary

Establish the runnable skeleton for the small RAG system: a `docker compose` stack with a FastAPI `app` service and a `pgvector/pgvector:pg16` `db` service, a Python 3.12 codebase managed by `uv`, a versioned migration runner that the app invokes on startup, a `vector(768)`-pinned chunk schema that already carries the Article-II provenance fields, and a Typer-based CLI exposing `ingest`/`query`/`eval` as discoverable not-yet-implemented stubs. The boilerplate ships zero RAG logic and zero Gemini calls — the only user-visible runtime surface is `GET /health`, which on every call runs `SELECT 1` against the database and returns the applied schema version. All downstream RAG features (ingestion, retrieval, generation, evaluation) plug into slots this feature defines without renegotiating shape or interface.

## Technical Context

**Language/Version**: Python 3.12 (constitution Art IV.1)
**Primary Dependencies**: FastAPI, Pydantic v2 + `pydantic-settings`, `psycopg[binary,pool]` v3 (async), Typer, uvicorn, `pgvector` (Python bindings)
**Storage**: Postgres 16 + pgvector extension via the `pgvector/pgvector:pg16` image (constitution Art IV.3, IV.7). Chunk embedding column is `vector(768)`.
**Testing**: `pytest` + `pytest-asyncio` + `httpx.AsyncClient` for the health endpoint via FastAPI's lifespan. Unit tests hermetic (no real DB); a real-DB integration suite is gated behind `RUN_INTEGRATION=1` and runs against `make up`.
**Target Platform**: Linux containers via Docker Desktop / Docker Engine on the developer's machine. No production target in scope.
**Project Type**: Single project, web service (FastAPI app) + companion CLI + SQL migrations. No frontend (spec FR-015).
**Performance Goals**: Stand-up time ≤ 5 min from clone to green `/health` on a fresh machine (spec SC-001). No throughput target at boilerplate stage; pgvector index strategy is deferred to the retrieval feature.
**Constraints**: Single command must bring stack to a healthy state (spec FR-001); no committed secrets (FR-014); no live Gemini call at startup (FR-003); migrations apply on app startup before `/health` reports healthy (clarification Q1).
**Scale/Scope**: One PDF, one tenant, no concurrency targets — Article VII places multi-doc, multi-tenant, and observability beyond logs out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution: `Nymbl RAG Assessment Constitution` v1.0.1.

| Article | Title | Status | Evidence / Note |
|---------|-------|--------|-----------------|
| I | Grounding Is Non-Negotiable | N/A this feature | No answer generation in boilerplate; refusal path is implemented in the query feature. Plan leaves the slot (CLI stub `rag query`) but does not implement it. |
| II | Citations Carry Real Provenance | **PASS** | Schema (data-model.md) requires `source_document_id`, `page_number`, `char_offset_start`, `char_offset_end`, `raw_text` as NOT NULL on `chunk`. Stable `chunk_id` is the primary key (UUID v7). Article II is structurally enforced from day one — no later feature can insert a chunk without provenance. |
| III | Evaluation Before Demo | N/A this feature | Eval CLI is a stub per spec FR-007; eval set + Recall@k/MRR + LLM-as-judge are downstream-feature concerns. Boilerplate creates the slot, not the contents. |
| IV | Stack Decisions Are Fixed | **PASS** | Python 3.12 + uv ✓ (pyproject.toml + uv.lock). FastAPI + Pydantic v2 ✓. Postgres 16 + pgvector with `vector(768)` pinned in migration `0001` ✓. Gemini key handled in `pydantic-settings` only (no client wired) ✓. `docker compose` with `app` and `db` services using `pgvector/pgvector:pg16` ✓. No deviations. |
| V | Developer Experience | **PASS** | `make up` brings the stack up (Makefile dispatches to `docker compose up -d --build`). Scripted commands for `up`/`down`/`test`/`lint`/`ingest`/`query`/`eval` ✓ (spec FR-007). `.env.example` checked in; `.env` gitignored ✓ (FR-004, FR-014). README covers problem statement, architecture diagram, setup, example queries (placeholder noting "delivered with query feature"), eval results table (empty placeholder noting "delivered with eval feature"), known limitations ✓ — see Phase 1 quickstart for the structure. |
| VI | Code Quality Floor | **PASS, with sequencing note** | `ruff` for lint+format via `make lint` ✓. `pytest` with tests covering config-loading (incl. missing-key refusal), health endpoint, and migration idempotency ✓ (FR-009). **Note**: chunking-boundary, retrieval-ranking, citation-construction, and refusal-path tests required by Art VI.2 are downstream-feature tests — they ship with the feature whose code they exercise. The boilerplate does not stub them in to avoid empty-test-file noise. Type hints on public functions ✓ (FR-013). Structured logging via stdlib `logging` + JSON formatter ✓ (FR-010). No bare `except`, no silent fallbacks — enforced by `ruff` config (`E722`, `BLE001`) and a code-review rule rather than a runtime check. |
| VII | Scope Discipline | **PASS** | Out-of-scope items (multi-doc, auth, observability beyond logs, streaming, polished frontend) are not in the plan; FR-015 makes the no-frontend stance binding. Stretch goals (hybrid retrieval, reranker, table-aware chunking) are deferred. |
| VIII | The Demo Is the Product | **PASS** | Spec-kit artifacts (`spec.md`, this plan, future `tasks.md`) committed in `specs/001-rag-boilerplate/`. README stands alone (FR-012). Slide deck + 30-min demo dry-run are submission-time concerns, not boilerplate concerns; this plan does not preempt them but leaves the artifact slots clean. |

**Gate result**: PASS — no violations, no Complexity Tracking entries required. Article I and III evaluations are "N/A this feature" by design (the boilerplate leaves correctly-shaped slots); Article VI carries a sequencing note that does not constitute a violation.

## Project Structure

### Documentation (this feature)

```text
specs/001-rag-boilerplate/
├── plan.md              # This file
├── research.md          # Phase 0 — resolved technical decisions
├── data-model.md        # Phase 1 — DB schema (chunk, source_document, schema_migrations)
├── quickstart.md        # Phase 1 — developer flow once the boilerplate lands
├── contracts/
│   ├── health.yaml      # OpenAPI for GET /health
│   └── cli.md           # CLI surface (rag root + subcommands)
├── checklists/
│   └── requirements.md  # From /speckit-specify (already exists)
└── tasks.md             # NOT created here — /speckit-tasks output
```

### Source Code (repository root)

```text
RAGQuerySystem/
├── .env.example                 # All env vars the app reads, with safe placeholders
├── .gitignore                   # Already excludes .env, .venv, etc.
├── docker-compose.yml           # app + db services, named volume, db healthcheck
├── Dockerfile                   # python:3.12-slim base, uv-managed install
├── Makefile                     # up / down / test / lint / ingest / query / eval
├── pyproject.toml               # uv-managed deps, ruff config, pytest config
├── uv.lock                      # Committed
├── README.md                    # Problem statement, prerequisites, stand-up command,
│                                # health URL, command listing, limitations (FR-012)
├── src/
│   └── rag/
│       ├── __init__.py
│       ├── api.py               # FastAPI app + /health route (calls db.ping())
│       ├── config.py            # pydantic-settings — refuses startup on missing key
│       ├── db.py                # psycopg AsyncConnectionPool + ping() + tx helpers
│       ├── lifespan.py          # FastAPI lifespan: wait_for_db → apply_migrations → ready
│       ├── log.py               # JSON formatter via dictConfig
│       ├── migrations.py        # File-discovery + schema_migrations bookkeeping
│       └── cli/
│           ├── __init__.py
│           ├── main.py          # Typer app entry: `rag --help`
│           ├── ingest.py        # Stub: exit 2, "not yet implemented — see feature 00X-ingest"
│           ├── query.py         # Stub: exit 2, "not yet implemented — see feature 00X-query"
│           └── eval.py          # Stub: exit 2, "not yet implemented — see feature 00X-eval"
├── migrations/
│   ├── 0001_init_vector_store.sql   # CREATE EXTENSION vector; chunk; source_document; schema_migrations
│   └── README.md                # How the runner works; how to author a new migration
└── tests/
    ├── conftest.py              # FastAPI TestClient with mocked db pool
    ├── unit/
    │   ├── test_config.py       # Missing/empty key → ValidationError; valid env loads
    │   ├── test_migrations.py   # Pure-function tests for pending() computation
    │   └── test_health.py       # /health handler via TestClient, DB ping mocked
    └── integration/
        └── test_health_live.py  # Gated by RUN_INTEGRATION=1; against `make up` stack
```

**Structure Decision**: Single-project layout (Option 1 from the template). One Python package (`rag`) under `src/`, plus first-class top-level directories for `migrations/` (SQL files) and `tests/`. A standalone `frontend/` directory is omitted entirely — FR-015 forbids a frontend in this feature, and creating an empty placeholder directory invites the next contributor to fill it with the wrong thing. The package layout is shallow on purpose: the boilerplate's job is to leave **named, discoverable slots** (`db.py`, `migrations.py`, the empty `cli/{ingest,query,eval}.py` stubs) that downstream features extend, not to pre-build abstractions.

## Complexity Tracking

> No constitution violations in this feature. Section intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| _(none)_  | _(n/a)_    | _(n/a)_                             |
