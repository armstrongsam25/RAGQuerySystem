"""FastAPI lifespan: bring the app to a healthy state on startup."""

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
from rag.migrations import run_pending
from rag.providers import LocalEmbeddingProvider, LocalEmbeddingProviderEmbedder, OpenAIProvider, Providers
from rag.repositories import PgVectorChunkRepository
from rag.ui.upload_jobs import UploadJob

logger = get_logger(__name__)

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
            "base_url": settings.LLM_BASE_URL,
            "embedding_model": settings.EMBEDDING_MODEL,
            "generation_model": settings.GENERATION_MODEL,
            "embedding_dim": settings.EMBEDDING_DIM,
            "judge_model": settings.GROUNDING_JUDGE_MODEL,
        },
    )

    dsn = settings.database_dsn

    await asyncio.to_thread(_wait_for_db, dsn)
    schema_version = await asyncio.to_thread(run_pending, dsn, _MIGRATIONS_DIR)
    await asyncio.to_thread(_verify_embedding_dim, dsn, settings.EMBEDDING_DIM)

    pool = make_pool(dsn)
    await pool.open(wait=True, timeout=10)

    pdf_dir = settings.RAG_PDF_STORAGE_DIR
    pdf_dir.mkdir(parents=True, exist_ok=True)
    logger.info("pdf_storage_ready", extra={"path": str(pdf_dir.resolve())})

    chunk_repo = PgVectorChunkRepository(pool)
    # Embedding: local CPU model (no API key needed)
    local_embed = LocalEmbeddingProvider(settings)
    embedder = LocalEmbeddingProviderEmbedder(local_embed)
    # Generation + judge: vLLM / OpenAI-compatible API
    llm = OpenAIProvider(settings)
    providers = Providers(embedder=embedder, generator=llm, judge=llm)

    app.state.pool = pool
    app.state.schema_version = schema_version
    app.state.settings = settings
    app.state.chunk_repo = chunk_repo
    app.state.providers = providers
    app.state.upload_lock = asyncio.Lock()

    upload_jobs: dict[str, UploadJob] = {}
    app.state.upload_jobs = upload_jobs

    logger.info("startup_ready", extra={"schema_version": schema_version})
    try:
        yield
    finally:
        logger.info("shutdown_begin")
        await pool.close()
        logger.info("shutdown_complete")