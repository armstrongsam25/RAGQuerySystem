"""Versioned SQL migration runner (research R-002).

Algorithm:
  1. Ensure `schema_migrations` exists.
  2. List `migrations/*.sql` lexically; query already-applied names.
  3. For each unapplied file in order: open a transaction, run the SQL,
     INSERT the filename, commit. Any error rolls back and propagates;
     the lifespan will catch it and refuse to bring the app up.

Idempotent: step 3 is empty when everything is applied. Migration files
are plain SQL — no Python templating — so the schema is reviewable as
static text.
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

logger = logging.getLogger(__name__)

_SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    name        TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def list_available(migrations_dir: Path) -> list[Path]:
    """Return migration files sorted lexically by filename."""
    return sorted(migrations_dir.glob("[0-9]*.sql"), key=lambda p: p.name)


def applied(conn: psycopg.Connection) -> set[str]:
    """Return the set of migration filenames already recorded."""
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def pending(applied_names: set[str], available: list[Path]) -> list[Path]:
    """Pure-function diff: what's on disk but not yet recorded."""
    return [p for p in available if p.name not in applied_names]


def apply(conn: psycopg.Connection, path: Path) -> None:
    """Apply a single migration in its own transaction."""
    sql = path.read_text(encoding="utf-8")
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO schema_migrations (name) VALUES (%s)",
            (path.name,),
        )


def run_pending(dsn: str, migrations_dir: Path) -> str:
    """Apply every pending migration; return the most-recent applied name.

    Creates `schema_migrations` if needed. Connection is opened in
    autocommit=False mode (psycopg default) so the per-migration
    transaction is real.
    """
    available = list_available(migrations_dir)
    if not available:
        raise RuntimeError(f"no migrations found under {migrations_dir!s}")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_MIGRATIONS_DDL)
        conn.commit()

        already = applied(conn)
        todo = pending(already, available)

        logger.info(
            "migrations_scan",
            extra={
                "available": [p.name for p in available],
                "applied": sorted(already),
                "pending": [p.name for p in todo],
            },
        )

        for path in todo:
            logger.info("migration_apply_begin", extra={"migration": path.name})
            apply(conn, path)
            logger.info("migration_apply_ok", extra={"migration": path.name})

    return available[-1].name
