"""HTMX UI route tests (spec FR-017 → FR-022, US4 acceptance)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api import create_app
from rag.query.responses import (
    Citation,
    QueryAnswered,
    QueryNoDocuments,
    QueryRefused,
)


def _make_app(scripted_response, settings, repo, providers) -> FastAPI:
    """Build an app with a no-op lifespan and a monkey-patched answer_question."""

    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.chunk_repo = repo
        app.state.providers = providers
        app.state.pool = None  # unused in UI tests
        app.state.schema_version = "0002_query_path.sql"
        yield

    app = create_app(lifespan=_noop_lifespan)
    return app


@pytest.fixture
def app_factory(monkeypatch, small_dim_settings, memory_repo):
    """Returns a builder that monkey-patches the pipeline's answer_question."""
    from rag.providers.base import Providers as _P

    providers = _P(embedder=None, generator=None, judge=None)  # type: ignore[arg-type]

    def _build(scripted):
        async def _stub(*args, **kwargs):
            if isinstance(scripted, Exception):
                raise scripted
            return scripted

        # Patch BOTH call sites that route through answer_question:
        # the JSON `POST /query` route and the HTMX `POST /ui/query` route.
        import rag.api
        import rag.ui.routes

        monkeypatch.setattr(rag.api, "answer_question", _stub)
        monkeypatch.setattr(rag.ui.routes, "answer_question", _stub)
        return _make_app(scripted, small_dim_settings, memory_repo, providers)

    return _build


def test_get_root_renders_form(app_factory):
    answered = QueryAnswered(
        answer="x",
        citations=[
            Citation(chunk_id=uuid4(), source_document_id=uuid4(), page_number=1, quoted_span="x")
        ],
        model="gemini-2.5-flash",
        trace_id="t",
    )
    app = app_factory(answered)
    with TestClient(app) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert 'hx-post="/ui/query"' in r.text
    # The chat-thread is the append target for /ui/query responses.
    assert 'id="chat-thread"' in r.text
    assert "Thinking" in r.text  # in-flight indicator (FR-021)


def test_post_ui_query_answered_renders_citations(app_factory):
    citation = Citation(
        chunk_id=uuid4(),
        source_document_id=uuid4(),
        page_number=12,
        quoted_span="Patients must fast for 8 hours.",
    )
    answered = QueryAnswered(
        answer="At least 8 hours.",
        citations=[citation],
        model="gemini-2.5-flash",
        trace_id="t-answer",
    )
    app = app_factory(answered)
    with TestClient(app) as client:
        r = client.post("/ui/query", data={"question": "How long?"})
    assert r.status_code == 200
    assert "status-answered" in r.text
    assert "At least 8 hours." in r.text
    assert "p. 12" in r.text
    assert "Patients must fast for 8 hours." in r.text
    assert "trace_id: t-answer" in r.text  # trace comment in HTML


def test_post_ui_query_refused_is_visually_distinct(app_factory):
    refused = QueryRefused(
        message="No.",
        refusal_cause="low_similarity",
        model="gemini-embedding-001",
        trace_id="t-refused",
    )
    app = app_factory(refused)
    with TestClient(app) as client:
        r = client.post("/ui/query", data={"question": "Out of scope."})
    assert r.status_code == 200
    assert "status-refused" in r.text
    assert "Not in document" in r.text
    # FR-013 + FR-020: refused renders no citation block.
    assert "status-answered" not in r.text
    assert '<ul class="citations"' not in r.text


def test_post_ui_query_no_documents_is_visually_distinct(app_factory):
    no_docs = QueryNoDocuments(message="empty corpus", trace_id="t-empty")
    app = app_factory(no_docs)
    with TestClient(app) as client:
        r = client.post("/ui/query", data={"question": "anything"})
    assert r.status_code == 200
    assert "status-empty" in r.text
    assert "rag ingest" in r.text  # FR-014 actionable hint


def test_post_ui_query_validation_error_renders_error_card(app_factory):
    app = app_factory(ValueError("question must be non-empty"))
    with TestClient(app) as client:
        r = client.post("/ui/query", data={"question": "anything"})
    assert r.status_code == 400
    assert "status-error" in r.text


# ---- Feature 004 — Visible failure feedback (US1) -------------------------
#
# These tests pin the contracts/error-rendering.md decision: visible copy
# is category-coded only; raw backend messages MUST NOT leak.


def test_query_503_renders_server_category(app_factory):
    """UpstreamProviderError → 503 → "Server error" copy, no raw cause."""
    from rag.providers.base import UpstreamProviderError

    raw_cause = "psycopg connection refused: host=db port=5432"
    app = app_factory(UpstreamProviderError("postgres", RuntimeError(raw_cause)))
    with TestClient(app) as client:
        r = client.post("/ui/query", data={"question": "anything"})
    assert r.status_code == 503
    assert 'role="alert"' in r.text
    assert "Server error" in r.text
    assert "Something went wrong on our end" in r.text
    # The raw backend text MUST NOT appear in the visible body.
    assert "psycopg" not in r.text
    assert "503" not in r.text or "5432" not in r.text  # status / port leak
    assert raw_cause not in r.text


def test_query_400_renders_validation_category(app_factory):
    """ValueError → 400 → "Invalid input" copy, no raw ValueError message."""
    raw = "question must be non-empty"
    app = app_factory(ValueError(raw))
    with TestClient(app) as client:
        r = client.post("/ui/query", data={"question": "anything"})
    assert r.status_code == 400
    assert 'role="alert"' in r.text
    assert "Invalid input" in r.text
    assert "We couldn't process that request" in r.text
    assert raw not in r.text


def test_upload_409_renders_concurrent_category(small_dim_settings, memory_repo):
    """Concurrent guard → 409 → "Upload in progress" copy, no raw guard text."""
    import asyncio

    from rag.providers.base import Providers
    from rag.ui.upload_jobs import UploadJob

    providers = Providers(embedder=object(), generator=object(), judge=object())  # type: ignore[arg-type]

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        app.state.settings = small_dim_settings
        app.state.chunk_repo = memory_repo
        app.state.providers = providers
        app.state.pool = None
        app.state.schema_version = "0002_query_path.sql"
        app.state.upload_lock = asyncio.Lock()
        # Plant a still-running job so the concurrent guard fires.
        app.state.upload_jobs = {"x": UploadJob(task_id="x", filename="x.pdf")}
        yield

    app = create_app(lifespan=_lifespan)
    with TestClient(app) as client:
        r = client.post(
            "/ui/upload",
            files={"pdf": ("blocked.pdf", b"%PDF-1.4 minimal", "application/pdf")},
        )
    assert r.status_code == 409
    assert 'role="alert"' in r.text
    assert "Upload in progress" in r.text
    # Raw guard text from the pre-feature-004 path MUST NOT appear.
    assert "concurrent_upload" not in r.text
    assert "Please retry once it completes" not in r.text


def test_upload_413_renders_validation_category(small_dim_settings, memory_repo, minimal_pdf_bytes):
    """Oversize → 413 → "Invalid input" copy, no cap-bytes details."""
    import asyncio

    from rag.providers.base import Providers

    providers = Providers(embedder=object(), generator=object(), judge=object())  # type: ignore[arg-type]
    tight = small_dim_settings.model_copy(update={"RAG_MAX_UPLOAD_BYTES": 10})

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        app.state.settings = tight
        app.state.chunk_repo = memory_repo
        app.state.providers = providers
        app.state.pool = None
        app.state.schema_version = "0002_query_path.sql"
        app.state.upload_lock = asyncio.Lock()
        app.state.upload_jobs = {}
        yield

    app = create_app(lifespan=_lifespan)
    with TestClient(app) as client:
        r = client.post(
            "/ui/upload",
            files={"pdf": ("big.pdf", minimal_pdf_bytes, "application/pdf")},
        )
    assert r.status_code == 413
    assert 'role="alert"' in r.text
    assert "Invalid input" in r.text
    # Cap-byte specifics stay in the log trail, not the UI.
    assert "RAG_MAX_UPLOAD_BYTES" not in r.text
    assert "Max size:" not in r.text


def test_upload_invalid_pdf_renders_validation_category(small_dim_settings, memory_repo):
    """Magic-header validation fail → 400 → "Invalid input" copy."""
    import asyncio

    from rag.providers.base import Providers

    providers = Providers(embedder=object(), generator=object(), judge=object())  # type: ignore[arg-type]

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        app.state.settings = small_dim_settings
        app.state.chunk_repo = memory_repo
        app.state.providers = providers
        app.state.pool = None
        app.state.schema_version = "0002_query_path.sql"
        app.state.upload_lock = asyncio.Lock()
        app.state.upload_jobs = {}
        yield

    app = create_app(lifespan=_lifespan)
    with TestClient(app) as client:
        r = client.post(
            "/ui/upload",
            files={"pdf": ("not-a-pdf.pdf", b"plain text, no magic header", "application/pdf")},
        )
    assert r.status_code == 400
    assert 'role="alert"' in r.text
    assert "Invalid input" in r.text
    assert "PDF magic header" not in r.text  # raw text MUST NOT leak


def test_json_query_endpoint_answered(app_factory):
    citation = Citation(
        chunk_id=uuid4(),
        source_document_id=uuid4(),
        page_number=5,
        quoted_span="evidence here",
    )
    answered = QueryAnswered(
        answer="An answer.",
        citations=[citation],
        model="gemini-2.5-flash",
        trace_id="t-json",
    )
    app = app_factory(answered)
    with TestClient(app) as client:
        r = client.post("/query", json={"question": "Q?"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "answered"
    assert body["answer"] == "An answer."
    assert len(body["citations"]) == 1
    assert "X-RAG-Trace-Id" in r.headers


def test_json_query_endpoint_400_on_validation_error(app_factory):
    app = app_factory(ValueError("question must be non-empty"))
    with TestClient(app) as client:
        r = client.post("/query", json={"question": "anything"})
    assert r.status_code == 400
    body = r.json()
    assert "error" in body
    assert "trace_id" in body
