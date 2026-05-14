"""Cross-cutting concurrent-upload test (feature 003 spec FR-028).

The route checks ``app.state.upload_lock.locked()`` AND
``any(not j.is_terminal for j in app.state.upload_jobs.values())``
before spawning the background task; if either is true it returns
HTTP 409 immediately. We verify by holding the lock manually from the
test (simulating "another upload is in progress").

The "lock released after success/failure" property is covered
end-to-end by :mod:`tests.unit.test_upload_progress` via polling.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from rag.api import create_app


def _build_app(settings, repo, providers, pool, lock):
    """Create the app and hand-wire `app.state` (lifespan won't run under AsyncClient)."""
    app = create_app(lifespan=None)
    app.state.settings = settings
    app.state.chunk_repo = repo
    app.state.providers = providers
    app.state.pool = pool
    app.state.schema_version = "0002_query_path.sql"
    app.state.upload_lock = lock
    app.state.upload_jobs = {}
    return app


@pytest.mark.asyncio
async def test_concurrent_upload_returns_409_when_lock_held(
    small_dim_settings, memory_repo, fake_upload_pool, minimal_pdf_bytes
):
    """While the lock is held, /ui/upload returns 409 immediately."""
    from rag.providers.base import Providers

    lock = asyncio.Lock()
    providers = Providers(embedder=object(), generator=object(), judge=object())  # type: ignore[arg-type]
    app = _build_app(small_dim_settings, memory_repo, providers, fake_upload_pool, lock)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with lock:
            r = await client.post(
                "/ui/upload",
                files={"pdf": ("blocked.pdf", minimal_pdf_bytes, "application/pdf")},
            )
        assert r.status_code == 409, r.text
        assert "Upload in progress" in r.text


@pytest.mark.asyncio
async def test_concurrent_upload_returns_409_when_job_in_flight(
    small_dim_settings, memory_repo, fake_upload_pool, minimal_pdf_bytes
):
    """A non-terminal job in app.state.upload_jobs also triggers the 409."""
    from rag.providers.base import Providers
    from rag.ui.upload_jobs import UploadJob

    lock = asyncio.Lock()
    providers = Providers(embedder=object(), generator=object(), judge=object())  # type: ignore[arg-type]
    app = _build_app(small_dim_settings, memory_repo, providers, fake_upload_pool, lock)
    # Plant a still-running job so the route's "any non-terminal" check fires.
    app.state.upload_jobs["existing"] = UploadJob(task_id="existing", filename="x.pdf")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/ui/upload",
            files={"pdf": ("blocked.pdf", minimal_pdf_bytes, "application/pdf")},
        )
    assert r.status_code == 409, r.text
    assert "Upload in progress" in r.text
