# Quickstart — RAG Boilerplate

**Feature**: [001-rag-boilerplate](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-05-11

This is the developer flow once the boilerplate lands. It mirrors what the shipped `README.md` will say, but is preserved here as a planning artifact so future Claude / future contributors can sanity-check the surface the boilerplate is supposed to deliver.

## Prerequisites

- Docker Desktop or Docker Engine (with the Compose v2 CLI — `docker compose`, not `docker-compose`).
- A Gemini API key. (Get one from Google AI Studio. The boilerplate does not call Gemini, but later features will, and the app refuses to start without the key set — by design.)
- Optional: GNU `make`. Every `make` target has a literal `docker compose ...` / `uv run ...` equivalent printed in `make help`, for developers on Windows-without-WSL.

The reviewer does **not** need Python, `uv`, Postgres, or any Python packages on the host. Everything runs in containers.

## First-run flow (cold cache)

```text
$ git clone <repo>
$ cd RAGQuerySystem

$ cp .env.example .env
$ $EDITOR .env                            # fill in GEMINI_API_KEY=...

$ make up                                 # builds the app image, pulls pgvector/pgvector:pg16,
                                          # starts both services, waits for db healthy,
                                          # then app applies migration 0001 on startup
                                          # (see lifespan.py)

$ curl -s http://localhost:8000/health | jq
{
  "status": "ok",
  "schema_version": "0001_init_vector_store.sql",
  "db": "ok",
  "embedding_model": "text-embedding-004",
  "embedding_dim": 768
}
```

Expected time to green-on-health from `git clone`: under 5 minutes on a fresh machine (spec SC-001), the bulk of which is `docker pull pgvector/pgvector:pg16` and the first `uv sync` inside the app image build.

## Day-2 flow

```text
$ make down                               # stop everything; pgdata volume preserved
$ make up                                 # second start is fast: image cached,
                                          # migration runner sees 0001 in schema_migrations
                                          # and no-ops (spec FR-006)
$ curl -s http://localhost:8000/health    # still ok
```

## Tests and lint

```text
$ make lint                               # ruff check + ruff format --check
$ make test                               # unit tier — hermetic, no DB
$ make test-integration                   # gated; needs `make up` already running
```

Unit tests cover (per spec FR-009):
- `tests/unit/test_config.py` — empty/missing `GEMINI_API_KEY` raises `ValidationError` naming the field; valid env loads cleanly.
- `tests/unit/test_migrations.py` — `pending(applied: set[str], available: list[str]) -> list[str]` returns the right diff for empty / partial / fully-applied states.
- `tests/unit/test_health.py` — `GET /health` returns the documented payload when the DB pool's `ping()` succeeds, and 503 when it raises.

Integration test (one, against the real stack):
- `tests/integration/test_health_live.py` — hits `http://localhost:8000/health` and asserts the payload + status code against the actual pgvector container. Skipped unless `RUN_INTEGRATION=1`.

## Stub commands

These exist and are discoverable; they don't do useful work yet:

```text
$ make ingest                             # rag ingest: not yet implemented — delivered by feature 00X-pdf-ingest
$ echo $?
2

$ rag --help                              # lists ingest / query / eval (each marked "(stub)")
$ rag query "What is in the PDF?"
rag query: not yet implemented — delivered by feature 00X-query-pipeline
```

The stubs deliberately accept positional args (a PDF path, a question, etc.) so the surface stays stable when the downstream features land — no flag renames, no positional-vs-option changes mid-flight.

## Failure modes a reviewer might exercise

| What you do | What you should see | Why |
|-------------|---------------------|-----|
| Run `make up` with `GEMINI_API_KEY=` empty in `.env` | App container exits with a Pydantic `ValidationError` naming `GEMINI_API_KEY` | spec FR-003 / SC-005 — refusal happens at config load, not at first request |
| Run `make up` with the `db` service unhealthy (e.g., volume corrupted) | `app` waits up to its compose-level start period, then exits; `/health` is never reachable | `depends_on: db: condition: service_healthy` blocks app startup |
| Set `EMBEDDING_DIM=512` in `.env` without re-migrating | App container exits at startup with a clear "dimension mismatch: env=512, schema=768" message | R-004 — startup check compares env to `pg_attribute` |
| Hit `GET /health` after the db container is killed | 503 with `db: "error"` and the failure reason | spec FR-002, clarification Q2 — every call round-trips the DB |
| Run `make test` on a fresh checkout with no `make up` | Unit tests pass; integration tests are silently skipped | R-009 — hermetic default tier |

## What lives where (for navigating the repo after `git clone`)

| Question | File |
|----------|------|
| "How do I run this?" | `README.md` (top of file) |
| "Where do new env vars go?" | `.env.example` + `src/rag/config.py` (single source of truth) |
| "What does `/health` actually return?" | `specs/001-rag-boilerplate/contracts/health.yaml` |
| "What's the DB schema?" | `migrations/0001_init_vector_store.sql` + `specs/001-rag-boilerplate/data-model.md` |
| "Why was the migration tool not Alembic?" | `specs/001-rag-boilerplate/research.md` (R-002) |
| "How do I add a migration?" | `migrations/README.md` |
| "How does the CLI work?" | `specs/001-rag-boilerplate/contracts/cli.md` + `src/rag/cli/main.py` |

## What's intentionally not here yet

(Cross-references to the constitution and the spec, so the reviewer can see the discipline at work.)

- No retrieval, no Gemini calls, no answer generation, no eval execution.
- No frontend — `/health` is the only HTTP surface. FR-015 makes this binding.
- No HNSW / IVFFlat index on the embedding column. The retrieval feature will pick parameters when it picks a `k`.
- No chunking-boundary / retrieval-ranking / citation-construction / refusal-path tests. Those ship with the features whose code they exercise (Constitution Check note for Art VI).
- No `make demo`, no slide deck. Article VIII demo prep is a submission-time concern; the README has a "limitations and next steps" placeholder where that lands.
