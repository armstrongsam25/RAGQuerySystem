---

description: "Task list for 003-pdf-upload-ui"
---

# Tasks: PDF Upload from the Web UI

**Input**: Design documents in [specs/003-pdf-upload-ui/](.)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Tests are **required** by spec FR-025 (six categories — replace happy path, append happy path, empty-corpus path, cancel-confirmation, non-PDF rejection, oversize rejection) plus the two clarification-driven categories (concurrent-upload 409, cancel-during-ingest rollback). Included throughout, not optional.

**Organization**: Grouped by user story per spec.md (US1 / US2 / US3). US1 is the headline replace flow and ships the full upload surface (UI + route + templates) as the MVP. US2 adds append-specific behavior (the dedup "no new content" rendering branch) on top of the shared route. US3 verifies the empty-corpus shortcut. Cancellation, concurrency, and validation tests are cross-cutting and live in Phase 6.

## Format

`[ID] [P?] [Story?] Description with file path`

- **[P]**: Parallelizable — different files, no dependency on incomplete tasks in the same phase.
- **[Story]**: User story (US1/US2/US3) the task belongs to. Setup, Foundational, and Polish phases carry no story label.

## Path Conventions

Single-project layout continuing from features 001 / 002. All paths are repo-relative from `NymblTechAssessment/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuration, env, and dependency review. No new runtime packages — `python-multipart` is already pinned from feature 002.

- [X] T001 Extend [src/rag/config.py](../../src/rag/config.py): add field `RAG_MAX_UPLOAD_BYTES: int = 26214400` (gt=0, le=1073741824 = 1 GiB upper bound for sanity). Default of 26,214,400 bytes = 25 MiB per clarification Q2 / spec FR-015. Docstring notes that the bound is enforced before any extraction/embedding work and surfaces in HTTP 413 error responses.
- [X] T002 [P] Update [.env.example](../../.env.example): add a `RAG_MAX_UPLOAD_BYTES=26214400` line under the existing app-tier env vars with a one-line comment ("Max upload size in bytes — default 25 MiB"). Place it near the other `RAG_*` keys so the `.env` template stays grouped by feature.
- [X] T003 [P] Confirm [pyproject.toml](../../pyproject.toml) already lists `python-multipart>=0.0.9`; no new dependency lines required. If `uv.lock` was generated without it for some reason, run `uv lock` to refresh.

**Checkpoint**: Config + env updated; lockfile sane. `make lint` still passes — no code changes yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Repository surface (new method + connection-passing parameter), ingest-core refactor for transactional reuse, the upload-validation helper, and the app-state lock. Every user story builds on what lands here.

**⚠️ CRITICAL**: No user-story task may begin until this phase is complete.

- [X] T004 Refactor [src/rag/repositories/base.py](../../src/rag/repositories/base.py): add `connection: AsyncConnection | None = None` kwarg to `ensure_source_document`, `add_chunks`, `delete_source_document_by_hash`. Import `psycopg.AsyncConnection` for the type hint. Add a new abstract method `async def delete_all_source_documents(self, *, connection: AsyncConnection | None = None) -> int` returning the count of deleted documents. Update the `ChunkRepository` Protocol or ABC declaration accordingly so the in-memory + pgvector implementations are required to honor it.
- [X] T005 [P] Implement [src/rag/repositories/pgvector.py](../../src/rag/repositories/pgvector.py)'s new behaviors: (a) introduce a small private helper `_run(self, connection, fn)` that, when `connection` is `None`, acquires from `self._pool` and runs `fn(conn)`; when supplied, runs `fn(connection)` directly — so each public method threads the caller-supplied connection through; (b) update `ensure_source_document`, `add_chunks`, `delete_source_document_by_hash` to use the helper; (c) implement `delete_all_source_documents(*, connection=None)` as `DELETE FROM source_document` and return `cur.rowcount`. The existing FK `ON DELETE CASCADE` from migration 0001 wipes chunks atomically.
- [X] T006 [P] Implement [src/rag/repositories/memory.py](../../src/rag/repositories/memory.py)'s new behaviors: same connection kwarg surface as pgvector (parameter accepted but ignored — there's no real transaction in the in-memory store; tests that need transactional semantics use pgvector). Implement `delete_all_source_documents` as a list-clear of internal source-document + chunk stores; return the count of source-documents removed.
- [X] T007 Refactor [src/rag/ingest/pipeline.py](../../src/rag/ingest/pipeline.py): extract a new function `async def ingest_pdf_core(*, pdf_bytes: bytes, display_filename: str, gemini: GeminiProvider, repo: ChunkRepository, settings: Settings, trace_id: str, force: bool = False, connection: AsyncConnection | None = None) -> IngestOutcome` that takes bytes directly and threads `connection` through to every repository call. Keep the existing path-based `ingest_pdf(pdf_path: Path, ...)` as a thin wrapper: it validates the path, reads the bytes, and calls `ingest_pdf_core` with `connection=None` so the CLI behavior is byte-identical to today. No behavior change for `rag ingest <path>` (FR-022).
- [X] T008 [P] Create [src/rag/ui/upload_validate.py](../../src/rag/ui/upload_validate.py): small module with two public symbols. (1) `class UploadCancelledError(Exception)` — raised from the route handler when a client disconnect is detected mid-ingest; carries an attribute `phase: str` naming the pipeline checkpoint at which the cancellation was detected. (2) `async def validate_pdf_magic(upload: UploadFile) -> None` — reads first 5 bytes of `upload`, raises `InvalidPDFError` (also defined here) if not `b"%PDF-"`, then calls `await upload.seek(0)` to rewind. Per R-006.
- [X] T009 [P] Extend [src/rag/lifespan.py](../../src/rag/lifespan.py): in the lifespan startup body, after the existing pool / providers / repo wiring, set `app.state.upload_lock = asyncio.Lock()`. Document in a one-line comment that the lock is process-wide and is the in-process implementation of FR-028's concurrent-upload guard (a future multi-worker deployment would need to swap in a Postgres advisory lock — R-003).

**Checkpoint**: Repository surface accepts caller-owned connections; `delete_all_source_documents` is implemented in both pgvector and in-memory; `ingest_pdf_core` runs against any caller-supplied connection; upload lock exists on `app.state`. No route exists yet, no UI changes yet — but every existing test (`pytest tests/unit`) still passes.

---

## Phase 3: User Story 1 — Upload a PDF and Replace the Corpus (Priority: P1) 🎯 MVP

**Story goal**: A reviewer with a non-empty corpus can click the paperclip in the textarea, pick a different PDF, confirm **Replace** at the inline confirmation prompt, and end up with a queryable corpus containing only the new PDF. Any failure during the replace rolls back the prior corpus atomically (strict rollback per FR-019).

**Independent test**: With ≥1 `source_document` row and ≥1 `chunk` row present, open the UI, attach a different PDF via the paperclip, select **Replace** at the confirmation. Verify (a) prior rows gone, (b) new rows present with full Article II provenance, (c) the UI shows a replace-success panel naming the new document and chunk count, (d) a query for a fact known only to the prior PDF returns `refused` or `no_documents`. Spec acceptance scenarios US1.1, US1.2, US1.3.

This phase ships the **entire upload UI and route**, because the route's action-dispatch and the UI's paperclip-and-confirm chrome are shared across all three stories. US2 and US3 verify their respective behaviors (append, empty-corpus) on top of the surface this phase delivers.

### Tests for User Story 1

Write these first; verify they fail.

- [X] T010 [P] [US1] Write [tests/unit/test_upload_replace.py](../../tests/unit/test_upload_replace.py). Cases using `InMemoryChunkRepository` + scripted `FakeGeminiProvider` (returns deterministic page texts + embeddings): (a) replace happy path — start with 1 source_document + N chunks; POST upload with `action=replace`; verify exactly 1 source_document remains (the new one), prior chunks are gone, new chunks are present with full provenance; (b) replace acceptance US1.3 — after replace, a `repo.search` for an embedding that previously matched the old PDF's chunks returns zero results; (c) replace returns `_upload_success.html` template with `action="replace"` and the new filename. Use FastAPI's `TestClient` to drive the route.
- [X] T011 [P] [US1] Write [tests/unit/test_upload_replace_rollback.py](../../tests/unit/test_upload_replace_rollback.py). Cases using a `FakeGeminiProvider` configured to raise `UpstreamProviderError` on the second embedding batch: (a) start with 1 source_document + N chunks; POST upload with `action=replace`; verify the response is `_upload_error.html` with cause `embedding_failed`; verify the prior source_document + chunks are **observably unchanged** (row counts + ids match pre-upload exactly). NOTE: the in-memory repo can't truly demonstrate transactional rollback at the SQL layer, so this test verifies the *application-level* contract (handler catches the upstream error, doesn't commit any state); the SQL-level transactional rollback is verified in the integration test (T030).
- [X] T012 [P] [US1] Write [tests/unit/test_upload_route_dispatch.py](../../tests/unit/test_upload_route_dispatch.py). Drives the route's action dispatch logic in isolation: (a) non-empty corpus + no `action` → returns `_upload_confirm.html` (HTTP 200) with `filename`, `size_mb`, `doc_count` template vars populated; (b) `action=cancel` → returns `_upload_cancelled.html` (HTTP 200) and no DB writes occur. Both cases use `InMemoryChunkRepository`.

### Implementation for User Story 1

- [X] T013 [US1] Modify [src/rag/ui/templates/base.html](../../src/rag/ui/templates/base.html): wrap the existing `<textarea id="question">` in a `<div class="textarea-wrap">`. Inside the wrap, add `<label for="pdf-file" class="paperclip-btn" title="Attach PDF">📎</label>` (U+1F4CE PAPERCLIP). Below the question form (still inside `<main>`), add a separate hidden upload form: `<form id="upload-form" hx-post="/ui/upload" hx-encoding="multipart/form-data" hx-target="#response" hx-indicator="#thinking"><input type="file" id="pdf-file" name="pdf" accept="application/pdf" hidden onchange="this.form.dispatchEvent(new Event('submit'))"></form>`. Per contracts/ui.md.
- [X] T014 [P] [US1] Extend [src/rag/ui/static/styles.css](../../src/rag/ui/static/styles.css): add rules for `.textarea-wrap` (`position: relative`), `.paperclip-btn` (`position: absolute; bottom: 0.5rem; right: 0.5rem; cursor: pointer; font-size: 1.25rem; opacity: 0.6;` + `:hover { opacity: 1; }`), and bump the textarea's `padding-right` to reserve space for the icon. Add panel rules for `.upload-confirm`, `.upload-success`, `.upload-error`, `.upload-cancelled` with distinct borders/backgrounds so reviewers can tell upload outcomes apart from query outcomes (SC-007). Styling intentionally minimal.
- [X] T015 [P] [US1] Create [src/rag/ui/templates/_upload_confirm.html](../../src/rag/ui/templates/_upload_confirm.html). Renders three buttons exactly per contracts/upload.md: Replace (with explicit "cannot be undone" copy per FR-009), Append, Cancel. Each button uses `hx-post="/ui/upload"`, `hx-include="#upload-form"`, `hx-vals='{"action": "<choice>"}'`, `hx-target="#response"`, `hx-indicator="#thinking"`. Template vars: `filename`, `size_mb`, `doc_count`.
- [X] T016 [P] [US1] Create [src/rag/ui/templates/_upload_success.html](../../src/rag/ui/templates/_upload_success.html). Template vars: `filename`, `action` ("replace" | "append"), `chunks_inserted`, `no_new_content` (bool). When `no_new_content` is True, render the distinct "This PDF was already in the knowledge base — no new chunks were created." message per FR-018; otherwise render the "Replaced previous documents" / "Added to knowledge base" message per `action`. Wrap in `.upload-success` class.
- [X] T017 [P] [US1] Create [src/rag/ui/templates/_upload_error.html](../../src/rag/ui/templates/_upload_error.html). Template vars: `cause`, `message`, `cap_bytes`/`actual_mb` (for oversize), `started_at` (for concurrent), `prior_corpus_intact` (bool — True only on replace failures, per FR-027). When `prior_corpus_intact` is True, append the "Your existing documents are unchanged." suffix to the rendered message. Wrap in `.upload-error` class.
- [X] T018 [P] [US1] Create [src/rag/ui/templates/_upload_cancelled.html](../../src/rag/ui/templates/_upload_cancelled.html). Minimal: a `<div class="upload-cancelled">` with "Upload cancelled. The knowledge base is unchanged." Wrap in `.upload-cancelled` class.
- [X] T019 [US1] Implement the upload route in [src/rag/ui/routes.py](../../src/rag/ui/routes.py) by extending `register_ui_routes` with a new `@app.post("/ui/upload", response_class=HTMLResponse)` handler. Signature: accepts `request: Request`, `pdf: Annotated[UploadFile, File()]`, `action: Annotated[str | None, Form()] = None`, plus the existing Depends dependencies (`_get_chunk_repo`, `_get_providers`, `_get_settings`). Behavior (per contracts/upload.md):
    1. Mint `trace_id = new_trace_id()`. Log `upload_received`.
    2. Concurrent-upload guard: if `request.app.state.upload_lock.locked()`, log `upload_rejected_concurrent`, return `_upload_error.html` with `cause="concurrent_upload"` and HTTP 409. Otherwise enter `async with request.app.state.upload_lock:` for the rest of the handler.
    3. PDF magic-header validation via `validate_pdf_magic(pdf)`. On `InvalidPDFError`, log `upload_rejected_invalid_pdf`, return `_upload_error.html` with `cause="invalid_pdf"` and HTTP 400.
    4. Size cap check: if `pdf.size > settings.RAG_MAX_UPLOAD_BYTES`, log `upload_rejected_oversize`, return `_upload_error.html` with `cause="oversize"` and HTTP 413.
    5. Handle `action=cancel` (second POST canceling confirmation): log `upload_action_chosen(action="cancel")`, return `_upload_cancelled.html` with HTTP 200. No DB work.
    6. Compute corpus state: `doc_count = await repo.count_source_documents()` (new lightweight repo method — add it in T020).
    7. If `action is None` AND `doc_count > 0`: return `_upload_confirm.html` (HTTP 200) with `filename=pdf.filename`, `size_mb=round(pdf.size/1024/1024, 1)`, `doc_count`. No DB work.
    8. If `action is None` AND `doc_count == 0`: synthesize `action = "append"` (empty corpus → no confirmation needed per FR-011) and fall through.
    9. Validate `action in {"replace", "append"}`; if not, raise `ValueError` → translates to HTTP 400 via the existing error pattern.
    10. Read upload bytes via `pdf_bytes = await pdf.read()`. Acquire a connection from the pool: `async with request.app.state.pool.connection() as conn: async with conn.transaction():`. Inside the transaction:
        - If `action == "replace"`: `await repo.delete_all_source_documents(connection=conn)` → log `upload_clear_complete` with deleted count; check `await request.is_disconnected()` → raise `UploadCancelledError("after_clear")` if disconnected.
        - Call `await ingest_pdf_core(pdf_bytes=pdf_bytes, display_filename=pdf.filename, gemini=providers.gemini, repo=repo, settings=settings, trace_id=trace_id, connection=conn)`. The existing pipeline emits its own structured log records under the same `trace_id`.
        - Between major pipeline phases (post-extraction, between embedding batches, before persistence), the pipeline itself can be extended to poll `request.is_disconnected()` — but for v1 the post-clear poll above is sufficient; the rest comes in T029 (Polish phase, cancel-during-ingest hardening).
    11. On `UpstreamProviderError`: log `upload_failed` with cause + elapsed time; the transaction has already rolled back. Return `_upload_error.html` with the matching cause (`extraction_failed` / `embedding_failed`) and HTTP 503. For `action=="replace"` set `prior_corpus_intact=True` so the FR-027 suffix renders.
    12. On success: log `upload_complete`. Determine `no_new_content = (outcome.status == "already_done")`. Return `_upload_success.html` with `filename`, `action`, `chunks_inserted=outcome.chunks_inserted`, `no_new_content`.
    13. Every response sets `X-RAG-Trace-Id: trace_id` header (parity with `/ui/query`).
- [X] T020 [US1] Add `async def count_source_documents(self, *, connection: AsyncConnection | None = None) -> int` to [src/rag/repositories/base.py](../../src/rag/repositories/base.py), then implement in [src/rag/repositories/pgvector.py](../../src/rag/repositories/pgvector.py) (`SELECT count(*) FROM source_document`) and [src/rag/repositories/memory.py](../../src/rag/repositories/memory.py) (`len(self._source_documents)`). Used by T019 step 6 to decide whether to return the confirmation partial.

**Checkpoint**: Paperclip click → file picker → auto-submit → confirmation panel → Replace → success panel works end-to-end against the in-memory repo and the real pgvector store. T010, T011, T012 all green. Acceptance scenarios US1.1, US1.2, US1.3 verified.

---

## Phase 4: User Story 2 — Upload a PDF and Append to the Corpus (Priority: P1)

**Story goal**: A reviewer with a non-empty corpus can attach a PDF, choose **Append** at the confirmation, and end up with both the old and new documents queryable. Re-attaching the same PDF surfaces a distinct "no new content" message rather than a generic success (dedup invariant per FR-018 / Feature 002 FR-004).

**Independent test**: With one PDF ingested, attach a second distinct PDF via the paperclip, choose **Append**. Verify (a) prior source_document + chunks intact, (b) new source_document + chunks present, (c) a query for a fact in either PDF returns an answered response with citations resolving correctly. Then re-attach the *same* second PDF via Append; verify zero new chunks, response renders the "no new content" message. Spec acceptance scenarios US2.1, US2.2, US2.3.

### Tests for User Story 2

- [X] T021 [P] [US2] Write [tests/unit/test_upload_append.py](../../tests/unit/test_upload_append.py). Cases: (a) append happy path — start with 1 source_document + N chunks; POST upload with a different PDF + `action=append`; verify the original source_document is intact and a second source_document is created with its own chunks; (b) append-dedup — start with the same setup; POST upload with the *same* PDF bytes via `action=append`; verify the response `_upload_success.html` renders with `no_new_content=True` and exactly 0 new chunks were inserted; (c) append-acceptance US2.3 — after appending a second distinct PDF, `repo.search` returns chunks from both source_documents and the `source_document_id` on each retrieved chunk correctly identifies the originating PDF.

### Implementation for User Story 2

No new implementation work — the route handler from T019 already handles `action=append` via the same `ingest_pdf_core` call (the only difference vs `replace` is whether the `delete_all_source_documents` step runs first). The "no new content" rendering branch is in `_upload_success.html` from T016.

This story is intentionally test-heavy and implementation-light: it verifies that the foundational ingest-core dedup behavior (carried forward from feature 002's `ensure_source_document` short-circuit) is correctly surfaced through the new upload route. Per the "Open Items deferred to /speckit-tasks" in research.md, the decision to share the route handler across replace and append is what makes this phase small.

- [X] T022 [US2] If T021's append-dedup test (T021b) reveals that `outcome.status` from `ingest_pdf_core` does not propagate `chunks_inserted=0` for the "already_done" branch (the existing IngestOutcome from feature 002), patch [src/rag/ingest/pipeline.py](../../src/rag/ingest/pipeline.py) to ensure `chunks_inserted=0` is returned in that branch. This is a small defensive fix that may already be in place; verify and patch only if needed.

**Checkpoint**: Append flow works end-to-end. The "no new content" branch renders distinctly. Both source_documents are queryable independently. Acceptance scenarios US2.1, US2.2, US2.3 verified.

---

## Phase 5: User Story 3 — Upload Into an Empty Corpus (Priority: P2)

**Story goal**: On a stack with zero ingested PDFs, the reviewer attaches a file and submits; the system skips the replace/append confirmation entirely (FR-011) and ingests directly. After success, queries against the uploaded PDF work without any page reload.

**Independent test**: On an empty `chunk` table, attach a PDF via the paperclip and let the form auto-submit. Verify (a) no confirmation partial is returned — the response is `_upload_success.html` directly, (b) the new source_document + chunks are present with full provenance, (c) a question whose answer is in the uploaded PDF returns an answered response with citations, without a page reload in between. Spec acceptance scenarios US3.1, US3.2.

### Tests for User Story 3

- [X] T023 [P] [US3] Write [tests/unit/test_upload_empty_corpus.py](../../tests/unit/test_upload_empty_corpus.py). Cases: (a) empty corpus + no `action` field → response is `_upload_success.html` directly (NOT `_upload_confirm.html`), verifies the skip-confirmation branch from T019 step 8; (b) empty corpus + `action=replace` → succeeds with an empty clear (zero rows deleted) followed by ingest, verifies the route doesn't error when there's nothing to clear; (c) empty corpus + `action=append` (explicit) → behaves identically to (a) — the synthesis of `action="append"` for empty corpus is semantically a no-op for an explicit append.

### Implementation for User Story 3

No new implementation work — the empty-corpus branch is in T019 step 8 (`doc_count == 0` synthesizes `action="append"` and falls through). This phase is verification-only.

**Checkpoint**: Empty-corpus upload flow works without a confirmation step. Acceptance scenarios US3.1, US3.2 verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cross-cutting tests (validation, concurrency, cancellation), the cancel-during-ingest hardening, README updates, and the integration tier.

### Cross-cutting tests

- [X] T024 [P] Write [tests/unit/test_upload_validation.py](../../tests/unit/test_upload_validation.py). Cases: (a) upload of a non-PDF file (e.g., a text file with `.pdf` extension) → response is `_upload_error.html` with `cause="invalid_pdf"`, HTTP 400, and the corpus row counts are observably unchanged (verifies SC-004); (b) upload of a file larger than `RAG_MAX_UPLOAD_BYTES` → response is `_upload_error.html` with `cause="oversize"`, HTTP 413, message names both the cap in bytes and in MB, corpus row counts unchanged; (c) upload with a missing `pdf` field → FastAPI's built-in validation returns HTTP 422 (we accept the framework default here; the test just pins the behavior).
- [X] T025 [P] Write [tests/unit/test_upload_concurrent.py](../../tests/unit/test_upload_concurrent.py). Uses two `asyncio.Task`s racing through the route. Case: (a) start one upload that holds the lock (use a `FakeGeminiProvider` that awaits on a `asyncio.Event` to keep the lock held); immediately POST a second upload; verify the second gets `_upload_error.html` with `cause="concurrent_upload"`, HTTP 409, and the first upload eventually completes successfully. (b) After the first completes, a third upload succeeds normally — verifies the lock is released after the response is sent.
- [X] T026 [P] Write [tests/unit/test_upload_cancel_confirm.py](../../tests/unit/test_upload_cancel_confirm.py). Case: with a non-empty corpus, simulate the two-POST flow — first POST returns `_upload_confirm.html`, second POST carries `action=cancel`. Verify the response is `_upload_cancelled.html` (HTTP 200) and that `source_document` + `chunk` row counts are *identical* to pre-first-POST (FR-012, SC-005).
- [X] T027 [P] Write [tests/unit/test_upload_cancel_during_ingest.py](../../tests/unit/test_upload_cancel_during_ingest.py). Case: with a non-empty corpus, POST upload with `action=replace`; inject a fake `request.is_disconnected()` that returns True after the `delete_all_source_documents` step but before the ingest completes. Verify (a) `UploadCancelledError` propagates, (b) the open transaction rolls back, (c) the prior corpus is observably restored (row counts + ids match pre-upload). This validates the user's `/speckit-plan` "cancel rolls back" requirement against the in-memory + transactional behavior.

### Cancel-during-ingest hardening

- [X] T028 Extend [src/rag/ingest/pipeline.py](../../src/rag/ingest/pipeline.py)'s `ingest_pdf_core` to accept an optional `cancel_check: Callable[[], Awaitable[bool]] | None = None` parameter. When supplied, the pipeline awaits `cancel_check()` at three checkpoints: (a) after `extract_pages_via_gemini` returns, (b) between each `gemini.embed` batch, (c) before the final `repo.add_chunks` call. If `cancel_check()` returns True, raise `UploadCancelledError(phase=<checkpoint_name>)`. The CLI's `ingest_pdf` wrapper passes `cancel_check=None` so it never polls — only the upload route uses the checkpoints.
- [X] T029 Wire the cancel-check into [src/rag/ui/routes.py](../../src/rag/ui/routes.py)'s upload route (refining T019 step 10): pass `cancel_check=request.is_disconnected` to `ingest_pdf_core`. The handler catches `UploadCancelledError`, logs `upload_cancelled` with the phase, and exits the `async with transaction` block — which rolls back automatically. No response is sent because the client has already disconnected.

### Integration tests

- [X] T030 Write [tests/integration/test_upload_live.py](../../tests/integration/test_upload_live.py) gated by `RUN_INTEGRATION=1`. Cases against the real pgvector store: (a) replace-rollback under a fault-injected embedding failure — wrap the real `GeminiProvider.embed` with a stub that raises on the second batch; POST a replace; verify after the response that the prior corpus row counts and ids are observably identical to pre-upload (this is the strict-rollback verification at the SQL layer); (b) append + dedup on identical bytes against the real DB — confirms the `source_document.file_hash` UNIQUE + chunk composite UNIQUE behave as expected through the new route.

### README & docs

- [X] T031 [P] Update [README.md](../../README.md): add a "Uploading PDFs from the UI" section under the existing "Ingest" section. Document the paperclip → file picker → confirmation → outcome flow with a screenshot placeholder (or omit the screenshot if no design pass is in scope per the accessibility deferral). Document `RAG_MAX_UPLOAD_BYTES` env var. Per FR-026.
- [X] T032 [P] Update [.specify/memory/constitution.md](../../.specify/memory/constitution.md)'s sync-impact block? **No** — this feature does not amend the constitution. The Article VII deviation is recorded only in `plan.md → Complexity Tracking`. No commit to the constitution file is required.

### Quickstart validation

- [X] T033 Run through [quickstart.md](./quickstart.md) end-to-end on a fresh `make up`: empty-corpus upload → query → replace upload → query → append upload → query against both. Confirm every step works as described. Update quickstart.md if any wording is stale.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup. Blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational. Ships the headline replace flow + the full upload surface (UI + route + templates). This is the MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational + Phase 3 (the route + templates from US1 are reused; US2 adds append-specific tests and verifies the dedup branch).
- **User Story 3 (Phase 5)**: Depends on Foundational + Phase 3. Verification-only; the empty-corpus branch is in US1's route handler.
- **Polish (Phase 6)**: Depends on all desired stories being complete.

### User-story independence note

US2 and US3 depend on US1's route + template artifacts. This is by design — the spec's user stories naturally share the upload surface, and splitting the route handler across stories would create a parallel-implementation footgun (the same issue feature 002 noted for its query pipeline). The "independent test" criterion is still satisfied: each story has a distinct independent test plan that exercises its specific behavior on the shared surface.

### Within each user story

- Tests are written first; verify they fail before implementing.
- Foundational repository surface (T004–T009) lands before the route handler depends on it.
- Templates (T015–T018) can land in parallel with each other but must precede the route handler (T019) since the handler references them by filename.
- `base.html` modification (T013) and `styles.css` updates (T014) are independent files and can run in parallel.
- The route handler (T019) is the single sequential bottleneck in US1 implementation; it imports symbols from all the foundational pieces.

### Parallel opportunities

- All Setup tasks marked [P] (T002, T003) can run in parallel.
- All Foundational tasks marked [P] (T005, T006, T008, T009) can run in parallel after T004 lands.
- All US1 template tasks (T014, T015, T016, T017, T018) can run in parallel.
- US1 tests (T010, T011, T012) can run in parallel (different test files).
- US2 test (T021) and US3 test (T023) can run in parallel once Phase 3 is complete.
- All Polish tests (T024, T025, T026, T027) can run in parallel.
- README + quickstart-validation (T031, T033) can run in parallel.

---

## Parallel Example: User Story 1 Implementation

```bash
# After Phase 2 (foundational) completes, launch US1 template work in parallel:
Task: "Create _upload_confirm.html template at src/rag/ui/templates/_upload_confirm.html"
Task: "Create _upload_success.html template at src/rag/ui/templates/_upload_success.html"
Task: "Create _upload_error.html template at src/rag/ui/templates/_upload_error.html"
Task: "Create _upload_cancelled.html template at src/rag/ui/templates/_upload_cancelled.html"
Task: "Extend src/rag/ui/static/styles.css with paperclip + upload-panel rules"

# In parallel, write US1 tests so they fail and pin the contract:
Task: "Write tests/unit/test_upload_replace.py"
Task: "Write tests/unit/test_upload_replace_rollback.py"
Task: "Write tests/unit/test_upload_route_dispatch.py"

# Sequentially after the above:
Task: "Modify base.html to add paperclip + hidden upload form (single file)"
Task: "Implement POST /ui/upload in src/rag/ui/routes.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories).
3. Complete Phase 3: User Story 1 — replace flow ships with the full upload UI + route + templates.
4. **STOP and VALIDATE**: A reviewer can upload via the paperclip, choose Replace, get a queryable new corpus. The append + empty-corpus paths technically work too (since the route handles them) but aren't verified by tests yet.
5. Demo-ready.

### Incremental delivery

1. Setup + Foundational → foundation ready.
2. Add US1 → Test → **demo MVP** (replace flow + working upload UI).
3. Add US2 → Test → demonstrate multi-document append + dedup messaging.
4. Add US3 → Test → demonstrate first-upload-without-confirmation.
5. Polish → cross-cutting tests + cancel-during-ingest hardening + README.

### Parallel team strategy

Most of this feature is single-threaded (one route handler, one base template). The parallel opportunities are mostly within the template-creation step (T014–T018) and the test-writing step (T010–T012, T021, T023, T024–T027). For a solo developer, the natural ordering above is appropriate.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete same-phase tasks.
- [Story] label maps task to specific user story for traceability.
- Tests are required (per spec FR-025); verify each fails before implementing the behavior it covers.
- Commit after each task or logical group; the after_tasks hook offers an optional auto-commit.
- Stop at the Phase 3 checkpoint to validate US1 (the MVP) independently before continuing.
- Avoid: extending the upload route's handler signature in ways that diverge from `contracts/upload.md`; splitting the route across files (one handler, one location); adding accessibility infrastructure (deferred per user input).
