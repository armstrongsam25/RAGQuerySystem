"""Database access layer.

* :func:`make_pool` builds the async connection pool.
* :func:`ping` runs a trivial round-trip query with a per-call timeout —
  the function the `/health` handler invokes (spec FR-002, clarification Q2).
* :func:`register_pgvector` registers pgvector's psycopg type adapters at
  pool-connection time so downstream features can pass `list[float]` /
  numpy arrays directly to `INSERT ... VALUES (%s)`.
"""

from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool


@runtime_checkable
class Pool(Protocol):
    """Minimal protocol so tests can swap in a fake without subclassing the
    real :class:`AsyncConnectionPool`.
    """

    async def open(self) -> None: ...
    async def close(self) -> None: ...
    def connection(self) -> object: ...  # async context manager


async def register_pgvector(conn: AsyncConnection) -> None:
    """psycopg `configure=` hook: register the pgvector type adapter."""
    await register_vector_async(conn)


def make_pool(dsn: str, *, min_size: int = 1, max_size: int = 4) -> AsyncConnectionPool:
    """Create (but do not open) an async connection pool.

    The pool is opened by the FastAPI lifespan; this function is a factory
    so tests can construct one without touching a real database.
    """
    return AsyncConnectionPool(
        conninfo=dsn,
        min_size=min_size,
        max_size=max_size,
        open=False,
        configure=register_pgvector,
    )


async def ping(pool: AsyncConnectionPool, *, timeout_s: float = 2.0) -> None:
    """Run `SELECT 1` with a hard timeout.

    Raises on failure or timeout. The caller (`/health`) converts the
    exception into a 503 response.
    """

    async def _run() -> None:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT 1")
            row = await cur.fetchone()
            if row is None or row[0] != 1:
                raise RuntimeError(f"unexpected ping response: {row!r}")

    await asyncio.wait_for(_run(), timeout=timeout_s)
