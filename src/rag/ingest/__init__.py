"""PDF ingestion pipeline.

Page-by-page extraction (per research R-010) → page-bounded recursive
character splitting (R-011) → batched embedding → idempotent persistence.

Feature 003 added :func:`ingest_pdf_core` (bytes-based, transaction-aware,
cancellation-aware) for the upload route, and the
:class:`UploadCancelledError` signal used by the cancel-check pathway.
``ingest_pdf`` (path-based) remains the CLI entry point and is unchanged
in behavior.
"""

from rag.ingest.pipeline import (
    IngestOutcome,
    UploadCancelledError,
    ingest_pdf,
    ingest_pdf_core,
)

__all__ = [
    "IngestOutcome",
    "UploadCancelledError",
    "ingest_pdf",
    "ingest_pdf_core",
]
