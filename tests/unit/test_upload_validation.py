"""Cross-cutting validation tests for the upload route (FR-014, FR-015).

Covers:
- Non-PDF file rejected at the magic-header boundary (FR-014).
- Oversize upload rejected with the cap surfaced in MB (FR-015).
- Missing pdf field handled by FastAPI's validation layer (HTTP 422).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api import create_app


def _make_app(settings, repo, providers, pool) -> FastAPI:
    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.chunk_repo = repo
        app.state.providers = providers
        app.state.pool = pool
        app.state.schema_version = "0002_query_path.sql"
        app.state.upload_lock = asyncio.Lock()
        app.state.upload_jobs = {}
        yield

    return create_app(lifespan=_noop_lifespan)


@pytest.fixture
def validation_app(small_dim_settings, memory_repo, fake_upload_pool):
    from rag.providers.base import Providers

    providers = Providers(embedder=object(), generator=object(), judge=object())  # type: ignore[arg-type]
    return _make_app(small_dim_settings, memory_repo, providers, fake_upload_pool), memory_repo


def test_non_pdf_file_rejected_with_invalid_pdf_cause(validation_app):
    app, repo = validation_app
    pre_doc_count = len(repo._docs)

    with TestClient(app) as client:
        # A text file masquerading as PDF — bytes that do NOT start with %PDF-.
        r = client.post(
            "/ui/upload",
            files={"pdf": ("not-a-pdf.pdf", b"This is plain text, not a PDF.", "application/pdf")},
        )
    assert r.status_code == 400
    # Feature 004 (clarify 2026-05-13): visible copy is category-coded, not
    # the raw cause string. The "invalid_pdf" key stays in the log trail.
    assert "Invalid input" in r.text
    assert "PDF magic header" not in r.text  # raw backend text MUST NOT leak
    # SC-004: corpus row counts unchanged after rejection.
    assert len(repo._docs) == pre_doc_count


def test_oversize_file_rejected_with_cap_in_message(
    small_dim_settings, memory_repo, fake_upload_pool, minimal_pdf_bytes
):
    """FR-015: cap exceeded → HTTP 413 + reviewer-readable cap in bytes AND MB."""
    from rag.providers.base import Providers

    # Tight cap so the minimal PDF (~70 bytes) exceeds it.
    tight_settings = small_dim_settings.model_copy(update={"RAG_MAX_UPLOAD_BYTES": 10})
    providers = Providers(embedder=object(), generator=object(), judge=object())  # type: ignore[arg-type]
    app = _make_app(tight_settings, memory_repo, providers, fake_upload_pool)
    pre_doc_count = len(memory_repo._docs)

    with TestClient(app) as client:
        r = client.post(
            "/ui/upload",
            files={"pdf": ("big.pdf", minimal_pdf_bytes, "application/pdf")},
        )
    assert r.status_code == 413
    # Feature 004 (clarify 2026-05-13): visible copy is category-coded.
    # Cap-bytes details remain in the log trail only.
    assert "Invalid input" in r.text
    assert "Max size:" not in r.text
    assert "RAG_MAX_UPLOAD_BYTES" not in r.text
    assert len(memory_repo._docs) == pre_doc_count


def test_missing_pdf_field_returns_422(validation_app):
    """FastAPI's framework-level validation handles a missing file field."""
    app, _repo = validation_app
    with TestClient(app) as client:
        r = client.post("/ui/upload")
    assert r.status_code == 422
