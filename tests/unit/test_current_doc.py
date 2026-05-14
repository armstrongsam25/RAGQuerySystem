"""Tests for the current-document indicator endpoint + Clear route.

Covers:
- ``GET /ui/current-doc`` on empty corpus → empty-state partial.
- ``GET /ui/current-doc`` on populated corpus → filename + metadata.
- ``POST /ui/clear`` wipes the corpus and re-renders the empty state.
- The Clear button's `hx-confirm` attribute is rendered so the user
  sees a native confirmation before the destructive POST fires.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api import create_app
from rag.repositories.base import ChunkRecord


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


def _seed_doc(repo, *, file_hash: str, filename: str, chunk_count: int, page_count: int):
    """Populate the in-memory repo with one source_document + its chunks."""
    doc_id = uuid4()
    # Go through ensure_source_document so _doc_meta picks up the filename
    # the same way the real ingest path does. We can't await here, so
    # populate the private dicts directly to keep this a sync helper.
    repo._docs[file_hash] = doc_id
    from datetime import datetime

    repo._doc_meta[file_hash] = (filename, datetime.now(UTC))
    for i in range(chunk_count):
        repo._chunks.append(
            ChunkRecord(
                source_document_id=doc_id,
                page_number=min(i + 1, page_count),
                char_offset_start=i * 100,
                char_offset_end=i * 100 + 50,
                raw_text=f"chunk {i}",
                token_count=10,
                embedding=[1.0, 0.0, 0.0],
            )
        )
    return doc_id


def _build_app(small_dim_settings, memory_repo, fake_upload_pool):
    from rag.providers.base import Providers

    providers = Providers(embedder=object(), generator=object(), judge=object())  # type: ignore[arg-type]
    return _make_app(small_dim_settings, memory_repo, providers, fake_upload_pool)


def test_get_current_doc_empty_corpus_renders_empty_state(
    small_dim_settings, memory_repo, fake_upload_pool
):
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)
    with TestClient(app) as client:
        r = client.get("/ui/current-doc")
    assert r.status_code == 200
    assert "No document ingested yet" in r.text
    assert "current-doc-empty" in r.text
    # No card rendered.
    assert "current-doc-card" not in r.text


def test_get_current_doc_populated_renders_filename_and_metadata(
    small_dim_settings, memory_repo, fake_upload_pool
):
    _seed_doc(memory_repo, file_hash="h1", filename="report.pdf", chunk_count=15, page_count=8)
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)
    with TestClient(app) as client:
        r = client.get("/ui/current-doc")
    assert r.status_code == 200
    assert "report.pdf" in r.text
    assert "15 chunks" in r.text
    assert "8 pages" in r.text
    assert "current-doc-card" in r.text
    # Clear button + native confirm.
    assert 'hx-post="/ui/clear"' in r.text
    assert "hx-confirm=" in r.text


def test_post_clear_wipes_and_returns_empty_state(
    small_dim_settings, memory_repo, fake_upload_pool
):
    _seed_doc(memory_repo, file_hash="h1", filename="report.pdf", chunk_count=3, page_count=2)
    assert len(memory_repo._docs) == 1  # pre-condition

    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)
    with TestClient(app) as client:
        r = client.post("/ui/clear")
    assert r.status_code == 200
    assert "No document ingested yet" in r.text
    # Corpus is empty after wipe.
    assert len(memory_repo._docs) == 0
    assert len(memory_repo._chunks) == 0


def test_post_clear_on_already_empty_is_idempotent(
    small_dim_settings, memory_repo, fake_upload_pool
):
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)
    with TestClient(app) as client:
        r = client.post("/ui/clear")
    assert r.status_code == 200
    assert "No document ingested yet" in r.text
    assert len(memory_repo._docs) == 0


def test_get_current_doc_singular_vs_plural_units(
    small_dim_settings, memory_repo, fake_upload_pool
):
    """Cosmetic: '1 chunk' (singular) vs '2 chunks' (plural) for chunk_count == 1."""
    _seed_doc(memory_repo, file_hash="h1", filename="one-pager.pdf", chunk_count=1, page_count=1)
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)
    with TestClient(app) as client:
        r = client.get("/ui/current-doc")
    assert "1 chunk" in r.text
    assert "1 chunks" not in r.text  # no plural-s when count == 1
    assert "1 page" in r.text
    assert "1 pages" not in r.text
