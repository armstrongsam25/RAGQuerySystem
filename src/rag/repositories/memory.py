"""In-memory :class:`ChunkRepository` for hermetic tests and the eval harness.

The ``connection`` kwarg on every method is accepted for API parity with
the pgvector implementation but is ignored — there is no real transaction
in the in-memory store. Tests that need transactional semantics use
pgvector via the integration tier.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from uuid import UUID, uuid4

from psycopg import AsyncConnection

from rag.repositories.base import ChunkRecord, RetrievedChunk, SourceDocumentInfo


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in pure Python (no numpy dependency at this layer)."""
    if len(a) != len(b):
        raise ValueError(f"vector dim mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryChunkRepository:
    """In-memory chunk repository — for tests + eval, never production."""

    def __init__(self) -> None:
        self._chunks: list[ChunkRecord] = []
        self._docs: dict[str, UUID] = {}  # file_hash -> id
        # Per-hash filename + timestamp for `list_source_documents`. Optional
        # and back-filled lazily — tests that pre-populate `_docs` directly
        # without going through `ensure_source_document` will just get
        # empty/placeholder metadata in the indicator, which is fine.
        self._doc_meta: dict[str, tuple[str, datetime]] = {}  # file_hash -> (filename, created_at)

    # ---- Mutators --------------------------------------------------------

    async def add_chunks(
        self,
        chunks: list[ChunkRecord],
        *,
        source_document_id: UUID,
        connection: AsyncConnection | None = None,
    ) -> int:
        del connection  # parity-only kwarg; in-memory has no transaction
        existing_keys = {
            (c.source_document_id, c.page_number, c.char_offset_start, c.char_offset_end)
            for c in self._chunks
        }
        inserted = 0
        for c in chunks:
            key = (
                source_document_id,
                c.page_number,
                c.char_offset_start,
                c.char_offset_end,
            )
            if key in existing_keys:
                continue
            # Reassign source_document_id in case the caller built the
            # record with a placeholder; matches the pgvector impl.
            c.source_document_id = source_document_id
            self._chunks.append(c)
            existing_keys.add(key)
            inserted += 1
        return inserted

    async def ensure_source_document(
        self,
        *,
        file_hash: str,
        display_filename: str,
        connection: AsyncConnection | None = None,
    ) -> tuple[UUID, bool]:
        del connection  # parity-only kwarg
        if file_hash in self._docs:
            return self._docs[file_hash], False
        new_id = uuid4()
        self._docs[file_hash] = new_id
        self._doc_meta[file_hash] = (display_filename, datetime.now(UTC))
        return new_id, True

    async def delete_source_document_by_hash(
        self,
        file_hash: str,
        *,
        connection: AsyncConnection | None = None,
    ) -> bool:
        del connection
        if file_hash not in self._docs:
            return False
        deleted_id = self._docs.pop(file_hash)
        self._doc_meta.pop(file_hash, None)
        self._chunks = [c for c in self._chunks if c.source_document_id != deleted_id]
        return True

    async def delete_all_source_documents(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> int:
        del connection
        count = len(self._docs)
        self._docs.clear()
        self._doc_meta.clear()
        self._chunks.clear()
        return count

    # ---- Readers ---------------------------------------------------------

    async def search(
        self,
        query_embedding: list[float],
        *,
        k: int,
        sim_floor: float,
        connection: AsyncConnection | None = None,
    ) -> list[RetrievedChunk]:
        del connection
        scored: list[RetrievedChunk] = []
        for c in self._chunks:
            if c.embedding is None:
                continue
            sim = _cosine(query_embedding, c.embedding)
            if sim < sim_floor:
                continue
            scored.append(RetrievedChunk(record=c, similarity=sim))
        scored.sort(key=lambda r: r.similarity, reverse=True)
        return scored[:k]

    async def get_by_id(
        self,
        chunk_id: UUID,
        *,
        connection: AsyncConnection | None = None,
    ) -> ChunkRecord | None:
        del connection
        for c in self._chunks:
            if c.id == chunk_id:
                return c
        return None

    async def has_any_chunks(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> bool:
        del connection
        return len(self._chunks) > 0

    async def count_source_documents(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> int:
        del connection
        return len(self._docs)

    async def list_source_documents(
        self,
        *,
        connection: AsyncConnection | None = None,
    ) -> list[SourceDocumentInfo]:
        del connection
        infos: list[SourceDocumentInfo] = []
        for file_hash, doc_id in self._docs.items():
            filename, created_at = self._doc_meta.get(file_hash, (file_hash, datetime.now(UTC)))
            chunks_for_doc = [c for c in self._chunks if c.source_document_id == doc_id]
            chunk_count = len(chunks_for_doc)
            page_count = max((c.page_number for c in chunks_for_doc), default=0)
            infos.append(
                SourceDocumentInfo(
                    id=doc_id,
                    display_filename=filename,
                    file_hash=file_hash,
                    chunk_count=chunk_count,
                    page_count=page_count,
                    created_at=created_at,
                )
            )
        infos.sort(key=lambda i: i.created_at, reverse=True)
        return infos
