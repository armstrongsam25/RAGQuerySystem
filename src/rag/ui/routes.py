"""HTMX routes — `GET /`, `POST /ui/query`, `POST /ui/upload` + status/cancel, current-doc, clear.

The query routes are unchanged from feature 002.

The upload surface (feature 003) is a **background-task model with
client-side polling**:

- ``POST /ui/upload`` — validates fast (lock check, magic header, size cap),
  spawns an ``asyncio.Task`` to run the actual ingest, and returns the
  in-progress partial. The partial polls every ~500ms.
- ``GET /ui/upload/status/{task_id}`` — returns either the in-progress
  partial (still running, polling continues) or the final result panel
  (success / error / cancelled, polling stops because the new markup
  drops the trigger).
- ``POST /ui/upload/cancel/{task_id}`` — sets the job's cancel event;
  the background task's progress checkpoints observe it and raise
  :class:`UploadCancelledError`, which rolls back the open transaction.

Load-bearing pieces preserved:
- Strict-rollback transaction wrapping inside the background task.
- Magic-header validation (FR-014) + size cap (FR-015) in the POST
  handler before any task is spawned.
- Process-wide ``asyncio.Lock`` for concurrent-upload 409 (FR-028);
  acquired in the background task so the lock lifetime matches the
  work, not the POST request.
- Structured logging with ``trace_id`` propagation (``trace_id`` == ``task_id``).
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg_pool import AsyncConnectionPool

from rag.config import Settings
from rag.ingest import UploadCancelledError, ingest_pdf_core
from rag.log import get_logger
from rag.providers.base import Providers, UpstreamProviderError
from rag.providers.gemini import GeminiProvider, RateLimitedError
from rag.query.pipeline import answer_question
from rag.query.responses import (
    QueryAnswered,
    QueryNoDocuments,
    QueryRefused,
)
from rag.repositories.base import ChunkRepository, SourceDocumentInfo
from rag.trace import TRACE_LOG_KEY, new_trace_id
from rag.ui.upload_jobs import UploadJob
from rag.ui.upload_validate import InvalidPDFError, validate_pdf_magic

_FILE_HASH_RE = re.compile(r"[0-9a-f]{64}")

logger = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _get_chunk_repo(request: Request) -> ChunkRepository:
    return request.app.state.chunk_repo


def _get_providers(request: Request) -> Providers:
    return request.app.state.providers


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _get_pool(request: Request) -> AsyncConnectionPool:
    return request.app.state.pool


def _try_unlink_pdf(storage_dir: Path, file_hash: str, *, trace_id: str) -> None:
    """Best-effort delete of a persisted PDF by its file_hash.

    Missing files are not an error — they're expected when the system was
    upgraded after an existing ingest, or when a prior write-side failure
    left a DB row without a PDF. Other OSErrors get logged but never
    propagate; the demo tolerates the orphan rather than 500'ing a clear.
    """
    if not _FILE_HASH_RE.fullmatch(file_hash):
        return
    path = storage_dir / f"{file_hash}.pdf"
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(
            "pdf_unlink_failed",
            extra={TRACE_LOG_KEY: trace_id, "path": str(path), "error": str(exc)},
        )


def _write_pdf_atomically(storage_dir: Path, file_hash: str, pdf_bytes: bytes) -> None:
    """Write PDF bytes to {storage_dir}/{file_hash}.pdf atomically.

    Writes to a sibling `.tmp` first, then ``os.replace`` to the final name.
    On same-volume targets this is atomic on POSIX and Windows, so a crash
    can't leave a half-written file at the canonical path.
    """
    storage_dir.mkdir(parents=True, exist_ok=True)
    final = storage_dir / f"{file_hash}.pdf"
    tmp = storage_dir / f"{file_hash}.pdf.tmp"
    tmp.write_bytes(pdf_bytes)
    os.replace(tmp, final)


def _pdf_available_hashes(
    docs: list[SourceDocumentInfo], storage_dir: Path
) -> set[str]:
    """Return the subset of ``docs`` file_hashes whose PDF bytes are on disk.

    Used by the templates to decide whether to render the filename as a
    clickable /ui/pdf/{hash} link or as plain text — keeps a row with a
    missing original (legacy ingest, write-side OSError that was logged
    and suppressed) from surfacing a dead link.
    """
    available: set[str] = set()
    for doc in docs:
        if not doc.file_hash:
            continue
        if (storage_dir / f"{doc.file_hash}.pdf").is_file():
            available.add(doc.file_hash)
    return available


def _render(template_name: str, context: dict) -> str:
    """Render a template to a string without a Request.

    Used by the background task to pre-render the terminal result HTML
    (success / error / cancelled). The status endpoint then returns this
    string verbatim when polled after completion. The lack of Request in
    the context is fine because none of the upload templates reference
    `request`.

    If the template render itself raises, return a minimal fallback HTML
    so the background task can still call ``job.finish_error(...)`` and
    the status endpoint has SOMETHING to serve. Logging the failure here
    surfaces the underlying bug instead of cascading into an
    AssertionError at the status endpoint.
    """
    try:
        return _templates.get_template(template_name).render(context)
    except Exception:
        logger.exception(
            "template_render_failed",
            extra={"template": template_name},
        )
        # Don't include the exception message in the HTML — keep the
        # surface clean. Log readers can correlate by template name.
        return (
            "<div class='status-card status-upload-error'>"
            "<span class='badge badge-upload-error'>Upload failed</span>"
            "<p>Internal template render error; see server logs.</p>"
            "</div>"
        )


# Stages shown in the in-progress card, in execution order. The route
# computes the per-stage state (`done` / `active` / `pending`) from the
# job's current `stage` value and passes a flat list to the template —
# keeps the template free of conditional logic that's a footgun in
# Jinja2 (set-inside-if scoping rules).
_PROGRESS_STAGES: list[tuple[str, str]] = [
    ("clearing", "Clear"),
    ("extracting", "Extract"),
    ("chunking", "Chunk"),
    ("embedding", "Embed"),
    ("persisting", "Save"),
]

# Each ingest stage emitted by ingest_pdf_core mapped to its index in
# _PROGRESS_STAGES (so transient stages like `extracted` / `chunked`
# still highlight the right step). Negative values mean "before the
# first stage" (pending) or "outside the stage bar" (cancelled, error).
_STAGE_TO_INDEX: dict[str, int] = {
    "pending": -1,
    "clearing": 0,
    "extracting": 1,
    "extracted": 1,
    "chunking": 2,
    "chunked": 2,
    "embedding": 3,
    "persisting": 4,
    "complete": 5,
    "cancelled": -2,
    "error": -2,
}


def _stages_view(current_stage: str) -> list[dict[str, str]]:
    """Pre-compute the per-stage view-model the in-progress template renders."""
    current_idx = _STAGE_TO_INDEX.get(current_stage, 0)
    view: list[dict[str, str]] = []
    for i, (_key, label) in enumerate(_PROGRESS_STAGES):
        if i < current_idx:
            state, dot = "done", "&#x2713;"
        elif i == current_idx:
            state, dot = "active", "&middot;"
        else:
            state, dot = "pending", "&middot;"
        view.append({"label": label, "state": state, "dot": dot})
    return view


def register_ui_routes(app: FastAPI) -> None:
    """Wire the UI routes + static-asset mount onto an existing FastAPI app."""
    # Static assets.
    app.mount(
        "/ui/static",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="ui-static",
    )

    @app.get("/", response_class=HTMLResponse)
    async def page(request: Request) -> HTMLResponse:
        return _templates.TemplateResponse(request, "base.html", {})

    @app.post("/ui/query", response_class=HTMLResponse)
    async def ui_query(
        request: Request,
        question: Annotated[str, Form()],
        repo: Annotated[ChunkRepository, Depends(_get_chunk_repo)],
        providers: Annotated[Providers, Depends(_get_providers)],
        settings: Annotated[Settings, Depends(_get_settings)],
    ) -> HTMLResponse:
        """Render the assistant reply only (no chat-turn wrapper).

        The client optimistically inserts the chat-turn shell (user bubble +
        a "Thinking…" placeholder) on form submit and retargets the htmx
        swap at the new .msg-assistant slot, so this route returns just the
        inner partial that fills the slot. See base.html → onChatConfigRequest.
        """
        trace_id = new_trace_id()
        try:
            response = await answer_question(
                question,
                repo=repo,
                providers=providers,
                settings=settings,
                trace_id=trace_id,
            )
        except ValueError as exc:
            # Log fidelity preserved: the underlying message stays in the log
            # trail; the UI shows only the fixed-category "Invalid input" copy
            # per the 2026-05-13 clarify decision and contracts/error-rendering.md.
            logger.warning(
                "ui_validation_error",
                extra={TRACE_LOG_KEY: trace_id, "cause": str(exc)},
            )
            html = _templates.TemplateResponse(
                request,
                "_error.html",
                {"category": "validation", "trace_id": trace_id},
                status_code=400,
            )
            html.headers["X-RAG-Trace-Id"] = trace_id
            return html
        except UpstreamProviderError as exc:
            logger.warning(
                "ui_upstream_failure",
                extra={
                    TRACE_LOG_KEY: trace_id,
                    "provider": exc.provider,
                    "cause": str(exc.cause),
                },
            )
            html = _templates.TemplateResponse(
                request,
                "_error.html",
                {"category": "server", "trace_id": trace_id},
                status_code=503,
            )
            html.headers["X-RAG-Trace-Id"] = trace_id
            return html

        inner = {
            QueryAnswered: "_answered.html",
            QueryRefused: "_refused.html",
            QueryNoDocuments: "_no_documents.html",
        }[type(response)]
        html = _templates.TemplateResponse(
            request,
            inner,
            {"response": response},
        )
        html.headers["X-RAG-Trace-Id"] = trace_id
        return html

    @app.get("/ui/current-doc", response_class=HTMLResponse)
    async def ui_current_doc(
        request: Request,
        repo: Annotated[ChunkRepository, Depends(_get_chunk_repo)],
        settings: Annotated[Settings, Depends(_get_settings)],
    ) -> HTMLResponse:
        docs = await repo.list_source_documents()
        return _templates.TemplateResponse(
            request,
            "_current_doc.html",
            {
                "docs": docs,
                "pdf_available_hashes": _pdf_available_hashes(
                    docs, settings.RAG_PDF_STORAGE_DIR
                ),
            },
        )

    @app.get("/ui/pdf/{file_hash}")
    async def ui_pdf(
        file_hash: str,
        repo: Annotated[ChunkRepository, Depends(_get_chunk_repo)],
        settings: Annotated[Settings, Depends(_get_settings)],
    ) -> FileResponse:
        """Serve the original PDF bytes for an ingested source document.

        The path uses the source-document's file_hash so we can validate it
        as a 64-char hex string (which prevents path traversal) and look up
        the display_filename to set a friendly Content-Disposition tab title.
        """
        if not _FILE_HASH_RE.fullmatch(file_hash):
            raise HTTPException(status_code=404, detail="not found")
        storage_dir = settings.RAG_PDF_STORAGE_DIR.resolve()
        path = (storage_dir / f"{file_hash}.pdf").resolve()
        # Belt-and-suspenders traversal guard. _FILE_HASH_RE already restricts
        # to [0-9a-f]{64} so this can't fail in practice, but the check makes
        # intent unmistakable and survives future regex loosening.
        if not path.is_relative_to(storage_dir) or not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        # Recover the display_filename so the browser tab shows a friendly
        # name instead of the 64-char hash. If the row was deleted between
        # the link render and the click, fall back to the hash filename.
        docs = await repo.list_source_documents()
        display_filename = next(
            (d.display_filename for d in docs if d.file_hash == file_hash),
            f"{file_hash}.pdf",
        )
        return FileResponse(
            path,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{quote(display_filename)}"',
            },
        )

    @app.post("/ui/clear", response_class=HTMLResponse)
    async def ui_clear(
        request: Request,
        repo: Annotated[ChunkRepository, Depends(_get_chunk_repo)],
        pool: Annotated[AsyncConnectionPool, Depends(_get_pool)],
        settings: Annotated[Settings, Depends(_get_settings)],
    ) -> HTMLResponse:
        trace_id = new_trace_id()
        logger.info("clear_requested", extra={TRACE_LOG_KEY: trace_id})
        # Snapshot the hashes BEFORE the transaction so we can unlink the
        # corresponding PDF files AFTER a successful commit. Doing the unlink
        # inside the transaction would orphan PDFs on rollback.
        prior_docs = await repo.list_source_documents()
        async with pool.connection() as conn, conn.transaction():
            deleted = await repo.delete_all_source_documents(connection=conn)
        # Post-commit: best-effort unlink. Missing files are fine — the demo
        # tolerates orphaned DB rows / orphaned files (they 404 on serve).
        for doc in prior_docs:
            _try_unlink_pdf(settings.RAG_PDF_STORAGE_DIR, doc.file_hash, trace_id=trace_id)
        logger.info(
            "clear_complete",
            extra={TRACE_LOG_KEY: trace_id, "deleted_source_documents": deleted},
        )
        html = _templates.TemplateResponse(
            request,
            "_current_doc.html",
            {"docs": [], "pdf_available_hashes": set(), "clear_chat": True},
        )
        html.headers["X-RAG-Trace-Id"] = trace_id
        return html

    @app.post("/ui/upload", response_class=HTMLResponse)
    async def ui_upload(
        request: Request,
        pdf: Annotated[UploadFile, File(description="PDF to ingest")],
        repo: Annotated[ChunkRepository, Depends(_get_chunk_repo)],
        providers: Annotated[Providers, Depends(_get_providers)],
        settings: Annotated[Settings, Depends(_get_settings)],
        pool: Annotated[AsyncConnectionPool, Depends(_get_pool)],
    ) -> HTMLResponse:
        trace_id = new_trace_id()
        logger.info(
            "upload_received",
            extra={
                TRACE_LOG_KEY: trace_id,
                "upload_filename": pdf.filename,
                "content_type": pdf.content_type,
                "size_bytes": pdf.size,
            },
        )

        upload_lock = request.app.state.upload_lock
        upload_jobs: dict[str, UploadJob] = request.app.state.upload_jobs

        # ---- Reap prior terminal jobs ------------------------------------
        # Terminal jobs linger so late polls don't see "session expired"
        # (see ui_upload_status); reap them here when a new upload starts.
        for stale_id in [tid for tid, j in upload_jobs.items() if j.is_terminal]:
            upload_jobs.pop(stale_id, None)

        # ---- Concurrent-upload guard (FR-028) -----------------------------
        # Reject if another upload is in flight. The check is a snapshot:
        # the actual lock acquisition happens in the background task.
        if upload_lock.locked() or any(not j.is_terminal for j in upload_jobs.values()):
            logger.warning(
                "upload_rejected_concurrent",
                extra={TRACE_LOG_KEY: trace_id, "upload_filename": pdf.filename},
            )
            html = _templates.TemplateResponse(
                request,
                "_upload_error.html",
                {
                    "category": "concurrent",
                    "prior_corpus_intact": True,
                    "trace_id": trace_id,
                },
                status_code=409,
            )
            html.headers["X-RAG-Trace-Id"] = trace_id
            return html

        # ---- Magic-header validation (FR-014) -----------------------------
        try:
            await validate_pdf_magic(pdf)
        except InvalidPDFError as exc:
            logger.warning(
                "upload_rejected_invalid_pdf",
                extra={
                    TRACE_LOG_KEY: trace_id,
                    "upload_filename": pdf.filename,
                    "observed": repr(exc.observed),
                },
            )
            html = _templates.TemplateResponse(
                request,
                "_upload_error.html",
                {
                    "category": "validation",
                    "prior_corpus_intact": True,
                    "trace_id": trace_id,
                },
                status_code=400,
            )
            html.headers["X-RAG-Trace-Id"] = trace_id
            return html

        # ---- Size cap (FR-015) -------------------------------------------
        cap = settings.RAG_MAX_UPLOAD_BYTES
        size = pdf.size or 0
        if size > cap:
            logger.warning(
                "upload_rejected_oversize",
                extra={TRACE_LOG_KEY: trace_id, "size_bytes": size, "cap_bytes": cap},
            )
            html = _templates.TemplateResponse(
                request,
                "_upload_error.html",
                {
                    "category": "validation",
                    "prior_corpus_intact": True,
                    "trace_id": trace_id,
                },
                status_code=413,
            )
            html.headers["X-RAG-Trace-Id"] = trace_id
            return html

        # ---- Spawn the background task -----------------------------------
        # Read pdf bytes now so the UploadFile can go out of scope when
        # the POST handler returns.
        pdf_bytes = await pdf.read()
        display_filename = pdf.filename or "upload.pdf"
        gemini = providers.embedder
        if not isinstance(gemini, GeminiProvider):
            gemini = gemini  # type: ignore[assignment]

        job = UploadJob(task_id=trace_id, filename=display_filename)
        upload_jobs[trace_id] = job

        async def _run_task() -> None:
            await _run_upload_task(
                job=job,
                pdf_bytes=pdf_bytes,
                display_filename=display_filename,
                gemini=gemini,
                repo=repo,
                settings=settings,
                pool=pool,
                upload_lock=upload_lock,
            )

        job.task = asyncio.create_task(_run_task(), name=f"upload-{trace_id}")
        logger.info(
            "upload_task_spawned",
            extra={TRACE_LOG_KEY: trace_id, "upload_filename": display_filename},
        )

        # ---- Return the in-progress partial ------------------------------
        html = _templates.TemplateResponse(
            request,
            "_upload_in_progress.html",
            {
                "task_id": trace_id,
                "filename": display_filename,
                "stage": job.stage,
                "stage_message": job.stage_message,
                "stages_view": _stages_view(job.stage),
            },
            status_code=200,
        )
        html.headers["X-RAG-Trace-Id"] = trace_id
        return html

    @app.get("/ui/upload/status/{task_id}", response_class=HTMLResponse)
    async def ui_upload_status(
        request: Request,
        task_id: str,
    ) -> HTMLResponse:
        """Polled by the in-progress partial every ~500ms.

        Returns the in-progress partial again while the task is running,
        or the final result partial when it terminates. The terminal
        partial doesn't carry the polling trigger, so polling stops
        naturally.
        """
        upload_jobs: dict[str, UploadJob] = request.app.state.upload_jobs
        job = upload_jobs.get(task_id)
        if job is None:
            # Task unknown (never existed, or was reaped). Return an empty
            # static response so HTMX's polling element disappears.
            return HTMLResponse(
                content=(
                    "<div class='upload-progress-empty'>"
                    "Upload session expired. Refresh the page if you need to "
                    "re-upload.</div>"
                ),
                status_code=200,
            )

        if job.is_terminal:
            # Re-entrant terminal delivery: the in-progress partial polls
            # every 500ms, and HTMX may have queued the next poll BEFORE
            # swapping in the prior poll's terminal response. If we popped
            # the job on the first terminal delivery, that second queued
            # poll would race to ``session-expired`` and overwrite the
            # legitimate result panel that just rendered. Instead, keep
            # the job in the registry and serve the same result_html for
            # every subsequent poll; the client's polling element has
            # already been replaced by the result, so HTMX's stray follow-
            # up polls render the same result into nowhere (no element
            # with that hx-trigger exists anymore).
            #
            # The job is reaped on the NEXT upload attempt — the
            # concurrent-upload guard ignores terminal jobs, and POSTs
            # opportunistically clean stale terminal entries below.
            content = job.result_html or (
                # Defensive fallback if the background task crashed
                # BEFORE setting result_html (asyncio.create_task swallows
                # exceptions silently otherwise — the safety net inside
                # _run_upload_task should always populate result_html,
                # but if it doesn't, this keeps the status endpoint from
                # 500'ing into a polling loop).
                "<div class='status-card status-upload-error'>"
                "<span class='badge badge-upload-error'>Upload failed</span>"
                "<p>The upload task did not record a result. "
                "See server logs for the underlying error.</p>"
                "</div>"
            )
            html = HTMLResponse(content=content, status_code=job.result_status_code)
            html.headers["X-RAG-Trace-Id"] = task_id
            return html

        # Still running — return the in-progress partial with the latest
        # stage + message. HTMX's hx-trigger="every 500ms" on the returned
        # element keeps polling.
        try:
            html = _templates.TemplateResponse(
                request,
                "_upload_in_progress.html",
                {
                    "task_id": task_id,
                    "filename": job.filename,
                    "stage": job.stage,
                    "stage_message": job.stage_message,
                    "stages_view": _stages_view(job.stage),
                },
            )
        except Exception as exc:
            # Surface render errors in the access log instead of silently
            # returning 500 — the previous template had Jinja set-inside-
            # if scoping that worked when called from the POST handler
            # but failed in some renders. The catch + log is defensive
            # so a future template bug doesn't go silent.
            logger.exception(
                "upload_status_render_failed",
                extra={
                    TRACE_LOG_KEY: task_id,
                    "stage": job.stage,
                    "stage_message": job.stage_message,
                    "error": str(exc),
                },
            )
            raise
        html.headers["X-RAG-Trace-Id"] = task_id
        return html

    @app.post("/ui/upload/cancel/{task_id}", response_class=HTMLResponse)
    async def ui_upload_cancel(
        request: Request,
        task_id: str,
    ) -> HTMLResponse:
        """Signal cancellation to a running upload task.

        The task's progress callbacks poll the cancel event and raise
        :class:`UploadCancelledError` at the next checkpoint, which rolls
        back the open transaction. The next status poll will see the
        terminal cancelled state.
        """
        upload_jobs: dict[str, UploadJob] = request.app.state.upload_jobs
        job = upload_jobs.get(task_id)
        if job is None or job.is_terminal:
            return HTMLResponse(
                content=(
                    "<div class='upload-progress-empty'>"
                    "Upload session not found or already complete.</div>"
                ),
                status_code=200,
            )
        logger.info("upload_cancel_requested", extra={TRACE_LOG_KEY: task_id})
        job.cancel_event.set()
        # Return the current in-progress partial; the next poll will pick
        # up the terminal cancelled state.
        html = _templates.TemplateResponse(
            request,
            "_upload_in_progress.html",
            {
                "task_id": task_id,
                "filename": job.filename,
                "stage": job.stage,
                "stage_message": "Cancelling…",
            },
        )
        html.headers["X-RAG-Trace-Id"] = task_id
        return html


async def _run_upload_task(
    *,
    job: UploadJob,
    pdf_bytes: bytes,
    display_filename: str,
    gemini: GeminiProvider,
    repo: ChunkRepository,
    settings: Settings,
    pool: AsyncConnectionPool,
    upload_lock: asyncio.Lock,
) -> None:
    """Run the actual upload work outside the HTTP request lifecycle.

    Updates ``job`` as it progresses; sets one of the terminal states
    (``complete`` / ``error`` / ``cancelled``) before returning. All
    exceptions are caught and translated into rendered error HTML on
    ``job.result_html`` — they MUST NOT propagate out of this coroutine
    (asyncio.create_task swallows them silently otherwise).
    """
    trace_id = job.task_id
    logger.info(
        "upload_task_started",
        extra={TRACE_LOG_KEY: trace_id, "upload_filename": display_filename},
    )

    async def progress(stage: str, message: str) -> None:
        job.set_progress(stage, message)
        # Use ``stage_message`` (not ``message``) in `extra` — ``message`` is a
        # reserved attribute on Python's ``LogRecord`` and the stdlib raises
        # ``KeyError("Attempt to overwrite 'message'...")`` at INFO-level
        # emission time. Same class of bug as the ``filename`` collision
        # I hit earlier.
        logger.info(
            "upload_progress",
            extra={TRACE_LOG_KEY: trace_id, "stage": stage, "stage_message": message},
        )

    async def cancel_check() -> bool:
        return job.cancel_event.is_set()

    job.set_progress("clearing", "Clearing existing document…")

    # Snapshot the prior doc list BEFORE the transaction so we can both
    # (a) include `prior_filename` in the success template (the chat-thread
    # "— Switched to NEW.pdf (was OLD.pdf) —" separator), and
    # (b) unlink the prior PDF files after a successful commit.
    prior_docs = await repo.list_source_documents()
    prior_filename = prior_docs[0].display_filename if prior_docs else None

    try:
        async with upload_lock:
            async with pool.connection() as conn, conn.transaction():
                await repo.delete_all_source_documents(connection=conn)
                if job.cancel_event.is_set():
                    raise UploadCancelledError(phase="after_clear")

                outcome = await ingest_pdf_core(
                    pdf_bytes=pdf_bytes,
                    display_filename=display_filename,
                    gemini=gemini,
                    repo=repo,
                    settings=settings,
                    trace_id=trace_id,
                    connection=conn,
                    cancel_check=cancel_check,
                    progress_callback=progress,
                )
            # Outside the transaction: re-read the doc list so the OOB
            # swap on `#current-doc` reflects the post-ingest state.
            docs = await repo.list_source_documents()
            # Post-commit filesystem ops: unlink prior PDFs, then write the
            # new one. Order: unlink first so a hash-collision on a re-ingest
            # (same file_hash → same path) doesn't unlink the file we just
            # wrote. The new write is atomic (.tmp → os.replace).
            for prior in prior_docs:
                if prior.file_hash != outcome.file_hash:
                    _try_unlink_pdf(
                        settings.RAG_PDF_STORAGE_DIR,
                        prior.file_hash,
                        trace_id=trace_id,
                    )
            try:
                _write_pdf_atomically(
                    settings.RAG_PDF_STORAGE_DIR,
                    outcome.file_hash,
                    pdf_bytes,
                )
            except OSError as exc:
                # The DB ingest already committed; failing to write the PDF
                # leaves a serveable doc whose original is unrecoverable.
                # Log loudly but don't fail the user-visible upload — the
                # answers still work, the filename link will 404.
                logger.warning(
                    "pdf_persist_failed",
                    extra={
                        TRACE_LOG_KEY: trace_id,
                        "file_hash": outcome.file_hash,
                        "error": str(exc),
                    },
                )
    except UploadCancelledError as exc:
        logger.info(
            "upload_cancelled",
            extra={TRACE_LOG_KEY: trace_id, "phase": exc.phase},
        )
        # Cancelled uses its own template — it's a user-initiated terminal
        # state, not an error. Keep the existing copy by reusing the
        # validation category copy isn't right semantically; render a
        # dedicated cancelled card.
        job.finish_cancelled(
            _render(
                "_upload_error.html",
                {
                    "category": "cancelled",
                    "prior_corpus_intact": True,
                    "trace_id": trace_id,
                },
            )
        )
        return
    except RateLimitedError as exc:
        logger.warning(
            "upload_failed",
            extra={
                TRACE_LOG_KEY: trace_id,
                "cause": "rate_limited",
                "retry_hint_s": exc.retry_hint_s,
            },
        )
        job.finish_error(
            _render(
                "_upload_error.html",
                {
                    "category": "rate_limited",
                    "prior_corpus_intact": True,
                    "trace_id": trace_id,
                },
            ),
            status_code=503,
        )
        return
    except UpstreamProviderError as exc:
        logger.warning(
            "upload_failed",
            extra={
                TRACE_LOG_KEY: trace_id,
                "cause": "embedding_failed" if exc.provider == "gemini" else "persistence_failed",
                "provider": exc.provider,
                "error": str(exc.cause),
            },
        )
        job.finish_error(
            _render(
                "_upload_error.html",
                {
                    "category": "server",
                    "prior_corpus_intact": True,
                    "trace_id": trace_id,
                },
            ),
            status_code=503,
        )
        return
    except ValueError as exc:
        logger.warning(
            "upload_failed",
            extra={
                TRACE_LOG_KEY: trace_id,
                "cause": "invalid_pdf",
                "error": str(exc),
            },
        )
        job.finish_error(
            _render(
                "_upload_error.html",
                {
                    "category": "validation",
                    "prior_corpus_intact": True,
                    "trace_id": trace_id,
                },
            ),
            status_code=400,
        )
        return
    except Exception as exc:
        logger.exception(
            "upload_failed_unexpected",
            extra={TRACE_LOG_KEY: trace_id, "error": str(exc)},
        )
        job.finish_error(
            _render(
                "_upload_error.html",
                {
                    "category": "server",
                    "prior_corpus_intact": True,
                    "trace_id": trace_id,
                },
            ),
            status_code=500,
        )
        return

    logger.info(
        "upload_complete",
        extra={
            TRACE_LOG_KEY: trace_id,
            "upload_filename": display_filename,
            "file_hash": outcome.file_hash,
            "chunks_inserted": outcome.chunks_inserted,
            "elapsed_s": round(outcome.elapsed_s, 2),
        },
    )
    job.finish_complete(
        _render(
            "_upload_success.html",
            {
                "pdf_name": display_filename,
                "chunks_inserted": outcome.chunks_inserted,
                "pages": outcome.pages,
                "elapsed_s": round(outcome.elapsed_s, 2),
                "trace_id": trace_id,
                "docs": docs,
                "pdf_available_hashes": _pdf_available_hashes(
                    docs, settings.RAG_PDF_STORAGE_DIR
                ),
                "prior_filename": prior_filename,
            },
        )
    )
