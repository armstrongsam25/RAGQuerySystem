"""Persistence-layer abstraction for chunks.

Two implementations:
  * :class:`PgVectorChunkRepository` — production, pgvector-backed.
  * :class:`InMemoryChunkRepository` — hermetic tests + eval harness.

The Protocol shields the query and ingest pipelines from psycopg / pgvector
details; tests can swap in the in-memory implementation without standing up
a database (research R-013).
"""

from rag.repositories.base import (
    ChunkRecord,
    ChunkRepository,
    RetrievedChunk,
    SourceDocumentInfo,
)
from rag.repositories.memory import InMemoryChunkRepository
from rag.repositories.pgvector import PgVectorChunkRepository

__all__ = [
    "ChunkRecord",
    "ChunkRepository",
    "InMemoryChunkRepository",
    "PgVectorChunkRepository",
    "RetrievedChunk",
    "SourceDocumentInfo",
]
