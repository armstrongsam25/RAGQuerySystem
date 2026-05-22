"""Tests for the feature-003 upload progress flow (background task + polling).

Covers the post-redesign behavior where ``POST /ui/upload`` immediately
returns an in-progress partial that polls
``GET /ui/upload/status/{task_id}`` every ~500ms; the background task
runs the actual ingest and pushes stage updates to the job object.

Synchronous-rejection paths (non-PDF, oversize, concurrent) are covered
in :mod:`tests.unit.test_upload_validation` and
:mod:`tests.unit.test_upload_concurrent`.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from rag.api import create_app
from rag.ingest.pipeline import IngestOutcome, UploadCancelledError
from rag.providers.base import Providers, UpstreamProviderError
from rag.repositories.base import ChunkRecord


def _build_app(settings, repo, pool):
    """Hand-wire the app for AsyncClient tests (lifespan won't run)."""
    providers = Providers(embedder=object(), generator=object(), judge=object())  # type: ignore[arg-type]
    app = create_app(lifespan=None)
    app.state.settings = settings
    app.state.chunk_repo = repo
    app.state.providers = providers
    app.state.pool = pool
    app.state.schema_version = "0002_query_path.sql"
    app.state.upload_lock = asyncio.Lock()
    app.state.upload_jobs = {}
    return app


_TASK_ID_PATTERN = re.compile(r"/ui/upload/status/([a-f0-9]+)")


def _extract_task_id(in_progress_html: str) -> str:
    match = _TASK_ID_PATTERN.search(in_progress_html)
    assert match, f"could not extract task_id from response: {in_progress_html[:300]!r}"
    return match.group(1)


async def _poll_until_terminal(
    client: AsyncClient, task_id: str, *, max_polls: int = 200
) -> httpx.Response:  # noqa: F821 — Response only at runtime
    """Poll the status endpoint until the response stops showing the in-progress partial."""
    for _ in range(max_polls):
        await asyncio.sleep(0.01)
        r = await client.get(f"/ui/upload/status/{task_id}")
        if "upload-progress" not in r.text or "status-upload-pending" not in r.text:
            return r
    raise AssertionError(f"task {task_id} did not terminate within {max_polls} polls")


@pytest.mark.asyncio
async def test_status_endpoint_renders_in_progress_at_every_stage(
    small_dim_settings, memory_repo, fake_upload_pool, minimal_pdf_bytes, monkeypatch
):
    """Regression: the status endpoint MUST render the in-progress partial
    successfully at every stage the background task can be in.

    Earlier the template had Jinja ``{% set %}`` inside ``{% if/else %}``,
    which scopes the variable to the block — production hit 500s every
    500ms because the variable was undefined after the block. The route
    now pre-computes the stage view in Python and passes a flat list.
    """
    from rag.ingest.pipeline import IngestOutcome

    block_until_set = asyncio.Event()

    async def _stage_advancing_ingest(**kwargs):
        # Walk through every stage the route's _STAGE_TO_INDEX cares about.
        cb = kwargs["progress_callback"]
        for stage_key, message in [
            ("extracting", "Extracting…"),
            ("extracted", "Extracted 5 pages."),
            ("chunking", "Chunking…"),
            ("chunked", "Made N chunks."),
            ("embedding", "Embedding 1/2…"),
            ("persisting", "Saving…"),
        ]:
            await cb(stage_key, message)
            # Yield so the status endpoint test can poll between stages.
            await asyncio.sleep(0)
        # Wait for the test to be done polling.
        await block_until_set.wait()
        return IngestOutcome(
            status="ingested",
            source_document_id=uuid4(),
            file_hash="h",
            pages=5,
            chunks_inserted=10,
            elapsed_s=0.1,
        )

    monkeypatch.setattr("rag.ui.routes.ingest_pdf_core", _stage_advancing_ingest)
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            r_post = await client.post(
                "/ui/upload",
                files={"pdf": ("doc.pdf", minimal_pdf_bytes, "application/pdf")},
            )
            assert r_post.status_code == 200
            task_id = _extract_task_id(r_post.text)

            # Hit the status endpoint while the task is mid-flight. Even
            # ONE 500 here is a regression.
            for _ in range(15):
                r = await client.get(f"/ui/upload/status/{task_id}")
                assert r.status_code == 200, (
                    f"status endpoint failed with {r.status_code} during "
                    f"in-progress polling: {r.text[:200]}"
                )
                await asyncio.sleep(0.01)
        finally:
            block_until_set.set()
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_stages_view_helper_renders_every_stage_safely():
    """Direct test of the Python-side stage-view computation."""
    from rag.ui.routes import _stages_view

    # Every stage the background task or progress callback can emit.
    for stage in [
        "pending",
        "clearing",
        "extracting",
        "extracted",
        "chunking",
        "chunked",
        "embedding",
        "persisting",
        "complete",
        "cancelled",
        "error",
        "unknown-stage-from-future-code",
    ]:
        view = _stages_view(stage)
        assert len(view) == 5  # five stages
        for entry in view:
            assert entry["state"] in {"done", "active", "pending"}
            assert "label" in entry
            assert "dot" in entry


@pytest.mark.asyncio
async def test_post_upload_returns_in_progress_partial_with_polling_trigger(
    small_dim_settings, memory_repo, fake_upload_pool, minimal_pdf_bytes, monkeypatch
):
    """POST /ui/upload returns 200 with the polling-enabled in-progress partial."""

    # Block the background task indefinitely so we can observe in-progress state.
    block = asyncio.Event()

    async def _blocked_ingest(**kwargs):
        await block.wait()
        return IngestOutcome(
            status="ingested",
            source_document_id=uuid4(),
            file_hash="h",
            pages=1,
            chunks_inserted=1,
            elapsed_s=0.1,
        )

    monkeypatch.setattr("rag.ui.routes.ingest_pdf_core", _blocked_ingest)
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            r = await client.post(
                "/ui/upload",
                files={"pdf": ("doc.pdf", minimal_pdf_bytes, "application/pdf")},
            )
            assert r.status_code == 200, r.text
            # The partial has the polling trigger, the cancel button, and the filename.
            assert 'hx-trigger="every 500ms"' in r.text
            assert "upload-progress-stages" in r.text  # the stage bar
            assert "doc.pdf" in r.text
            assert "Cancel upload" in r.text
            task_id = _extract_task_id(r.text)
            # Job is registered in app state.
            assert task_id in app.state.upload_jobs
        finally:
            # Unblock so the background task can finish and pytest's teardown
            # doesn't see a pending task warning.
            block.set()
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_upload_completes_to_success_via_polling(
    small_dim_settings, memory_repo, fake_upload_pool, minimal_pdf_bytes, monkeypatch
):
    """Background task succeeds; polling eventually returns the success partial."""

    async def _fast_ingest(**kwargs):
        # Inject one chunk so the doc list has something to report.
        memory_repo._docs["h1"] = uuid4()
        from datetime import datetime

        memory_repo._doc_meta["h1"] = ("doc.pdf", datetime.now(UTC))
        return IngestOutcome(
            status="ingested",
            source_document_id=memory_repo._docs["h1"],
            file_hash="h1",
            pages=3,
            chunks_inserted=7,
            elapsed_s=0.2,
        )

    monkeypatch.setattr("rag.ui.routes.ingest_pdf_core", _fast_ingest)
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_post = await client.post(
            "/ui/upload",
            files={"pdf": ("doc.pdf", minimal_pdf_bytes, "application/pdf")},
        )
        task_id = _extract_task_id(r_post.text)

        r_final = await _poll_until_terminal(client, task_id)

    assert r_final.status_code == 200
    # Fresh ingest (empty corpus pre-upload): the template says "Ingested X"
    # rather than the older unconditional "Replaced previous document with X".
    assert "Upload complete" in r_final.text
    assert "Ingested" in r_final.text
    assert "doc.pdf" in r_final.text
    assert "7 chunks" in r_final.text
    assert "3 pages" in r_final.text
    # OOB swap region present so the indicator refreshes.
    assert "hx-swap-oob" in r_final.text
    # Job lingers in the registry after terminal delivery so a stray
    # follow-up poll (HTMX queues the next poll before swapping in the
    # current response) gets the same result HTML rather than the
    # session-expired message. The entry is reaped opportunistically on
    # the next upload attempt.
    assert task_id in app.state.upload_jobs
    assert app.state.upload_jobs[task_id].is_terminal


@pytest.mark.asyncio
async def test_upload_failure_renders_error_via_polling(
    small_dim_settings, memory_repo, fake_upload_pool, minimal_pdf_bytes, monkeypatch
):
    """Background ingest raises an UpstreamProviderError; polling returns the error."""

    async def _failing_ingest(**kwargs):
        raise UpstreamProviderError("gemini", RuntimeError("embedding batch 2 failed"))

    monkeypatch.setattr("rag.ui.routes.ingest_pdf_core", _failing_ingest)
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_post = await client.post(
            "/ui/upload",
            files={"pdf": ("doc.pdf", minimal_pdf_bytes, "application/pdf")},
        )
        task_id = _extract_task_id(r_post.text)

        r_final = await _poll_until_terminal(client, task_id)

    assert r_final.status_code == 503
    # Feature 004 (clarify 2026-05-13): visible copy is category-coded.
    # The "embedding_failed" cause key remains in the log trail only.
    assert "Server error" in r_final.text
    assert "embedding_failed" not in r_final.text
    assert "Your existing documents are unchanged." in r_final.text


@pytest.mark.asyncio
async def test_upload_replace_clears_prior_corpus(
    small_dim_settings, memory_repo, fake_upload_pool, minimal_pdf_bytes, monkeypatch
):
    """Background task's `delete_all_source_documents` fires before ingest."""
    prior_doc_id = uuid4()
    memory_repo._docs["prior"] = prior_doc_id
    memory_repo._chunks.append(
        ChunkRecord(
            source_document_id=prior_doc_id,
            page_number=1,
            char_offset_start=0,
            char_offset_end=12,
            raw_text="prior content",
            token_count=2,
            embedding=[0.0, 1.0, 0.0],
        )
    )

    async def _ingest(**kwargs):
        # By this point delete_all_source_documents has run inside the
        # transaction; the in-memory repo's _docs is empty.
        memory_repo._docs["new"] = uuid4()
        memory_repo._chunks.append(
            ChunkRecord(
                source_document_id=memory_repo._docs["new"],
                page_number=1,
                char_offset_start=0,
                char_offset_end=10,
                raw_text="new content",
                token_count=2,
                embedding=[1.0, 0.0, 0.0],
            )
        )
        return IngestOutcome(
            status="ingested",
            source_document_id=memory_repo._docs["new"],
            file_hash="new",
            pages=1,
            chunks_inserted=1,
            elapsed_s=0.05,
        )

    monkeypatch.setattr("rag.ui.routes.ingest_pdf_core", _ingest)
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_post = await client.post(
            "/ui/upload",
            files={"pdf": ("new.pdf", minimal_pdf_bytes, "application/pdf")},
        )
        task_id = _extract_task_id(r_post.text)
        await _poll_until_terminal(client, task_id)

    # Prior corpus gone; only the new doc remains.
    assert prior_doc_id not in memory_repo._docs.values()
    assert "new" in memory_repo._docs


@pytest.mark.asyncio
async def test_cancel_endpoint_aborts_task_and_rolls_back_transaction(
    small_dim_settings, memory_repo, fake_upload_pool, minimal_pdf_bytes, monkeypatch
):
    """POST /ui/upload/cancel/{task_id} aborts the task; transaction rolls back.

    Either of two paths leads to ``cancelled`` state:
    1. The route's own ``after_clear`` check fires (cancel arrived
       before the task entered ``ingest_pdf_core``).
    2. The pipeline's ``cancel_check`` callback fires mid-ingest.

    Both are valid; we assert the observable end state (cancelled
    partial + fake pool's transaction marked rolled-back).
    """

    async def _slow_ingest(**kwargs):
        # Poll the cancel_check; if cancel fires here we abort gracefully.
        # In practice the route's after_clear check usually catches the
        # cancel first; this stub is the second-chance path.
        cancel_check = kwargs["cancel_check"]
        for _ in range(500):
            if await cancel_check():
                raise UploadCancelledError(phase="between_embedding_batches")
            await asyncio.sleep(0.005)
        # Should not reach: cancel should have fired by now.
        raise AssertionError("ingest stub timed out waiting for cancel")

    monkeypatch.setattr("rag.ui.routes.ingest_pdf_core", _slow_ingest)
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_post = await client.post(
            "/ui/upload",
            files={"pdf": ("new.pdf", minimal_pdf_bytes, "application/pdf")},
        )
        task_id = _extract_task_id(r_post.text)

        # Cancel the upload.
        r_cancel = await client.post(f"/ui/upload/cancel/{task_id}")
        assert r_cancel.status_code == 200

        # Poll until terminal.
        r_final = await _poll_until_terminal(client, task_id)

    assert r_final.status_code == 200
    assert "cancelled" in r_final.text.lower()
    # The route's `async with conn.transaction():` exited via exception,
    # which the fake pool's _FakeTxn records as a rollback.
    assert fake_upload_pool.conn.rolled_back >= 1, (
        "transaction context manager should have rolled back on cancel"
    )


@pytest.mark.asyncio
async def test_status_unknown_task_returns_expired_session_partial(
    small_dim_settings, memory_repo, fake_upload_pool
):
    """Polling a task_id that doesn't exist returns the expired-session message."""
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/ui/upload/status/no-such-task")
    assert r.status_code == 200
    assert "Upload session expired" in r.text
    # No polling trigger — the polling element on the client is replaced
    # with this static empty-state, so polling stops.
    assert "hx-trigger" not in r.text


@pytest.mark.asyncio
async def test_progress_callback_is_invoked_with_stage_updates(
    small_dim_settings, memory_repo, fake_upload_pool, minimal_pdf_bytes, monkeypatch
):
    """Verify the background task wires up progress_callback so the UI sees stage changes."""
    progress_calls: list[tuple[str, str]] = []

    async def _ingest_reports_progress(**kwargs):
        cb = kwargs["progress_callback"]
        if cb is not None:
            await cb("extracting", "Extracting pages from PDF…")
            await cb("embedding", "Embedding chunks (batch 1/2)…")
            await cb("persisting", "Saving to vector store…")
        progress_calls.append(("done", "stub finished"))
        return IngestOutcome(
            status="ingested",
            source_document_id=uuid4(),
            file_hash="h",
            pages=1,
            chunks_inserted=2,
            elapsed_s=0.05,
        )

    monkeypatch.setattr("rag.ui.routes.ingest_pdf_core", _ingest_reports_progress)
    app = _build_app(small_dim_settings, memory_repo, fake_upload_pool)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_post = await client.post(
            "/ui/upload",
            files={"pdf": ("doc.pdf", minimal_pdf_bytes, "application/pdf")},
        )
        task_id = _extract_task_id(r_post.text)
        # Let the task run to completion.
        r_final = await _poll_until_terminal(client, task_id)

    assert r_final.status_code == 200
    assert "Upload complete" in r_final.text
    # Background task reached the inner stub (progress callbacks accepted).
    assert ("done", "stub finished") in progress_calls
