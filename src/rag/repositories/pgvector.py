"""pgvector-backed :class:`ChunkRepository`.

Per research R-013 (feature 002), the cosine pre-filter is applied **in
Python after the SQL LIMIT** so the HNSW index stays in play. A WHERE on
a computed expression would force a sequential scan; that defeats the
purpose of the index.

Connection handling (feature 003)
---------------------------------
Each public method accepts ``connection: AsyncConnection | None`` and
routes through :meth:`_acquire`. When ``connection`` is ``None`` the
method acquires its own connection from the pool (the historical, single-
statement-per-call behavior). When supplied, the method runs against the
caller's connection — this is what lets the upload route wrap clear-then-
ingest in a single transaction (data-model.md → Transactional boundary).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from pgvector import Vector
from psycopg import AsyncConnection
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from rag.repositories.base import ChunkRecord, RetrievedChunk, SourceDocumentInfo


async def _ensure_vector_registered(conn: AsyncConnection) -> None:
    """Register pgvector type adapters on *conn* if not already done."""
    from pgvector.psycopg import register_vector_async

    await register_vector_async(conn)


class PgVectorChunkRepository:
    """Production chunk repository using pgvector + psycopg async pool."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    @asynccontextmanager
    async def _acquire(
        self,
        connection: AsyncConnection | None,
    ) -> AsyncIterator[AsyncConnection]:
        """Yield a usable connection with pgvector adapters registered.

        If the caller passed one, use it as-is (no enter/exit on the pool).
        Otherwise borrow one from the pool for the duration of the block.
        Registers pgvector type adapters on the connection so Vector
        values can be passed to SQL placeholders.
        """
        if connection is not None:
            await _ensure_vector_registered(connection)
            yield connection
        else:
            async with self._pool.connection() as conn:
                await _ensure_vector_registered(conn)
                yield conn

    async def add_chunks(
        self,
        chunks: list[ChunkRecord],
        *,
        source_document_id: UUID,
        connection: AsyncConnection | None = None,
    ) -> int:
        if not chunks:
            return 0

        rows = [
            (
                c.id,
                source_document_id,
                c.page_number,
                c.char_offset_start,
                c.char_offset_end,
                c.raw_text,
                c.token_count,
                Vector(c.embedding) if c.embedding is not None else None,
            )
            for c in chunks
        ]

        async with self._acquire(connection) as conn, conn.cursor() as cur:
            inserted = 0
            for row in rows:
                # Per-row insert with ON CONFLICT DO NOTHING is simpler than
                # executemany + RETURNING for counting. Volume is small —
                # tens of chunks per page, hundreds per typical PDF.
                await cur.execute(
                    """
                    INSERT INTO chunk (
                        id, source_document_id, page_number,
                        char_offset_start, char_offset_end, raw_text,
                        token_count, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_document_id, page_number,
                                 char_offset_start, char_offset_end)
                    DO NOTHING
                    """,
                    row,
                )
                inserted += cur.rowcount or 0
            return inserted

    async def search(
        self,
        query_embedding: list[float],
        *,
        k: int,
        sim_floor: float,
        connection: AsyncConnection | None = None,
    ) -> list[RetrievedChunk]:
        qvec = Vector(query_embedding)
        async with (
            self._acquire(connection) as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            # `<=>` is pgvector's cosine-distance operator (0 = identical).
            # cosine_similarity = 1 - cosine_distance.
            await cur.execute(
                """
                SELECT id, source_document_id, page_number,
                       char_offset_start, char_offset_end, raw_text,
                       token_count, embedding,
                       1 - (embedding <=> %s) AS similarity
                  FROM chunk
                 WHERE embedding IS NOT NULL
                 ORDER BY embedding <=> %s
                 LIMIT %s
                """,
                (qvec, qvec, k),
            )
            rows = await cur.fetchall()

        results: list[RetrievedChunk] = []
        for row in rows:
            sim = float(row["similarity"])
            if sim < sim_floor:
                continue
            embedding_val = row["embedding"]
            if embedding_val is not None and not isinstance(embedding_val, list):
                # pgvector returns a numpy array via its psycopg adapter;
                # normalize to list[float] for the ChunkRecord shape.
                embedding_val = list(embedding_val)
            results.append(
                RetrievedChunk(
                    record=ChunkRecord(
                        id=row["id"],
                        source_document_id=row["source_document_id"],
                        page_number=row["page_number"],
                        char_offset_start=row["char_offset_start"],
                        char_offset_end=row["char_offset_end"],
                        raw_text=row["raw_text"],
                        token_count=row["token_count"] or 0,
                        embedding=embedding_val,
                    ),
                    similarity=sim,
                )
            )
        return results

    async def get_by_id(
        self,
        chunk_id: UUID,
        *,
        connection: AsyncConnection | None = None,
    ) -> ChunkRecord | None:
        async with (
            self._acquire(connection) as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            await cur.execute(
                """
                SELECT id, source_document_id, page_number,
                       char_offset_start, char_offset_end, raw_text,
                       token_count, embedding
                  FROM chunk
                 WHERE id = %s
                """,
                (chunk_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        embedding_val = row["embedding"]
        if embedding_val is not None and not isinstance(embedding_val, list):
            embedding_val = list(embedding_val)
        return ChunkRecord(
            id=row["id"],
            source_document_id=row["source_document_id"],
            page_number=row["page_number"],
            char_offset_start=row["char_offset_start"],
            char_offset_end=row["char_offset_end"],
            raw_text=row["raw_text"],
            token_count=row["token_count"] or 0,
            embedding=embedding_val,
        )

    async def has_any_chunks(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> bool:
        async with self._acquire(connection) as conn, conn.cursor() as cur:
            await cur.execute("SELECT 1 FROM chunk LIMIT 1")
            row = await cur.fetchone()
        return row is not None

    async def count_source_documents(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> int:
        async with self._acquire(connection) as conn, conn.cursor() as cur:
            await cur.execute("SELECT count(*) FROM source_document")
            row = await cur.fetchone()
        return int(row[0]) if row is not None else 0

    async def ensure_source_document(
        self,
        *,
        file_hash: str,
        display_filename: str,
        connection: AsyncConnection | None = None,
    ) -> tuple[UUID, bool]:
        # If the caller supplied a connection (transaction), do NOT roll it
        # back on UniqueViolation — that would discard the caller's other
        # work in the same transaction. Use a SAVEPOINT instead so we can
        # cleanly recover from the unique conflict without affecting the
        # outer transaction state.
        async with self._acquire(connection) as conn, conn.cursor() as cur:
            if connection is not None:
                async with conn.transaction():
                    try:
                        await cur.execute(
                            """
                            INSERT INTO source_document (display_filename, file_hash)
                            VALUES (%s, %s)
                            RETURNING id
                            """,
                            (display_filename, file_hash),
                        )
                        row = await cur.fetchone()
                        assert row is not None
                        return row[0], True
                    except UniqueViolation:
                        # The savepoint will be rolled back by the inner
                        # transaction context; re-raise a sentinel so the
                        # outer logic can do the lookup below.
                        pass
                # Outside the inner savepoint: look up the existing row.
                await cur.execute(
                    "SELECT id FROM source_document WHERE file_hash = %s",
                    (file_hash,),
                )
                row = await cur.fetchone()
                if row is None:
                    raise RuntimeError(
                        "ensure_source_document: unique violation but no row "
                        f"with file_hash={file_hash!r} could be found",
                    )
                return row[0], False
            else:
                # Pool-owned connection: legacy path with explicit rollback.
                try:
                    await cur.execute(
                        """
                        INSERT INTO source_document (display_filename, file_hash)
                        VALUES (%s, %s)
                        RETURNING id
                        """,
                        (display_filename, file_hash),
                    )
                    row = await cur.fetchone()
                    assert row is not None
                    return row[0], True
                except UniqueViolation:
                    await conn.rollback()
                    await cur.execute(
                        "SELECT id FROM source_document WHERE file_hash = %s",
                        (file_hash,),
                    )
                    row = await cur.fetchone()
                    if row is None:
                        raise
                    return row[0], False

    async def delete_source_document_by_hash(
        self,
        file_hash: str,
        *,
        connection: AsyncConnection | None = None,
    ) -> bool:
        async with self._acquire(connection) as conn, conn.cursor() as cur:
            # chunk rows are removed by ON DELETE CASCADE on the FK
            # (migration 0001 set this up).
            await cur.execute(
                "DELETE FROM source_document WHERE file_hash = %s",
                (file_hash,),
            )
            return (cur.rowcount or 0) > 0

    async def delete_all_source_documents(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> int:
        async with self._acquire(connection) as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM source_document")
            return cur.rowcount or 0

    async def list_source_documents(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> list[SourceDocumentInfo]:
        async with (
            self._acquire(connection) as conn,
            conn.cursor(row_factory=dict_row) as cur,
        ):
            # Outer join + GROUP BY so a source_document with zero chunks
            # (transient state during an in-flight ingest) still appears
            # with count=0. The chunk-level page_count uses MAX(page_number)
            # — since chunks are page-bounded (feature 002 chunker), this
            # matches the actual page count of the extracted PDF.
            await cur.execute(
                """
                SELECT s.id,
                       s.display_filename,
                       s.file_hash,
                       s.created_at,
                       coalesce(c.chunk_count, 0) AS chunk_count,
                       coalesce(c.page_count, 0) AS page_count
                  FROM source_document s
                  LEFT JOIN (
                       SELECT source_document_id,
                              count(*)         AS chunk_count,
                              max(page_number) AS page_count
                         FROM chunk
                         GROUP BY source_document_id
                  ) c ON c.source_document_id = s.id
                 ORDER BY s.created_at DESC
                """
            )
            rows = await cur.fetchall()
        return [
            SourceDocumentInfo(
                id=row["id"],
                display_filename=row["display_filename"],
                file_hash=row["file_hash"],
                chunk_count=int(row["chunk_count"]),
                page_count=int(row["page_count"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]
