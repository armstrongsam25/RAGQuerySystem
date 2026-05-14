"""Live schema test against a running `make up` stack (spec US3).

Gated by ``RUN_INTEGRATION=1``. Verifies:
  (a) `chunk` table columns and nullability match data-model.md;
  (b) inserting a wrong-dim embedding is rejected by pgvector;
  (c) re-running ``migrations.run_pending`` is a no-op.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.integration


def _dsn() -> str:
    """DSN for the host-side connection to the running `db` service.

    Defaults to localhost:5432 — adjust via ``DATABASE_URL_HOST`` if the
    compose file binds a different port.
    """
    return os.environ.get(
        "DATABASE_URL_HOST",
        "postgresql://rag:rag@localhost:5432/rag",
    )


_EXPECTED_COLUMNS = {
    "id": "NO",
    "source_document_id": "NO",
    "page_number": "NO",
    "char_offset_start": "NO",
    "char_offset_end": "NO",
    "raw_text": "NO",
    "embedding": "YES",  # nullable at boilerplate stage
    "created_at": "NO",
}


def test_chunk_schema_matches_data_model() -> None:
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, is_nullable
              FROM information_schema.columns
             WHERE table_name = 'chunk'
            """
        )
        actual = {name: nullable for name, nullable in cur.fetchall()}

    assert actual == _EXPECTED_COLUMNS, (
        f"chunk schema diverged from data-model.md\n  expected: {_EXPECTED_COLUMNS!r}\n  "
        f"actual:   {actual!r}"
    )


def test_wrong_dim_embedding_rejected() -> None:
    """Insert a 512-float vector into a vector(768) column — pgvector
    must reject it with an error naming the dimension."""
    with psycopg.connect(_dsn()) as conn:
        # Make sure we have a parent row to attach to.
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO source_document (display_filename) VALUES ('test.pdf') RETURNING id"
            )
            doc_id = cur.fetchone()[0]
        conn.commit()

        with conn.cursor() as cur:
            wrong = "[" + ",".join(["0.1"] * 512) + "]"
            with pytest.raises(psycopg.errors.DataException) as exc_info:
                cur.execute(
                    """
                    INSERT INTO chunk
                      (source_document_id, page_number,
                       char_offset_start, char_offset_end, raw_text, embedding)
                    VALUES (%s, 1, 0, 1, 'x', %s::vector)
                    """,
                    (doc_id, wrong),
                )
            assert (
                "expected" in str(exc_info.value).lower()
                or "dimension" in str(exc_info.value).lower()
            )
        conn.rollback()

        # Cleanup
        with conn.cursor() as cur:
            cur.execute("DELETE FROM source_document WHERE id = %s", (doc_id,))
        conn.commit()


def test_re_running_run_pending_is_noop() -> None:
    """Run the migration runner against the up stack twice. Second call MUST
    not change anything in `schema_migrations`.
    """
    from rag.migrations import run_pending

    repo_root = Path(__file__).resolve().parents[2]
    migrations_dir = repo_root / "migrations"
    dsn = _dsn()

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), max(applied_at) FROM schema_migrations")
        count_before, max_before = cur.fetchone()

    last_applied = run_pending(dsn, migrations_dir)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), max(applied_at) FROM schema_migrations")
        count_after, max_after = cur.fetchone()

    assert count_after == count_before, (
        f"row count changed: {count_before} -> {count_after}; runner is not idempotent"
    )
    assert max_after == max_before, "max(applied_at) changed; runner re-inserted a row"
    assert last_applied.endswith(".sql")
