---

description: "Task list for 001-rag-boilerplate"
---

# Tasks: RAG System Boilerplate

**Input**: Design documents in [specs/001-rag-boilerplate/](.)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Tests are **required** by spec FR-009 (config loading incl. missing-key refusal, health endpoint, migration idempotency). Included throughout, not optional.

**Organization**: Grouped by user story per spec.md (US1 / US2 / US3). Each story is independently completable and testable.

## Format

`[ID] [P?] [Story?] Description with file path`

- **[P]**: Parallelizable — different files, no dependency on incomplete tasks in the same phase.
- **[Story]**: User story (US1/US2/US3) the task belongs to. Setup, Foundational, and Polish phases carry no story label.

## Path Conventions

Single-project layout per [plan.md §Project Structure](./plan.md). All paths are repo-relative from `RAGQuerySystem/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repository scaffolding and tooling — no application logic yet.

- [X] T001 Create top-level directory layout: `src/rag/`, `src/rag/cli/`, `migrations/`, `tests/unit/`, `tests/integration/`. Add empty `__init__.py` to `src/rag/`, `src/rag/cli/`, `tests/`, `tests/unit/`, `tests/integration/`.
- [X] T002 Initialize `pyproject.toml` at repo root with project metadata (`name = "rag"`, Python 3.12, build-backend = `hatchling`), runtime deps (`fastapi`, `pydantic-settings`, `psycopg[binary,pool]`, `typer`, `uvicorn[standard]`, `pgvector`), dev deps (`pytest`, `pytest-asyncio`, `httpx`, `ruff`), and `[project.scripts]` registering `rag = "rag.cli.main:app"`. Reference: research R-001, R-003, R-006.
- [X] T003 Add `[tool.ruff]` section to `pyproject.toml` enforcing constitution Art VI.1/.5 (lint rules including `E722` and `BLE001` to forbid bare/blind excepts; format settings; target-version `py312`).
- [X] T004 Add `[tool.pytest.ini_options]` section to `pyproject.toml` with `asyncio_mode = "auto"`, `markers = ["integration: requires RUN_INTEGRATION=1 and a running make-up stack"]`, and `addopts = "-m 'not integration'"` so default `make test` skips the integration tier (research R-009).
- [X] T005 [P] Write `.gitignore` at repo root excluding `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `pgdata/` (defense in depth — named volume should never land on disk in the repo, but in case of bind-mount mistakes).
- [X] T006 [P] Write `.env.example` at repo root with the 6 variables documented in research R-003 (`GEMINI_API_KEY`, `DATABASE_URL`, `EMBEDDING_DIM`, `LOG_LEVEL`, `EMBEDDING_MODEL`, `GENERATION_MODEL`), each with a safe placeholder and a one-line comment.
- [X] T007 [P] Write `Dockerfile` at repo root: base `python:3.12-slim`, install `uv` via the official installer, `COPY pyproject.toml uv.lock ./`, `uv sync --frozen --no-dev`, `COPY src/ src/`, `COPY migrations/ migrations/`, `CMD ["uv", "run", "uvicorn", "rag.api:app", "--host", "0.0.0.0", "--port", "8000"]`.
- [X] T008 [P] Write `docker-compose.yml` at repo root with `app` (builds from `Dockerfile`, depends on `db: condition: service_healthy`, env from `.env`, ports `8000:8000`) and `db` (image `pgvector/pgvector:pg16`, named volume `pgdata:/var/lib/postgresql/data`, env `POSTGRES_USER/DB/PASSWORD` from `.env`, `healthcheck: pg_isready -U $$POSTGRES_USER` every 5s). Reference: research R-007.
- [X] T009 [P] Write `Makefile` at repo root with targets `up`, `down`, `logs`, `test`, `test-integration`, `lint`, `fmt`, `ingest`, `query`, `eval`, and a self-documenting `help` target that greps `## ` annotations from the Makefile. Each target body is a single `docker compose` or `uv run` invocation per the contract in [contracts/cli.md](./contracts/cli.md).
- [X] T010 Run `uv lock` to generate `uv.lock`; commit the file. Depends on T002/T003/T004 (pyproject.toml must be complete).

**Checkpoint**: `make help` lists every command, `make lint` runs (and passes — no source yet), `make up` builds and starts containers but the app will crash on import until Phase 2.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Cross-cutting modules every user story depends on: config loading, structured logging, and the package root.

**⚠️ CRITICAL**: No user-story task may begin until this phase is complete — every story imports from `rag.config` or `rag.log`.

- [X] T011 Implement `src/rag/__init__.py`: read `__version__` from package metadata via `importlib.metadata.version("rag")`; expose nothing else.
- [X] T012 [P] Implement `src/rag/log.py`: a `JsonFormatter(logging.Formatter)` whose `format()` returns `json.dumps({"ts": ..., "level": ..., "logger": ..., "msg": ..., **record.__dict__ extras})`; a `configure_logging(level: str) -> None` that calls `logging.config.dictConfig(...)`; and a `get_logger(name: str) -> logging.Logger` helper. Reference: research R-005, constitution Art VI.4.
- [X] T013 [P] Implement `src/rag/config.py`: a `Settings(BaseSettings)` Pydantic model with `SettingsConfigDict(env_file=".env", extra="forbid")` and the 6 fields from R-003 — `GEMINI_API_KEY: SecretStr` (`min_length=1`), `DATABASE_URL: PostgresDsn`, `EMBEDDING_DIM: int = 768`, `LOG_LEVEL: str = "INFO"`, `EMBEDDING_MODEL: str = "text-embedding-004"`, `GENERATION_MODEL: str = "gemini-2.0-flash"`. Expose `get_settings()` as a cached factory (`functools.lru_cache`). Reference: spec FR-003, FR-004, FR-014.

**Checkpoint**: `from rag.config import get_settings; from rag.log import configure_logging` works at the REPL with the right env. No HTTP surface yet.

---

## Phase 3: User Story 1 — One-Command Local Stand-Up (Priority: P1) 🎯 MVP

**Story goal**: A fresh-machine reviewer runs `cp .env.example .env`, fills the key, runs `make up`, and within minutes `GET http://localhost:8000/health` returns 200 with the documented payload. Spec acceptance scenarios US1.1–US1.4 all pass.

**Independent test**: On a machine with only Docker and a Gemini API key, follow the [quickstart.md](./quickstart.md) "First-run flow" verbatim. `curl -s http://localhost:8000/health | jq` returns the payload shaped by [contracts/health.yaml](./contracts/health.yaml).

### Tests for User Story 1

Write these before implementation; verify they fail before T020–T022.

- [X] T014 [P] [US1] Write `tests/conftest.py`: fixtures `settings_factory` (returns a `Settings` constructor that takes overrides via kwargs, builds from a controlled env dict) and `fake_db_pool` (an object with an async `ping()` method whose return / side-effect is set per-test).
- [X] T015 [P] [US1] Write `tests/unit/test_config.py`: missing `GEMINI_API_KEY` → `ValidationError` whose `.errors()[0]["loc"]` includes `"GEMINI_API_KEY"`; empty-string key → same error; valid env → `Settings` instance with `get_secret_value()` returning the key; typo'd env var (e.g., `GEMINY_API_KEY`) → `ValidationError` mentioning the extra field. Covers spec FR-003 + clarification Q3.
- [X] T016 [P] [US1] Write `tests/unit/test_health.py`: build the FastAPI app with `fake_db_pool` injected; `GET /health` with `ping()` returning ok → 200 + payload matches the `HealthOk` schema in [contracts/health.yaml](./contracts/health.yaml); `ping()` raising → 503 + payload matches `HealthUnhealthy`. Uses `httpx.AsyncClient(app=app, base_url="http://test")`.
- [X] T017 [US1] Write `tests/integration/test_health_live.py` marked `@pytest.mark.integration`: hits `http://localhost:8000/health` via `httpx.AsyncClient`, asserts 200, asserts `schema_version == "0001_init_vector_store.sql"` and `embedding_dim == 768`. Test is skipped silently when `RUN_INTEGRATION` is unset (handled by the pytest `addopts` from T004).

### Implementation for User Story 1

- [X] T018 [P] [US1] Implement `src/rag/db.py`: `make_pool(dsn: str) -> AsyncConnectionPool` (psycopg pool factory with sensible min/max sizes); `async def ping(pool, timeout_s: float = 2.0) -> None` runs `SELECT 1` with a per-call timeout (raises on failure or timeout); `register_pgvector(conn)` hook for downstream features. No SQL beyond `SELECT 1` at this stage. Reference: research R-001.
- [X] T019 [P] [US1] Implement `src/rag/migrations.py`: `list_available(migrations_dir: Path) -> list[Path]` returning lexically-sorted `*.sql` files; `applied(conn) -> set[str]` querying `schema_migrations`; `pending(applied: set[str], available: list[Path]) -> list[Path]` pure-function diff; `apply(conn, path: Path) -> None` runs the SQL in a transaction and INSERTs the filename; `run_pending(dsn: str, migrations_dir: Path) -> str` orchestrates the loop, creates `schema_migrations` if missing, returns the name of the most recent applied migration. Uses sync `psycopg.connect`. Reference: research R-002.
- [X] T020 [US1] Implement `src/rag/lifespan.py`: an `@asynccontextmanager async def lifespan(app: FastAPI)` that (1) calls `configure_logging(settings.LOG_LEVEL)`, (2) waits for DB reachability with bounded retry (5 retries × 2s, gives up loudly), (3) calls `migrations.run_pending(...)`, (4) runs the dimension-drift check from research R-004 (`SELECT atttypmod FROM pg_attribute WHERE attrelid='chunk'::regclass AND attname='embedding'` → compare to `settings.EMBEDDING_DIM`, raise on mismatch), (5) creates the async pool via `db.make_pool(...)` and stores it on `app.state.pool` and `app.state.schema_version`, (6) yields, (7) on shutdown closes the pool. Logs structured events at each step (FR-010). Depends on T012, T013, T018, T019.
- [X] T021 [US1] Implement `src/rag/api.py`: `app = FastAPI(lifespan=lifespan)`; route `GET /health` whose handler reads `app.state.pool`, calls `db.ping(pool)`, on success returns a Pydantic `HealthOk` model matching [contracts/health.yaml](./contracts/health.yaml) (with `schema_version=app.state.schema_version`, `embedding_dim=settings.EMBEDDING_DIM`, `embedding_model=settings.EMBEDDING_MODEL`), on `ping()` failure returns `HealthUnhealthy` with HTTP 503. Pydantic v2 response models with `model_config = ConfigDict(extra="forbid")`. Depends on T020.
- [X] T022 [US1] Add a structured-log call for every `/health` invocation in `src/rag/api.py` at INFO with fields `{"event": "health_check", "status": "ok"|"error", "duration_ms": ...}`. Satisfies spec FR-010 for the health-check event.

**Checkpoint**: `make up && curl http://localhost:8000/health` returns 200 with the documented payload. Acceptance scenarios US1.1, US1.2, US1.4 all green. (US1.3 — restart preservation — is verified later via T037 quickstart validation.)

---

## Phase 4: User Story 2 — Scripted Developer Commands (Priority: P2)

**Story goal**: Every command in [contracts/cli.md](./contracts/cli.md) is reachable via both `rag <cmd>` and `make <cmd>`. `rag --help` and `make help` each list the same set of commands. Ingest/query/eval are discoverable stubs exiting code 2.

**Independent test**: Run `rag --help`, `make help`, `rag ingest /tmp/x.pdf`, `rag query "test"`, `rag eval`. Each subcommand stub exits with code 2 and writes the documented "not yet implemented" message to stderr.

### Tests for User Story 2

- [X] T023 [P] [US2] Write `tests/unit/test_cli_stubs.py`: parametrize over `("ingest", "00X-pdf-ingest"), ("query", "00X-query-pipeline"), ("eval", "00X-eval-harness")`; use `typer.testing.CliRunner` to invoke each command; assert exit code 2, assert stderr contains both the command name and the feature id, assert stdout is empty. Covers spec FR-007 acceptance #3.

### Implementation for User Story 2

- [X] T024 [P] [US2] Implement `src/rag/cli/__init__.py`: re-export `app` from `rag.cli.main`.
- [X] T025 [US2] Implement `src/rag/cli/main.py`: a `typer.Typer(help="Small RAG system CLI...")` instance named `app`; `--version` callback printing `rag.__version__`; register subcommands from `ingest`, `query`, `eval` modules. Reference: [contracts/cli.md](./contracts/cli.md).
- [X] T026 [P] [US2] Implement `src/rag/cli/ingest.py`: a single Typer subcommand `ingest(pdf_path: Optional[Path] = typer.Argument(None))` that emits the structured log line per cli.md ("event": "cli_stub_invoked", "command": "ingest", "feature": "00X-pdf-ingest"), writes the user-facing message to `sys.stderr`, and raises `typer.Exit(code=2)`.
- [X] T027 [P] [US2] Implement `src/rag/cli/query.py`: same pattern as T026 for `query(question: Optional[str] = typer.Argument(None))`, feature id `00X-query-pipeline`.
- [X] T028 [P] [US2] Implement `src/rag/cli/eval.py`: same pattern as T026 for `eval()` (no positional args), feature id `00X-eval-harness`.

**Checkpoint**: `uv run rag --help` lists 3 subcommands; each stub behaves per contract. `make help` lists every Make target. Acceptance scenarios US2.1, US2.2, US2.3 all green.

---

## Phase 5: User Story 3 — Versioned Vector Schema with Provenance Fields (Priority: P2)

**Story goal**: The `chunk` table exists with every Article II provenance field NOT NULL + CHECK-constrained, embedding pinned to `vector(768)`, and a stable UUID id. The migration runner refuses to re-apply.

**Independent test**: Connect to the running `db` service (`docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB`) and run `\d+ chunk`. All eight columns from data-model.md are present with the documented types and constraints. `make down && make up` does not re-apply migration `0001` (log shows "pending migrations: 0").

### Tests for User Story 3

- [X] T029 [P] [US3] Extend `tests/unit/test_migrations.py` (file created here, or split if T019 already wrote a stub): unit tests for `pending(applied, available)` covering empty-applied / fully-applied / partial-applied / unknown-applied-name cases. Uses `tmp_path` and constructed file lists; never touches a DB. Covers spec FR-006 idempotency at the logic level.
- [X] T030 [P] [US3] Write `tests/integration/test_schema_live.py` marked `@pytest.mark.integration`: (a) introspects `information_schema.columns` for `chunk` and asserts the expected columns + nullability; (b) attempts an INSERT with a wrong-dim embedding (e.g., 512 floats) and asserts the error message names the dimension mismatch; (c) calls `migrations.run_pending` a second time and asserts the return value is unchanged and no `INSERT` happened on `schema_migrations`. Covers spec US3.1–US3.3 + SC-003.

### Implementation for User Story 3

- [X] T031 [US3] Write `migrations/0001_init_vector_store.sql` literally as the SQL shown in [data-model.md §"Migration: 0001_init_vector_store.sql — outline"](./data-model.md): `CREATE EXTENSION IF NOT EXISTS vector;` then the `source_document`, `chunk`, and `idx_chunk_source` definitions with every NOT NULL, CHECK, and the composite UNIQUE on chunk provenance fields.
- [X] T032 [P] [US3] Write `migrations/README.md` documenting (a) the runner algorithm from R-002, (b) how to author a new migration (filename convention `NNNN_short_description.sql`, SQL conventions, no down-migrations at boilerplate stage), (c) the `schema_migrations` bookkeeping table.

**Checkpoint**: Schema introspection matches [data-model.md](./data-model.md). Wrong-dim insert rejected. Second `run_pending` is a no-op. Acceptance scenarios US3.1, US3.2, US3.3 all green.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: User-facing artifacts and end-to-end validation. None of these block earlier phases, but every one is required for the feature to ship.

- [X] T033 [P] Write `README.md` at repo root satisfying spec FR-012: one-paragraph problem statement, prerequisites section (Docker, Gemini key), the literal `make up` command, the `http://localhost:8000/health` URL with an example response, a table of every `make` target with one-line descriptions, a "what's intentionally not here yet" section pulling from [quickstart.md](./quickstart.md). Constitution Art V.4 requires an architecture diagram — include a simple ASCII diagram of `app ↔ db` or a referenced PNG. Limitations section is honest (Art VIII.4) — name the deferred features explicitly.
- [X] T034 [P] Run `make lint` against the complete source tree; fix any ruff violations. Acceptance: exit code 0. (Spec SC-002.)
- [X] T035 [P] Run `make test` (unit tier) against the complete source tree; ensure all FR-009 tests pass. Acceptance: exit code 0, non-zero test count. (Spec FR-009.)
- [ ] T036 Run the full [quickstart.md](./quickstart.md) "First-run flow" in a fresh worktree (`git worktree add ../boilerplate-validation`): clone → `.env` → `make up` → `curl /health` → measure wall time. Acceptance: under 5 minutes from `git clone` to green `/health` (spec SC-001).
- [ ] T037 With the stack still up from T036, run `make down && make up` ten times consecutively; on each `up` capture the lifespan log and assert "pending migrations: 0" (or equivalent). Acceptance: SC-004 — zero schema re-applications, zero data loss.
- [ ] T038 Run `RUN_INTEGRATION=1 make test-integration` against the up stack from T036; assert both `test_health_live.py` and `test_schema_live.py` pass. Brief summary appended to the spec's checklist as evidence of US1 + US3 acceptance.
- [ ] T039 Verify FR-007 acceptance #3: `rag --help` and `make help` list identical command sets (capture both outputs, diff; differences are blockers). Fix any drift in T009 (Makefile) or T025 (`rag.cli.main`).

**Demo prep deferred**: Constitution Art VIII.5 (slide deck) and VIII.6 (30-min demo dry-run) are submission-time concerns that span the whole project, not the boilerplate feature. No artifact created here; these belong to the final composition pass before submission. See [plan.md Constitution Check](./plan.md#constitution-check), Art VIII row.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: no dependencies; can start immediately.
- **Phase 2 (Foundational)**: depends on Phase 1 — needs `pyproject.toml` to install deps for `pydantic-settings`.
- **Phase 3 (US1)**: depends on Phase 2 — needs `rag.config` and `rag.log` to wire the lifespan and the health endpoint.
- **Phase 4 (US2)**: depends on Phase 2 — needs `rag.log` for the stub log lines. Independent of Phase 3.
- **Phase 5 (US3)**: depends on Phase 3 — the lifespan that runs migrations is built in T020; the SQL file is consumed by it.
- **Phase 6 (Polish)**: depends on all prior phases.

### Story dependencies

- **US1 (P1)**: depends on Foundational only. Delivers the MVP — the stack stands up and `/health` is green.
- **US2 (P2)**: depends on Foundational only. **Independent of US1** — the CLI surface can be wired and stub-tested without the FastAPI app running. A team member can build US2 in parallel with US1.
- **US3 (P2)**: depends on US1 (the lifespan in T020 consumes the SQL file from T031). Sequential after US1.

### Parallel opportunities

- Phase 1: T005, T006, T007, T008, T009 all parallelizable after T001 (different files, no shared edits).
- Phase 2: T012 and T013 parallelizable after T011 (different files).
- Phase 3 tests: T014, T015, T016 parallelizable (different files); T017 sequential after T016 (same integration concept, kept ordered).
- Phase 3 implementation: T018 and T019 parallelizable; T020 sequential after both; T021 sequential after T020; T022 same file as T021 (sequential).
- Phase 4: T024, T026, T027, T028 parallelizable after T025 (different files); T023 parallel with T026/T027/T028 (independent test file).
- Phase 5: T029 and T030 parallelizable (different files); T031 and T032 parallelizable (different files).
- Phase 6: T033, T034, T035 parallelizable (different artifacts); T036, T037, T038, T039 sequential against the live stack.

---

## Parallel Example: User Story 1

```bash
# After T013 (foundational), launch tests for US1 together:
Task: "Write tests/conftest.py per T014"
Task: "Write tests/unit/test_config.py per T015"
Task: "Write tests/unit/test_health.py per T016"

# After T013, launch the two leaf implementation modules together:
Task: "Implement src/rag/db.py per T018"
Task: "Implement src/rag/migrations.py per T019"

# Then T020 (lifespan) gates everything else in US1 — sequential.
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Complete Phase 1 (Setup) — repo scaffolding.
2. Complete Phase 2 (Foundational) — config + logging.
3. Complete Phase 3 (US1) — stack stands up, `/health` green.
4. **STOP and validate**: run the quickstart flow against the MVP. This is already a demo-able artifact — the reviewer can see a healthy stack.

### Incremental delivery

1. Setup + Foundational → green build.
2. + US1 → MVP. Demo: `make up` + `curl /health`.
3. + US2 → CLI surface lands. Demo: `rag --help`, stubs exit 2 with the right messages.
4. + US3 → schema is reviewable. Demo: `psql` introspection of `chunk` table.
5. Polish (Phase 6) → ship-ready: README, lint, tests, restart-preservation evidence.

### Parallel team strategy

With more than one developer:

1. Phase 1 + Phase 2 done together (mostly mechanical).
2. After T013:
   - Developer A: US1 (Phase 3).
   - Developer B: US2 (Phase 4) — independent.
3. US3 (Phase 5) starts when US1's T020 lands.
4. Phase 6 done by whoever finishes their story first; the README needs all stories landed before final.

---

## Notes

- `[P]` tasks: different files, no in-phase dependency on incomplete work.
- `[Story]` label maps a task to one of US1/US2/US3 for traceability.
- Tests are written before the implementation in each story per the standard TDD ordering (and per the FR-009 acceptance contract).
- Commit after each task or each related cluster — the constitution Art VIII.2 expects narratable history.
- Phase 6 is not optional; in particular, T036–T039 are the evidence that SC-001, SC-002, SC-003, SC-004 are met.
- Avoid: editing `pyproject.toml` in parallel branches (T002/T003/T004 are deliberately sequential), editing the Makefile in parallel branches.
