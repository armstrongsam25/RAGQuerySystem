"""Live upload-route tests against the running ``make up`` stack.

Skipped silently unless ``RUN_INTEGRATION=1``. These verify the spec
properties that can only be exercised against real pgvector + the real
Gemini stack — namely the always-REPLACE transactional behavior and
the current-document indicator endpoint.

Run with::

    RUN_INTEGRATION=1 pytest tests/integration/test_upload_live.py
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000")
_SAMPLE_PDF = Path(__file__).resolve().parents[2] / "data" / "sample.pdf"


def _read_sample_pdf() -> bytes:
    """Read data/sample.pdf bytes; skip the test if the fixture is missing."""
    if not _SAMPLE_PDF.exists():
        pytest.skip(f"sample PDF not found at {_SAMPLE_PDF}; run `make sample-pdf` first")
    return _SAMPLE_PDF.read_bytes()


@pytest.mark.asyncio
async def test_upload_replaces_corpus_and_updates_indicator() -> None:
    """Upload populates the corpus; GET /ui/current-doc reflects the new state."""
    pdf_bytes = _read_sample_pdf()

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=120.0) as client:
        # Clear first so we start from a known state.
        await client.post("/ui/clear")

        # Upload via the route. Always-replace semantics.
        r_upload = await client.post(
            "/ui/upload",
            files={"pdf": ("sample.pdf", pdf_bytes, "application/pdf")},
        )
        assert r_upload.status_code == 200, r_upload.text
        assert "Replaced previous document" in r_upload.text

        # The current-doc indicator endpoint should now show the doc.
        r_indicator = await client.get("/ui/current-doc")
        assert r_indicator.status_code == 200
        assert "sample.pdf" in r_indicator.text
        assert "Currently ingested" in r_indicator.text


@pytest.mark.asyncio
async def test_upload_non_pdf_rejected_and_corpus_intact() -> None:
    """Non-PDF upload returns 400 and leaves prior corpus untouched.

    The magic-header check fires BEFORE any DB mutation, so even with
    the always-replace flow the prior corpus is preserved on rejection.
    """
    pdf_bytes = _read_sample_pdf()

    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=120.0) as client:
        # Seed the corpus.
        await client.post("/ui/clear")
        r_seed = await client.post(
            "/ui/upload",
            files={"pdf": ("sample.pdf", pdf_bytes, "application/pdf")},
        )
        assert r_seed.status_code == 200

        # Attempt a non-PDF upload — should reject and leave corpus intact.
        r_bad = await client.post(
            "/ui/upload",
            files={"pdf": ("not.pdf", b"This is not a PDF.", "application/pdf")},
        )
        assert r_bad.status_code == 400
        assert "invalid_pdf" in r_bad.text
        assert "Your existing documents are unchanged." in r_bad.text

        # Indicator still shows the seeded doc.
        r_indicator = await client.get("/ui/current-doc")
        assert r_indicator.status_code == 200
        assert "sample.pdf" in r_indicator.text


@pytest.mark.asyncio
async def test_clear_wipes_corpus() -> None:
    """POST /ui/clear removes all documents; indicator returns empty state."""
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=15.0) as client:
        r_clear = await client.post("/ui/clear")
        assert r_clear.status_code == 200
        assert "current-doc-card" not in r_clear.text

        r_indicator = await client.get("/ui/current-doc")
        assert r_indicator.status_code == 200
        assert "current-doc-card" not in r_indicator.text


@pytest.mark.asyncio
async def test_upload_route_rejects_garbage_with_400() -> None:
    """Sanity: the route exists and rejects non-PDF clearly."""
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=15.0) as client:
        r = await client.post(
            "/ui/upload",
            files={"pdf": ("garbage.pdf", b"obviously not a PDF", "application/pdf")},
        )
    assert r.status_code == 400
    assert "invalid_pdf" in r.text
    assert "X-RAG-Trace-Id" in r.headers
