# Phase 0 Research: PDF Upload from the Web UI

**Feature**: [003-pdf-upload-ui](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-05-12

## Scope

Resolve every implementation-level unknown the spec leaves open (the spec is the WHAT; this file is the HOW). Where the user supplied additional constraints via `/speckit-plan` input ("paperclip in the textarea", "skip accessibility", "UI cancel rolls back the DB"), those are recorded here as Phase 0 decisions rather than back-edited into the spec — the spec stays clean as the contract; this file binds the implementation.

Each decision below carries: **Decision**, **Rationale**, **Alternatives considered**.

---

### R-001 — Paperclip icon placement inside the question textarea

**Decision**: An overlay button (`<label>` element) is absolute-positioned inside a `<div class="textarea-wrap">` that contains the existing `<textarea name="question">`. The label is bound to a **hidden `<input type="file" name="pdf" accept="application/pdf">`** that lives in a **separate, hidden upload form** (`<form id="upload-form" hx-post="/ui/upload" hx-encoding="multipart/form-data" hx-target="#response">`). Clicking the paperclip opens the OS file picker via the native `<label for=...>` mechanism. On `change`, the file input fires an `htmx:trigger`-bound JS one-liner (`this.form.dispatchEvent(new Event('submit'))`) that submits the upload form. The question form (`<form hx-post="/ui/query">`) remains a separate form to keep query and upload semantics distinct.

**Rationale**:
- Two-form pattern keeps the existing query path completely unchanged (FR-022, FR-023). The `<textarea>` element stays in its current form; only the visual container around it is new.
- Native `<label for="...">` opens the file picker without any JavaScript. Only the auto-submit-on-change handler is JS, and it's one line.
- Single `<input type="file">` element keeps file state in the DOM across the two-POST confirmation flow (R-008): after the first POST returns a confirmation partial, the file is still mounted in the upload form and re-submits cleanly via `hx-include="#upload-form"` on the confirmation buttons.
- The accessibility deferral (per user `/speckit-plan` input) means we don't pursue a keyboard-discoverable file-selector pattern beyond the default `<label>` click behavior. The native label IS keyboard-focusable, but no ARIA-label-for-screen-readers work is in scope.

**Alternatives considered**:
- **Single combined form** with both `textarea` and file input. Rejected: would require the server to branch on "is `pdf` field present" vs "is `question` field present", muddying two clean endpoints (`/ui/query`, `/ui/upload`). Also breaks the `hx-post` symmetry feature 002 already has.
- **Drag-and-drop zone** (HTML5 file drop on the textarea). Rejected: explicitly out of scope per spec ("Out of scope: ... drag-and-drop UX"). A drop zone is also visually heavier than a paperclip.
- **Separate full-width upload widget below the textarea**. Rejected: user's `/speckit-plan` input explicitly asks for paperclip-in-textarea placement.
- **JS-built modal file picker**. Rejected: no JS framework is available, and a modal contradicts the spec's inline-confirmation decision (Q3).

---

### R-002 — Upload form structure and the two-POST flow

**Decision**: A single `<form id="upload-form">` carries the file input. The first POST (file selected → form auto-submits) hits `POST /ui/upload` with multipart `pdf` and **no `action` field**. Server inspects the corpus state and returns one of:
- **Empty corpus**: proceeds with ingest immediately, returns `_upload_success.html` or `_upload_error.html`.
- **Non-empty corpus**: returns `_upload_confirm.html` — a partial swapped into `#response` containing Replace / Append / Cancel buttons.

Each confirmation button in `_upload_confirm.html` uses `hx-post="/ui/upload"` with `hx-include="#upload-form"` and `hx-vals` to add `action=replace` (or `append`, or `cancel`). The form's file input is still in the DOM and gets re-submitted with the button's POST. The server validates the file again on the second POST (FR-013 explicit re-validation).

**Rationale**:
- Matches the FR-013 contract: "the file MUST be present in the second POST" and "the server MUST re-validate it before any database mutation."
- Single endpoint serves both the initial submit and the confirmed-action submit, keyed off the presence/absence of the `action` field. The route handler dispatches on `action`: missing → return confirm partial (or proceed if empty corpus); `replace`/`append` → execute; `cancel` → return a small "upload cancelled" partial.
- HTMX's `hx-include` re-serializes the upload form's data, including the file. This is documented behavior for HTMX 2.x; the form retains the file across UI re-renders as long as the `<input type="file">` element is not replaced.

**Alternatives considered**:
- **Server-side session storage of uploaded bytes between POSTs**. Rejected: explicitly forbidden by FR-013 ("the server MUST NOT rely on per-session storage of the uploaded bytes between the two requests"). Also requires a session layer we don't have.
- **Skip confirmation if a query string flag is set**. Rejected: violates FR-010 (no implicit defaults; affirmative selection required).
- **Two endpoints `/ui/upload/stage` and `/ui/upload/commit`**. Rejected: two endpoints would either need a server-side stash (forbidden) or would require the client to resubmit the file anyway, in which case one endpoint with an `action` discriminator is simpler.

---

### R-003 — Process-wide concurrent-upload guard

**Decision**: A single `asyncio.Lock` stored on `app.state.upload_lock` (assigned during the existing `lifespan` startup). The upload route checks `app.state.upload_lock.locked()` **before** acquiring it; if already held, returns 409 immediately with an `_upload_error.html` partial naming the cause `concurrent_upload`. If not held, acquires via `async with app.state.upload_lock:` for the full upload duration (including the confirmation round-trip if applicable).

**Rationale**:
- The spec's FR-028 requires "process-wide (not per-request-handler) so concurrent requests across worker threads are caught." A single `asyncio.Lock` on `app.state` is process-wide and correctly serializes async tasks within one Uvicorn worker.
- Uvicorn's default for the local-dev stack is a single worker (`--workers 1` implied by `rag serve`). Multi-worker is out of scope per Art VII / spec assumptions. If a future deployment runs multiple workers, the lock would need to upgrade to a Postgres advisory lock — flagged here so future-us doesn't silently regress, but **not implemented** now (YAGNI per CLAUDE.md guidance against speculative over-engineering).
- The `locked()` pre-check is non-blocking and immediate, so the second uploader sees a 409 in milliseconds rather than waiting for the first upload to complete.

**Alternatives considered**:
- **Postgres advisory lock** (`pg_try_advisory_lock`). Rejected for now: adds a round-trip to the DB on every upload start; the in-process lock is sufficient for the single-worker demo deployment. Promoted to a "future work" note in `quickstart.md`.
- **Database row flag** (`source_document.ingesting_now BOOLEAN`). Rejected: schema change for a behavior the in-memory lock handles perfectly at our scale.
- **Optimistic / no guard, rely on transaction conflicts to surface the race**. Rejected: replace conflicts would manifest as confusing errors (FK violations, deadlocks) rather than the clean 409 the spec mandates.

---

### R-004 — Transactional wrapping for the replace flow

**Decision**: The replace path opens a single psycopg 3 async connection from the pool, calls `async with conn.transaction():` around BOTH `delete_all_source_documents()` AND the entire `ingest_pdf` pipeline. The repository methods are refactored to accept an externally-provided connection (a thin layering change: the existing methods that acquire-their-own-connection get a new `connection: Connection | None = None` parameter that falls through to the pool if `None`). All DELETE / INSERT statements inside the transaction commit atomically on `__aexit__` or roll back on any exception (including `asyncio.CancelledError`).

For the append flow, the same connection-passing pattern is used so the entire append also runs in a single transaction — but the transaction wraps only INSERTs, since append doesn't delete anything.

**Rationale**:
- Matches spec FR-019's strict-rollback requirement: "the clear-step and the ingest MUST execute inside the same transactional boundary, and any failure inside that boundary MUST roll back both the clear and any partial inserts."
- Postgres MVCC means concurrent SELECTs (queries via `/ui/query` or `/query`) see the pre-DELETE state for the duration of the open transaction. The moment the transaction commits, they see the post-INSERT state. There is no observable half-cleared corpus — this satisfies FR-016's "concurrent query never observes a half-cleared corpus" requirement automatically; no application-level locking is required for read isolation.
- The transaction's lifetime is bounded by the SC-001 budget (under 3 minutes for a 50-page PDF). During this time, the transaction holds row-level locks on the deleted `source_document` rows and on the newly-inserted ones, but no table-level locks — concurrent reads are unaffected. Concurrent writes are already prevented by the upload lock (R-003).
- Wrapping append in a transaction (even though it's append-only) gives us free atomicity on the cancel-during-ingest path (R-005): if the user cancels mid-append, the partial chunks roll back cleanly.

**Alternatives considered**:
- **Snapshot-and-swap** (write new chunks under a "staging" source_document, then atomically swap by deleting the old ones). Rejected: more complex, requires an additional `is_staging` column or transactional juggling, and the long-transaction concern (the embedding API calls are slow) is the only thing it solves — but for our single-user local-dev demo, holding a transaction open for 3 minutes is fine.
- **Two separate transactions** (delete-then-ingest, with manual compensation on failure). Rejected: compensation is brittle (what if the compensating DELETE itself fails?), defeats the simplicity goal, and Postgres gives us atomic multi-statement transactions for free.
- **Implicit autocommit per repository call** (current state). Rejected: explicitly disallowed by FR-019. The whole point of strict-rollback is to coordinate multiple writes atomically.

---

### R-005 — Cancel-during-ingest behavior

**Decision**: Per user `/speckit-plan` input ("if UI cancel, then backend cancel and rollback db"). The cancel pathway has two surfaces:

1. **Cancel-during-confirmation** (already covered by FR-012 — pre-action): clicking the Cancel button in `_upload_confirm.html` issues `POST /ui/upload` with `action=cancel`. The server returns a small "upload cancelled" partial and does no DB work. No transaction was open, so no rollback is needed.

2. **Cancel-during-ingest** (NEW — extends FR-012 implicit semantics): once the user has confirmed Replace or Append, the response partial includes a Cancel button (in addition to the spinner) that calls `htmx.abort(htmx.find('#upload-form'))` to abort the in-flight HTMX request. The server-side handler polls `await request.is_disconnected()` at three checkpoints: (a) after `delete_all_source_documents` returns (replace path only), (b) after each embedding batch completes, (c) before the final `add_chunks` call. If disconnected at any checkpoint, raises `UploadCancelledError`. The open `async with conn.transaction():` block catches the exception, rolls back, and the client (already disconnected) receives nothing — but the database is observably identical to its pre-upload state.

**Rationale**:
- The user explicitly requested this behavior. It also tightens the spec's behavior beyond what FR-012 strictly requires (FR-012 only covers the pre-confirmation cancel; mid-ingest cancel was previously implicit in the "browser tab closes mid-upload" edge case).
- `request.is_disconnected()` is the FastAPI/Starlette standard mechanism for detecting client disconnect. It does not poll automatically — handler code must check it. Polling at natural pipeline checkpoints (not in a tight loop) keeps overhead negligible.
- The transaction rollback is automatic: psycopg 3 async's `Transaction.__aexit__` rolls back if the body raised any exception. `asyncio.CancelledError` and our custom `UploadCancelledError` both qualify.
- For the UI side: HTMX 2.x supports `htmx.ajax`'s abort signal via the underlying `AbortController`. Triggering `htmx:abort` on the form (or calling `xhr.abort()` directly via stashed reference) closes the connection. We expose this via a small inline JS handler on the Cancel button.

**Alternatives considered**:
- **No mid-ingest cancel** (let the spec's tab-close edge case cover it implicitly). Rejected: user explicitly requested an explicit cancel.
- **Server-side timer / external cancel queue**. Rejected: requires a separate channel for the client to send "cancel signal X for upload Y"; far more machinery than the disconnect-poll approach for the same outcome.
- **`asyncio.shield` around the transaction** to make it uncancellable. Rejected: that's the *opposite* of what the user asked for. We *want* cancellation to propagate so the transaction can roll back.

---

### R-006 — PDF magic-header validation

**Decision**: At the top of the route handler (before any DB or Gemini work), read the first 5 bytes of the upload via `header = await upload.read(5)`. Validate `header == b"%PDF-"` (the PDF specification's required magic). If invalid, return `_upload_error.html` with cause `invalid_pdf` and HTTP 400. If valid, call `await upload.seek(0)` to rewind the spooled buffer before passing to the ingest pipeline.

**Rationale**:
- Matches spec FR-014: "Validation MUST NOT rely solely on the filename extension — it MUST inspect the file's content (e.g., the PDF magic header)."
- Five bytes is enough — `%PDF-` is the canonical magic per ISO 32000-1 §7.5.2. Some PDFs have leading whitespace or a BOM before the magic; per the standard those are non-conforming but tools accept them. For our demo PDFs (assessment PDF + `data/sample.pdf` + reviewer-supplied), strict magic-at-byte-0 is sufficient and avoids tolerating malformed inputs.
- `UploadFile.read(n)` does not consume the entire upload — it reads only `n` bytes from the spooled buffer. The `seek(0)` rewinds it for downstream consumption.

**Alternatives considered**:
- **Trust the `Content-Type` header**. Rejected: explicitly disallowed by FR-014 (the spec's "renamed non-PDF cannot reach the extractor" requirement).
- **Use a heavier MIME-sniffing library** (`python-magic`, `filetype`). Rejected: adds a system dependency (`libmagic`) for a five-byte check.
- **Defer validation to Gemini extraction**. Rejected: Gemini would happily accept a non-PDF and either succeed with garbage extraction or fail with an opaque error. Validating at the boundary keeps errors actionable and avoids wasting a Gemini call.

---

### R-007 — Upload-size cap enforcement

**Decision**: Read the configured cap from `settings.RAG_MAX_UPLOAD_BYTES` (default `26214400` = 25 MiB, per spec FR-015 / clarification Q2). At route entry, after PDF-magic validation, check `upload.size` against the cap. If `upload.size > cap`, return `_upload_error.html` with cause `oversize` and HTTP 413, including both the cap in bytes and a `cap / 1024 / 1024` MB rendering for the reviewer-readable rejection message.

**Rationale**:
- Matches FR-015: cap is enforced before any extraction or embedding work; rejection names the cap in both bytes and megabytes.
- Starlette's `UploadFile.size` is populated from the multipart parser once the body has been read. For requests that exceed the cap, we still incur the cost of receiving the bytes; this is acceptable on local-dev (loopback is fast) and the alternative — Content-Length pre-check — is unreliable because not all clients send it accurately.
- The cap default of 25 MiB is stricter than the "25 MB" wording in the spec (which is decimal MB). Using MiB (binary) is more conventional for HTTP body limits; the discrepancy (~0.5 MB) doesn't materially affect SC-001's 50-page-PDF reality. Documented in `quickstart.md` so reviewers know.

**Alternatives considered**:
- **Reject via Content-Length header before reading the body**. Rejected: not all clients (especially HTMX through some proxies) send accurate Content-Length. Reading the body and checking actual size is more robust.
- **Reverse-proxy-level limit** (Nginx `client_max_body_size`). Rejected: the demo stack doesn't run a reverse proxy. If a future deployment adds one, both layers should enforce — defense in depth — but the route-level check is the authoritative one for now.
- **Stream-and-truncate** (read up to cap+1, reject if extra). Rejected: starlette already buffers the upload to a spooled temp file, and `upload.size` is available without extra plumbing.

---

### R-008 — Inline confirmation partial structure

**Decision**: `_upload_confirm.html` is a small Jinja partial swapped into `#response` after the first POST. Structure:

```html
<div class="upload-confirm" role="region">
  <h3>Confirm upload action</h3>
  <p>File: <strong>{{ filename }}</strong> ({{ size_mb }} MB)</p>
  <p class="warning">The knowledge base already contains {{ doc_count }} document(s).
    Choose how to handle this upload:</p>
  <button hx-post="/ui/upload" hx-include="#upload-form"
          hx-vals='{"action": "replace"}' hx-target="#response"
          hx-indicator="#thinking">
    Replace existing — clears all current documents (cannot be undone)
  </button>
  <button hx-post="/ui/upload" hx-include="#upload-form"
          hx-vals='{"action": "append"}' hx-target="#response"
          hx-indicator="#thinking">
    Add to existing — preserves current documents
  </button>
  <button hx-post="/ui/upload" hx-include="#upload-form"
          hx-vals='{"action": "cancel"}' hx-target="#response">
    Cancel
  </button>
</div>
```

The Replace button copy makes the consequence explicit (FR-009: "in plain language, the consequence of each option ... that replace will delete all currently-ingested documents and cannot be undone").

**Rationale**:
- Server-rendered partial fits the existing HTMX pattern feature 002 established (`_answered.html`, `_refused.html`, `_no_documents.html`, `_error.html`).
- `hx-include="#upload-form"` is the HTMX mechanism for pulling additional form data (the file) into a request originated from outside that form.
- The "cancel" path goes through the server (rather than a pure client-side undo) so the server can clear any per-request state and emit a structured log record for observability (FR-020).

**Alternatives considered**:
- **Pure-client cancel** (just remove the partial from the DOM via `hx-on::click`). Rejected: the server should log the cancel event for FR-020. Round-trip cost is negligible.
- **Confirmation as a dialog/modal**. Already rejected by clarification Q3.
- **Pre-check buttons** (radio + "Confirm" button). Rejected: extra click for the reviewer; FR-010's "explicit affirmative selection" is satisfied by the dedicated buttons.

---

### R-009 — Logging extension

**Decision**: Add `upload_*` events to the existing structured-logging setup. All events carry `trace_id` (a new one is minted at upload-request entry, propagating through every downstream call). Event names (alphabetical):

- `upload_received` — entry, includes filename and reported content-type.
- `upload_validated` — magic header passed.
- `upload_rejected_invalid_pdf` — magic header failed.
- `upload_rejected_oversize` — cap exceeded.
- `upload_rejected_concurrent` — lock held, 409 returned.
- `upload_action_chosen` — second POST received with `action=replace|append|cancel`.
- `upload_clear_complete` (replace only) — `delete_all_source_documents` finished, includes deleted document count.
- `upload_cancelled` — disconnect detected mid-flight; includes the pipeline phase the cancel was caught at.
- `upload_complete` — happy path; includes filename, file_hash, action, chunks_inserted, elapsed_s.
- `upload_failed` — error path; includes failure cause and elapsed_s.

These events are subsetted into FR-020's required list: upload received, validation outcome, action chosen, clear outcome (replace), ingest start/end (already emitted by the existing ingest pipeline, carrying the same `trace_id`), final outcome with elapsed time.

**Rationale**:
- Matches the structured-logging pattern feature 002 already uses (`extra={TRACE_LOG_KEY: trace_id, ...}` with stdlib `logging` + JSON formatter).
- `trace_id` propagation enables end-to-end correlation in JSON logs — the same property Art VI.4 requires for queries (feature 002).
- One log per state transition keeps log volume manageable; per-page or per-batch logging within the existing `ingest_pdf` pipeline is already configured and propagates naturally.

**Alternatives considered**:
- **Print statements / unstructured logs**. Rejected by constitution Art VI.4.
- **OpenTelemetry spans / external tracing**. Rejected by constitution Art VII (production observability out of scope).

---

### R-010 — Test strategy

**Decision**: Hermetic unit tests using `InMemoryChunkRepository` (already implemented for feature 002) and `FakeGeminiProvider` / `FakeEmbedder`. Each FR-025 category gets at least one test; the two clarification-driven categories (concurrent-upload, cancel-during-ingest) get dedicated tests. Integration tests under `tests/integration/test_upload_live.py` (gated by `RUN_INTEGRATION=1`) cover the real-pgvector transactional behavior, including a fault-injected embedding failure mid-replace to verify rollback.

**Rationale**:
- The hermetic boundary feature 002 set up (`ChunkRepository` interface + in-memory implementation) makes route-level tests fast and deterministic.
- The strict-rollback property requires a real transactional store to test meaningfully; the integration test is what gives confidence that FR-019 actually holds against pgvector, not just against a Python-level mock.
- The cancel-during-ingest test simulates client disconnect by raising `RequestDisconnected` from a faked `request.is_disconnected()` and verifies that no rows were committed.

**Alternatives considered**:
- **End-to-end Playwright/Selenium tests through the browser**. Rejected: outside the test-tier complexity budget for an assessment-scale codebase; the route-level tests + manual smoke from `quickstart.md` are sufficient.
- **Property-based testing of the action discriminator**. Rejected: only three valid `action` values; no combinatorial space worth exploring.

---

## Open items for `/speckit-tasks`

These are decisions intentionally **not** made here, because they're closer to "what gets written in which file" than "what behavior do we want":

- Exact module layout for the new route handler (inlined in `routes.py` vs new `src/rag/ui/upload.py`).
- Exact connection-passing signature for the refactored repository methods.
- Whether `UploadCancelledError` lives in `rag.ui` or `rag.errors`.
- Exact CSS class names for the paperclip overlay and confirm partial.

These flow naturally from the decisions above and are best owned by the task-decomposition step.
