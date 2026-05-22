"""Ingest orchestrator.

Two public entry points:

- :func:`ingest_pdf` — path-based. Reads bytes from disk and delegates to
  :func:`ingest_pdf_core`. The historical CLI entry point.
- :func:`ingest_pdf_core` — bytes-based. Accepts an optional caller-owned
  connection so the upload route (feature 003) can wrap clear-then-ingest
  in a single transaction.

Steps (spec FR-001 → FR-006):
    1. read bytes (path wrapper) or accept them (core)
    2. sha256 → file_hash
    3. ensure_source_document(file_hash, display_filename)
       -> if not created, short-circuit "already ingested"
    4. enumerate_pages + extract pages via provider
    5. chunk_pages
    6. provider.embed in RAG_EMBED_BATCH-sized batches
    7. repo.add_chunks
    8. emit ingest_complete log
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from psycopg import AsyncConnection

from rag.config import Settings
from rag.ingest.chunker import chunk_pages
from rag.ingest.pdf import extract_pages
from rag.log import get_logger
from rag.providers.base import LLMProvider
from rag.repositories.base import ChunkRepository
from rag.trace import TRACE_LOG_KEY

logger = get_logger(__name__)

IngestStatus = Literal["ingested", "already_done", "reingested"]

CancelCheck = Callable[[], Awaitable[bool]]
ProgressCallback = Callable[[str, str], Awaitable[None]]


class UploadCancelledError(Exception):
    """Raised when an ingest run is aborted via the cancel-check callback."""

    def __init__(self, *, phase: str) -> None:
        self.phase = phase
        super().__init__(f"upload cancelled at phase={phase}")


@dataclass(frozen=True)
class IngestOutcome:
    status: IngestStatus
    source_document_id: UUID
    file_hash: str
    pages: int
    chunks_inserted: int
    elapsed_s: float


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _check_cancelled(
    cancel_check: CancelCheck | None,
    phase: str,
    trace_id: str,
) -> None:
    if cancel_check is None:
        return
    if await cancel_check():
        logger.info(
            "ingest_cancelled",
            extra={TRACE_LOG_KEY: trace_id, "phase": phase},
        )
        raise UploadCancelledError(phase=phase)


async def _emit_progress(
    callback: ProgressCallback | None,
    stage: str,
    message: str,
) -> None:
    if callback is not None:
        await callback(stage, message)


async def ingest_pdf_core(
    *,
    pdf_bytes: bytes,
    display_filename: str,
    gemini: LLMProvider,
    repo: ChunkRepository,
    settings: Settings,
    trace_id: str,
    force: bool = False,
    connection: AsyncConnection | None = None,
    cancel_check: CancelCheck | None = None,
    progress_callback: ProgressCallback | None = None,
) -> IngestOutcome:
    """Run the ingest pipeline against in-memory PDF bytes.

    ``gemini``: named for backward compatibility with older call sites
    but accepts any :class:`LLMProvider` (GeminiProvider, OpenAIProvider, etc.).
    """
    started = time.perf_counter()

    if not pdf_bytes:
        raise ValueError(f"PDF bytes are empty: {display_filename}")
    file_hash = _sha256_hex(pdf_bytes)

    logger.info(
        "ingest_started",
        extra={
            TRACE_LOG_KEY: trace_id,
            "display_filename": display_filename,
            "size_bytes": len(pdf_bytes),
            "force": force,
        },
    )
    logger.info(
        "file_hash_computed",
        extra={TRACE_LOG_KEY: trace_id, "file_hash": file_hash},
    )

    overwrote_existing = False
    if force:
        overwrote_existing = await repo.delete_source_document_by_hash(
            file_hash,
            connection=connection,
        )
        if overwrote_existing:
            logger.info(
                "ingest_force_purged_existing",
                extra={TRACE_LOG_KEY: trace_id, "file_hash": file_hash},
            )

    source_id, created = await repo.ensure_source_document(
        file_hash=file_hash,
        display_filename=display_filename,
        connection=connection,
    )
    if not created:
        elapsed = time.perf_counter() - started
        logger.info(
            "ingest_already_done",
            extra={
                TRACE_LOG_KEY: trace_id,
                "source_document_id": str(source_id),
                "file_hash": file_hash,
            },
        )
        return IngestOutcome(
            status="already_done",
            source_document_id=source_id,
            file_hash=file_hash,
            pages=0,
            chunks_inserted=0,
            elapsed_s=elapsed,
        )

    # Extract pages using whatever provider was passed.
    await _emit_progress(
        progress_callback,
        "extracting",
        "Extracting pages from PDF…",
    )
    pages = await extract_pages(
        pdf_bytes,
        provider=gemini,
        concurrency=settings.RAG_PROVIDER_CONCURRENCY,
    )
    logger.info(
        "pages_extracted",
        extra={
            TRACE_LOG_KEY: trace_id,
            "page_count": len(pages),
            "non_empty_pages": sum(1 for _, text in pages if text.strip()),
        },
    )
    await _emit_progress(
        progress_callback,
        "extracted",
        f"Extracted {len(pages)} page{'s' if len(pages) != 1 else ''}.",
    )
    await _check_cancelled(cancel_check, "after_extraction", trace_id)

    # Chunk.
    await _emit_progress(progress_callback, "chunking", "Splitting into chunks…")
    chunks = chunk_pages(pages)
    if not chunks:
        elapsed = time.perf_counter() - started
        logger.warning(
            "ingest_no_chunks",
            extra={TRACE_LOG_KEY: trace_id, "reason": "all pages were empty after extraction"},
        )
        return IngestOutcome(
            status="ingested",
            source_document_id=source_id,
            file_hash=file_hash,
            pages=len(pages),
            chunks_inserted=0,
            elapsed_s=elapsed,
        )

    # Embed in batches.
    batch_size = settings.RAG_EMBED_BATCH
    n_batches = max(1, math.ceil(len(chunks) / batch_size))
    for batch_idx, batch_start in enumerate(range(0, len(chunks), batch_size)):
        await _emit_progress(
            progress_callback,
            "embedding",
            f"Embedding chunks (batch {batch_idx + 1}/{n_batches})…",
        )
        batch = chunks[batch_start : batch_start + batch_size]
        texts = [c.raw_text for c in batch]
        embeddings = await gemini.embed(texts)
        for chunk, emb in zip(batch, embeddings, strict=True):
            if len(emb) != settings.EMBEDDING_DIM:
                raise RuntimeError(
                    f"embedding dim mismatch: got {len(emb)}, expected {settings.EMBEDDING_DIM}"
                )
            chunk.embedding = emb
        await _check_cancelled(cancel_check, "between_embedding_batches", trace_id)
    logger.info(
        "chunks_embedded",
        extra={
            TRACE_LOG_KEY: trace_id,
            "chunk_count": len(chunks),
            "model": settings.EMBEDDING_MODEL,
        },
    )

    await _check_cancelled(cancel_check, "before_persistence", trace_id)
    await _emit_progress(progress_callback, "persisting", "Saving to vector store…")

    inserted = await repo.add_chunks(
        chunks,
        source_document_id=source_id,
        connection=connection,
    )
    elapsed = time.perf_counter() - started
    final_status: IngestStatus = "reingested" if overwrote_existing else "ingested"
    logger.info(
        "ingest_complete",
        extra={
            TRACE_LOG_KEY: trace_id,
            "source_document_id": str(source_id),
            "pages": len(pages),
            "chunks_inserted": inserted,
            "elapsed_s": round(elapsed, 2),
            "status": final_status,
        },
    )
    return IngestOutcome(
        status=final_status,
        source_document_id=source_id,
        file_hash=file_hash,
        pages=len(pages),
        chunks_inserted=inserted,
        elapsed_s=elapsed,
    )


async def ingest_pdf(
    pdf_path: Path,
    *,
    gemini: LLMProvider,
    repo: ChunkRepository,
    settings: Settings,
    trace_id: str,
    force: bool = False,
) -> IngestOutcome:
    """Run the ingest pipeline against the file at ``pdf_path``.

    ``gemini``: named for backward compatibility but accepts any LLMProvider.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not pdf_path.is_file():
        raise ValueError(f"not a regular file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"not a PDF (expected .pdf extension): {pdf_path}")

    pdf_bytes = pdf_path.read_bytes()
    return await ingest_pdf_core(
        pdf_bytes=pdf_bytes,
        display_filename=pdf_path.name,
        gemini=gemini,
        repo=repo,
        settings=settings,
        trace_id=trace_id,
        force=force,
        connection=None,
        cancel_check=None,
    )