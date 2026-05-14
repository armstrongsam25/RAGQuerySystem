"""Repository Protocol + records for the chunk store.

Connection handling
-------------------
Every mutating / reading method accepts an optional
``connection: AsyncConnection | None = None`` keyword. When ``None`` (the
default), the method acquires its own connection from the pool and runs
in its own implicit transaction — the historical behavior used by the
CLI ingest path and the query path. When a connection is supplied (by
the upload route, feature 003), the method runs against that connection
so the caller can wrap multiple repository calls in a single
``async with conn.transaction():`` block. This is what makes feature 003's
strict-rollback replace flow atomic (data-model.md → Transactional
boundary).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from psycopg import AsyncConnection


@dataclass(frozen=True)
class SourceDocumentInfo:
    """Summary of one ingested PDF for the current-document indicator (feature 003 UI)."""

    id: UUID
    display_filename: str
    file_hash: str
    chunk_count: int
    page_count: int
    created_at: datetime


@dataclass
class ChunkRecord:
    """One row in the chunk table.

    `id` defaults to a fresh UUID v4 so ingest can compose records before
    insert without round-tripping to the DB. The chunk-level UNIQUE on
    (source_document_id, page_number, char_offset_start, char_offset_end)
    is what actually deduplicates re-ingests, so the in-memory id is fine.
    """

    source_document_id: UUID
    page_number: int
    char_offset_start: int
    char_offset_end: int
    raw_text: str
    token_count: int
    embedding: list[float] | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk returned by :meth:`ChunkRepository.search` with its similarity score."""

    record: ChunkRecord
    similarity: float


@runtime_checkable
class ChunkRepository(Protocol):
    """The persistence surface ingest and query depend on."""

    async def add_chunks(
        self,
        chunks: list[ChunkRecord],
        *,
        source_document_id: UUID,
        connection: AsyncConnection | None = None,
    ) -> int:
        """Insert chunks; on conflict, do nothing. Return rows actually inserted."""
        ...

    async def search(
        self,
        query_embedding: list[float],
        *,
        k: int,
        sim_floor: float,
        connection: AsyncConnection | None = None,
    ) -> list[RetrievedChunk]:
        """Top-k cosine-similarity search, filtered by sim_floor."""
        ...

    async def get_by_id(
        self,
        chunk_id: UUID,
        *,
        connection: AsyncConnection | None = None,
    ) -> ChunkRecord | None:
        """Lookup by primary key. None if the chunk doesn't exist."""
        ...

    async def has_any_chunks(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> bool:
        """True iff the corpus is non-empty. Used by the no-documents path."""
        ...

    async def count_source_documents(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> int:
        """Number of source_document rows currently in the corpus.

        Used by the upload route (feature 003) to decide whether to present
        the replace/append confirmation step (non-zero) or proceed directly
        (zero) per spec FR-008 / FR-011.
        """
        ...

    async def ensure_source_document(
        self,
        *,
        file_hash: str,
        display_filename: str,
        connection: AsyncConnection | None = None,
    ) -> tuple[UUID, bool]:
        """Insert-or-fetch a source_document by file_hash.

        Returns `(id, created)`. `created=False` means the file_hash already
        existed — caller should treat this as "already ingested" and short-
        circuit.
        """
        ...

    async def delete_source_document_by_hash(
        self,
        file_hash: str,
        *,
        connection: AsyncConnection | None = None,
    ) -> bool:
        """Delete a source_document by file_hash; CASCADE removes its chunks.

        Returns True if a row was deleted, False if no document with that
        hash existed. Used by `rag ingest --force` to clear prior state
        before re-ingesting the same file.
        """
        ...

    async def delete_all_source_documents(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> int:
        """Delete every source_document row; CASCADE removes every chunk.

        Used by the upload route's **replace** flow (feature 003 spec FR-016).
        Returns the count of source_documents removed.
        """
        ...

    async def list_source_documents(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> list[SourceDocumentInfo]:
        """Return summaries of every currently-ingested source document.

        Powers the feature-003 UI "currently ingested document" indicator
        on the home page. Each entry carries the filename plus per-document
        chunk and page counts so the indicator can render rich metadata.
        Ordered by ``created_at`` descending (most recent first).
        """
        ...
