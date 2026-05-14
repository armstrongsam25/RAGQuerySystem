"""FastAPI lifespan: bring the app to a healthy state on startup.

Order of operations (carried forward from feature 001 + extended in
feature 002 to wire providers + repository onto ``app.state``):

    1. configure_logging
    2. wait_for_db
    3. run_pending migrations (now picks up migrations/0002_query_path.sql too)
    4. verify EMBEDDING_DIM matches the schema's `chunk.embedding` column
    5. open AsyncConnectionPool
    6. instantiate ChunkRepository + GeminiProvider and stash them on
       app.state for routes to depend on
    7. yield
    8. close the pool on shutdown
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI

from rag.config import Settings, get_settings
from rag.db import make_pool
from rag.log import configure_logging, get_logger
from rag.ui.upload_jobs import UploadJob
from rag.migrations import run_pending
from rag.providers import GeminiProvider, Providers
from rag.repositories import PgVectorChunkRepository

logger = get_logger(__name__)

# Project root contains a top-level `migrations/` directory. This file
# lives at <root>/src/rag/lifespan.py — two parents up.
_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _wait_for_db(dsn: str, *, retries: int = 5, delay_s: float = 2.0) -> None:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
            logger.info("db_reachable", extra={"attempt": attempt})
            return
        except psycopg.OperationalError as exc:
            last_exc = exc
            logger.warning(
                "db_not_ready",
                extra={"attempt": attempt, "retries": retries, "error": str(exc)},
            )
            time.sleep(delay_s)
    raise RuntimeError(
        f"database not reachable after {retries} attempts: {last_exc!s}"
    ) from last_exc


def _verify_embedding_dim(dsn: str, expected: int) -> None:
    sql = """
    SELECT a.atttypmod
      FROM pg_attribute a
      JOIN pg_class c ON c.oid = a.attrelid
     WHERE c.relname = 'chunk'
       AND a.attname = 'embedding'
       AND NOT a.attisdropped
    """
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()

    if row is None:
        raise RuntimeError(
            "schema check: chunk.embedding column not found; did migration 0001 fail to apply?"
        )
    actual = int(row[0])
    if actual != expected:
        raise RuntimeError(
            f"embedding dimension mismatch: env EMBEDDING_DIM={expected} "
            f"but chunk.embedding is vector({actual}). Re-run migrations "
            "or restore EMBEDDING_DIM to match the schema."
        )
    logger.info("embedding_dim_ok", extra={"dim": actual})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Wire startup → ready → shutdown."""
    settings: Settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    logger.info(
        "startup_begin",
        extra={
            "embedding_model": settings.EMBEDDING_MODEL,
            "generation_model": settings.GENERATION_MODEL,
            "embedding_dim": settings.EMBEDDING_DIM,
            "judge_model": settings.GROUNDING_JUDGE_MODEL,
        },
    )

    dsn = settings.database_dsn

    # Run sync I/O off the event loop so we don't block the ASGI worker.
    await asyncio.to_thread(_wait_for_db, dsn)
    schema_version = await asyncio.to_thread(run_pending, dsn, _MIGRATIONS_DIR)
    await asyncio.to_thread(_verify_embedding_dim, dsn, settings.EMBEDDING_DIM)

    pool = make_pool(dsn)
    await pool.open(wait=True, timeout=10)

    # PDF storage dir — created at startup so a read-only filesystem fails
    # loudly here instead of on the first upload's commit-then-write path.
    pdf_dir = settings.RAG_PDF_STORAGE_DIR
    pdf_dir.mkdir(parents=True, exist_ok=True)
    logger.info("pdf_storage_ready", extra={"path": str(pdf_dir.resolve())})

    # Feature 002 wiring: repository + providers behind clean abstractions.
    chunk_repo = PgVectorChunkRepository(pool)
    gemini = GeminiProvider(settings)
    providers = Providers(embedder=gemini, generator=gemini, judge=gemini)

    app.state.pool = pool
    app.state.schema_version = schema_version
    app.state.settings = settings
    app.state.chunk_repo = chunk_repo
    app.state.providers = providers
    # Process-wide upload guard (feature 003 spec FR-028 / R-003). One worker
    # per process today; a multi-worker deployment would need a Postgres
    # advisory lock instead — see quickstart.md "Future work" section.
    app.state.upload_lock = asyncio.Lock()
    # Background-task registry for the progress-pushing upload flow. Keys
    # are short-lived task_ids (one per upload). Cleared by the status
    # endpoint after returning a terminal partial.

    upload_jobs: dict[str, UploadJob] = {}
    app.state.upload_jobs = upload_jobs

    logger.info("startup_ready", extra={"schema_version": schema_version})
    try:
        yield
    finally:
        logger.info("shutdown_begin")
        await pool.close()
        logger.info("shutdown_complete")
