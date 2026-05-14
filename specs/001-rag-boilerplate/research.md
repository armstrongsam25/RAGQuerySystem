# Phase 0 Research: RAG System Boilerplate

**Feature**: [001-rag-boilerplate](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-05-11

## Purpose

The constitution (Article IV) pins most of the high-level technology stack, and the clarification round closed the biggest behavioral ambiguities (migrations on app startup, `SELECT 1` on every `/health`, present-and-non-empty Gemini key check, no frontend). What's left for Phase 0 are the **library-level decisions inside each pinned slot** — the calls a senior engineer makes about which Postgres driver to use, how to load config, how migrations are tracked, how the CLI is wired. Each decision below resolves a "NEEDS CLARIFICATION"-class question that would otherwise surface during `/speckit-tasks` or implementation.

---

## R-001 — Database driver

**Decision**: `psycopg` v3 (`psycopg[binary,pool]`) in async mode, with `AsyncConnectionPool`.

**Rationale**:
- Modern Postgres driver actively maintained by the same project that owned `psycopg2`. Async support is first-class, not bolted on.
- Built-in connection pool (`psycopg_pool.AsyncConnectionPool`) — no second dependency (e.g., SQLAlchemy) for pool management at boilerplate stage.
- Integrates cleanly with `pgvector`'s Python bindings (`pgvector.psycopg.register_vector`) so downstream features can `INSERT ... VALUES (%s)` with a Python `list[float]` and the driver handles the `vector` type adapter.
- The same driver supports synchronous mode for the migration runner (which doesn't benefit from async), so we have one DB dependency, not two.

**Alternatives considered**:
- **asyncpg**: faster on raw throughput but its API is its own world (no DB-API), pool is less ergonomic, and pgvector support relies on third-party adapter packages. The marginal speed isn't worth the second mental model at boilerplate stage.
- **SQLAlchemy 2.0 async + asyncpg**: gives an ORM and a mature pool, but pulls in a heavy abstraction (Core + ORM + Alembic) that this feature would only use for `SELECT 1` and a single `INSERT INTO schema_migrations`. Constitution Art VII ("scope discipline") and the "no premature abstraction" rule both argue against pulling in an ORM before there's a query that benefits from one.

---

## R-002 — Migration tool

**Decision**: Hand-rolled, file-driven migration runner in `src/rag/migrations.py`. Migration files are plain `.sql` in `migrations/` named `NNNN_description.sql`. A `schema_migrations` table tracks applied filenames with timestamps.

**Rationale**:
- The boilerplate has exactly one migration (`0001_init_vector_store.sql`). Pulling in Alembic for a single SQL file is the textbook over-abstraction.
- A 50-line Python runner satisfies FR-006 (idempotency) and the "migration runner refuses to re-apply" acceptance scenario, with logic that's *visible to the reviewer in one screen* — which is itself a hiring-signal asset.
- Plain `.sql` files are reviewable by anyone familiar with Postgres, including the Nymbl team, without an Alembic mental model. The pgvector `vector(768)` type, the GIN/HNSW index choices that arrive later, and the provenance constraints all read cleanly as SQL.
- A future feature can swap in Alembic if migration complexity grows; the runner's contract (list of applied filenames in `schema_migrations`) is what Alembic uses too, so the migration is mechanical.

**Alternatives considered**:
- **Alembic**: standard choice but requires SQLAlchemy metadata (which we don't have, per R-001), and `alembic.ini` + `env.py` + a `versions/` directory is more ceremony than this feature warrants.
- **`dbmate`** / **`golang-migrate`**: language-external tools that add a Docker layer and a second binary. Rejected for the same reason — one SQL file doesn't justify a separate tool.

**Runner algorithm** (load-bearing for FR-006 + Art II):
1. On app startup, before binding the health endpoint as healthy, the lifespan handler opens a sync connection.
2. `CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())`.
3. List `migrations/*.sql` from disk, sorted lexically.
4. Query `SELECT name FROM schema_migrations` → set of applied.
5. For each unapplied file in order: open a transaction, execute the SQL, INSERT the filename, commit. On any error: rollback and raise — the app fails to start, surfacing the migration name in the log.
6. Idempotency: step 5 is empty when all files are applied; runner returns and the lifespan proceeds.

---

## R-003 — Config loader

**Decision**: `pydantic-settings` (Pydantic v2) with `SettingsConfigDict(env_file=".env", extra="forbid")`. Required fields have no default; type-level constraints (`SecretStr`, `PostgresDsn`, `min_length=1` for strings) handle the "missing or empty" refusal path (FR-003).

**Rationale**:
- Constitution Art IV already pins Pydantic v2 for request/response models — `pydantic-settings` is the natural companion and adds zero new mental model.
- Validation errors at startup are formatted by Pydantic into a list naming each failing field, which directly satisfies FR-003's "error message that names the missing variable" requirement without any custom error formatting.
- `SecretStr` for `GEMINI_API_KEY` prevents accidental logging of the value when the app structured-logs its config snapshot on startup.
- `extra="forbid"` is set on the model and catches typos in **direct kwargs** at the construction site (e.g., a test that builds a `Settings` programmatically). Note: it does **not** catch typo'd *environment variable* names, since pydantic-settings reads env vars by looking up declared field names rather than walking `os.environ` — an unknown env var is silently ignored, which is standard pydantic-settings behavior. Documented in `tests/unit/test_config.py` so a future reader doesn't expect protection that doesn't exist.

**Alternatives considered**:
- **`python-dotenv` + manual `os.environ` parsing**: cheaper dependency-wise but loses the validation surface (we'd hand-write the missing-key check, the type coercion, and the error messages — all the things Pydantic does for free).
- **`dynaconf`**: more powerful, but its layered-settings model is overkill for a one-env-file boilerplate.

**Env vars the boilerplate reads** (each appears in `.env.example` with a safe placeholder):

| Var | Type | Required | Notes |
|-----|------|----------|-------|
| `GEMINI_API_KEY` | `SecretStr` | yes (min length 1) | Boilerplate only checks presence; first ingest/query call validates against Gemini. |
| `DATABASE_URL` | `PostgresDsn` | yes | Defaults provided in `docker-compose.yml` to point at the `db` service. |
| `EMBEDDING_DIM` | `int` | no, default `768` | Matches the constitution-pinned Gemini `text-embedding-004` dim. Edge case 5 (config-vs-schema mismatch) is enforced by a startup check that compares this value to the `chunk.embedding`'s atttypmod. |
| `LOG_LEVEL` | `str` | no, default `"INFO"` | One of `DEBUG/INFO/WARNING/ERROR`. |
| `EMBEDDING_MODEL` | `str` | no, default `"text-embedding-004"` | Read for log/health-payload context; not used by Gemini client (no client at boilerplate stage). |
| `GENERATION_MODEL` | `str` | no, default `"gemini-2.0-flash"` | Same — recorded for downstream features, unused at boilerplate stage. |

---

## R-004 — Embedding-dimension drift check

**Decision**: At app startup, after migrations apply, query `pg_attribute` / `information_schema.columns` for the `chunk.embedding` column's pgvector dimensionality and compare to `settings.EMBEDDING_DIM`. On mismatch, raise and abort startup with a message naming both values.

**Rationale**:
- Spec edge case 5 requires the dimension mismatch to surface at startup, not at query time. The schema pins it (`vector(768)`) and the config defaults to 768, but a developer who changes the env var without re-migrating is the realistic failure mode.
- This is a 10-line check at startup and turns a class of silent retrieval-feature bugs into a loud boilerplate-stage failure.

**Alternatives considered**:
- **Trust the schema** (no check): violates the edge case requirement.
- **Generate the migration from `EMBEDDING_DIM`** (templating SQL): defeats "schema pins it" — the env var would be the source of truth, which is brittle in a multi-developer setting and makes the migration non-reviewable as static SQL.

---

## R-005 — Logging

**Decision**: stdlib `logging` configured via `dictConfig` with a JSON formatter implemented in `src/rag/log.py` (~30 LOC). No third-party logging library at boilerplate stage.

**Rationale**:
- Constitution Art VI.4 explicitly allows "stdlib logging with JSON formatter or structlog" — both are valid. stdlib avoids a dependency and is dead-simple to teach to a future contributor.
- A small custom JSON formatter (`logging.Formatter` subclass that returns `json.dumps({...})`) is more transparent than `python-json-logger` (a third-party dep) at the cost of ~20 LOC.
- Structured fields needed at boilerplate stage: `timestamp`, `level`, `logger`, `message`, plus extras (`schema_version`, `migration_name`, `db_url_host`). All fit into stdlib's `LogRecord.__dict__` mechanism cleanly.

**Alternatives considered**:
- **structlog**: more ergonomic context-binding, but the boilerplate has ~5 log call sites; the binding surface doesn't pay back the dependency yet. Easy to swap in later if the codebase grows.
- **loguru**: nice DX but its global state and monkey-patching habits are at odds with FastAPI's logger discovery; not a good fit.

---

## R-006 — CLI framework

**Decision**: `typer` (which uses Click underneath and Pydantic-style type-hint dispatch).

**Rationale**:
- Pairs naturally with the FastAPI + Pydantic stack — same type-hint mental model.
- The "discoverable" requirement (FR-007 acceptance #3) is satisfied for free: `rag --help` lists subcommands; `rag ingest --help` shows the stub's docstring.
- Stub commands are 5 lines each: emit a structured log line, print a user-facing message naming the downstream feature, `raise typer.Exit(code=2)`.

**Alternatives considered**:
- **`click`**: works fine but lacks the Pydantic-friendly type-hint signatures; more decorator boilerplate.
- **`argparse`**: stdlib but verbose for a 7-subcommand surface; help text is harder to make consistent across subcommands.
- **Separate shell scripts in `scripts/`**: avoidable now that the Makefile dispatches commands. One CLI entry point keeps Python logic in Python.

---

## R-007 — Container topology

**Decision**: Two `docker compose` services — `app` and `db`. `app` builds from a Dockerfile (`python:3.12-slim` base with `uv` installed via the official binary, deps synced via `uv sync --frozen`). `db` uses the `pgvector/pgvector:pg16` image directly. A named volume (`pgdata`) is mounted at `/var/lib/postgresql/data` on `db`.

**Rationale**:
- Constitution Art IV.7 mandates this exact topology (`app` and `db`, `pgvector/pgvector:pg16` image). No deviation.
- The `db` service includes a `healthcheck` running `pg_isready` every 5s. The `app` service uses `depends_on: db: condition: service_healthy` so it never starts against an unready DB. This is what makes the spec's "wait for DB before declaring healthy" edge case feasible without bespoke retry logic in the lifespan.
- Named volume (vs bind mount) keeps the developer's filesystem clean and aligns with spec FR-011 + SC-004 (state survives 10+ restarts).

**Alternatives considered**:
- **Single-service compose with embedded SQLite + vector hack**: violates Art IV.3 outright.
- **`pgvector/pgvector:pg17`**: constitution pins `pg16`. Locked.
- **`postgres:16` + manual `CREATE EXTENSION vector` from a SQL file**: would require getting the pgvector extension installed in the base image, which is what `pgvector/pgvector:pg16` already does. No reason to reinvent it.

---

## R-008 — Command dispatch surface

**Decision**: `Makefile` at repo root is the single command dispatcher. Each target delegates: `make up` → `docker compose up -d --build`, `make test` → `uv run pytest`, `make ingest` → `uv run rag ingest`, etc.

**Rationale**:
- Constitution Art V.1 names `make up` directly. Honoring the literal command keeps the README's stand-up section identical to what the constitution promises.
- A Makefile dispatching to `uv run` + `docker compose` is ~30 lines and doesn't add a runtime dependency (developers on macOS / Linux have `make`; on Windows the README documents `wsl` or `docker compose up -d --build` directly).
- Single source of truth for command names — what `make` runs and what `rag --help` shows are wired together, so spec FR-007's "discoverable from a single help listing" lands.

**Alternatives considered**:
- **`task` / `just`**: nicer syntax but adds a tool the reviewer probably doesn't have installed. Make is universal.
- **Python `invoke` / `nox`**: pulls in another Python dep just to dispatch to other Python deps; circular and unnecessary.
- **Shell scripts only (no Makefile)**: loses the one-line `make help` listing that FR-007 acceptance #3 leans on.

---

## R-009 — Test strategy

**Decision**: Two tiers.

- **Unit tier** (default, hermetic, runs via `make test`): `pytest` + `pytest-asyncio`. Covers config loading (missing/empty key, valid env), migration runner's pure-function pieces (which files are pending given a `set[applied_names]`), and the `/health` handler invoked through `httpx.AsyncClient` against the FastAPI app with the DB pool replaced by a fake whose `ping()` returns immediately. Zero real Postgres dependency.
- **Integration tier** (gated, real-DB, runs via `make test-integration` against an already-running `make up` stack): `pytest -m integration`. The integration suite at boilerplate stage contains one test — that `/health` returns 200 with the expected schema version against the actual `pgvector/pgvector:pg16` container. Marked tests skip silently when `RUN_INTEGRATION` is not set.

**Rationale**:
- FR-009 says "boilerplate tests MUST pass on a fresh checkout" — this is only achievable if the default tier doesn't depend on Docker being up. The hermetic unit tier satisfies that bar.
- An integration test that runs against the real stack is what proves the migration ↔ schema ↔ `/health` chain actually works end-to-end. Gating it behind an env var means CI and casual contributors don't have to spin up containers, but the reviewer doing the demo can run `RUN_INTEGRATION=1 make test-integration` for the full picture.
- Avoids `testcontainers-python`: adding it would pull in `docker-py`, add a 30-second-per-suite Postgres spin-up time, and create a separate code path for spinning up DBs vs. what `compose up` does. The two tiers above achieve the same coverage with less surface area.

**Alternatives considered**:
- **Testcontainers everywhere**: one tier, but every test pays the Postgres start-up cost. Slow feedback loop.
- **Mocks all the way down (no integration tier)**: the `/health` ↔ pgvector chain is never exercised end-to-end, which is exactly what the demo needs to show works.

---

## Resolved NEEDS CLARIFICATION items

All Technical Context fields are now concrete. No `NEEDS CLARIFICATION` markers remain. Phase 1 can proceed.
