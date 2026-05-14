# Migrations

Versioned SQL migrations for the RAG boilerplate's vector store.

## How the runner works

The runner lives in [`src/rag/migrations.py`](../src/rag/migrations.py) and is invoked by the FastAPI lifespan on every app startup (clarification Q1 — migrations apply before `/health` reports healthy). Algorithm:

1. `CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())`.
2. List `migrations/[0-9]*.sql` lexically.
3. Query the already-applied filenames from `schema_migrations`.
4. For each pending file in order: open a transaction, execute the SQL, `INSERT` the filename, commit.
5. On any error: roll back and propagate — the lifespan refuses to bring the app up.

The runner is **idempotent**: step 4 is a no-op when every file is already recorded. Restarting the stack does not re-apply migrations (spec FR-006, SC-004).

## Authoring a new migration

1. Pick the next sequential number: `0002`, `0003`, …
2. Filename: `NNNN_short_description.sql` (lowercase, underscores). The runner sorts by filename.
3. SQL conventions:
   - Use `CREATE EXTENSION IF NOT EXISTS …` when activating extensions.
   - **Do not** wrap the migration in `BEGIN`/`COMMIT` — the runner opens a transaction for you, and nesting would silently disable rollback.
   - Avoid statements that cannot run in a transaction (`CREATE INDEX CONCURRENTLY`, `ALTER TYPE … ADD VALUE` in pg < 12). If you must use one, split the migration so the non-transactional statement is alone and amend the runner.
   - Keep migrations narrowly scoped — one logical change per file makes review and rollback (via a follow-up migration) tractable.
4. No down-migrations at this stage. If a migration needs to be undone, write a new forward migration that reverses the change. This matches the constitution's "boilerplate, not framework" stance.

## `schema_migrations` table

| Column | Type | Notes |
|---|---|---|
| `name` | `TEXT PRIMARY KEY` | Filename of the applied migration, e.g. `0001_init_vector_store.sql`. |
| `applied_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | Wall-clock time the migration committed. Surfaced in the `/health` response. |

The table is created lazily by the runner on first invocation, **not** by `0001_init_vector_store.sql` itself. This is deliberate: the runner needs to query the table before deciding whether to apply `0001`, so chicken-and-egg ordering forces `schema_migrations` into the runner code.

## Why hand-rolled instead of Alembic

See [research R-002](../specs/001-rag-boilerplate/research.md). Short version: one SQL file does not justify Alembic's metadata-driven ceremony, and a 50-line runner is more reviewable than `alembic.ini` + `env.py` + `versions/` for a tiny project.
