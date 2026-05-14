# Implementation Plan: PDF Upload from the Web UI

**Branch**: `003-pdf-upload-ui` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-pdf-upload-ui/spec.md`

## Summary

Surface the existing ingest pipeline through the web UI. A paperclip icon overlaid on the question textarea opens the OS file picker; selecting a PDF auto-submits an upload form to a new `POST /ui/upload` route. If the corpus is non-empty, the server returns an inline confirmation partial (Replace / Append / Cancel) that re-submits the *same* form (with the file still mounted in the DOM) carrying an `action` field. Replace runs `DELETE FROM source_document` then the existing ingest pipeline inside a **single psycopg 3 async transaction**, so any failure — including a client-initiated cancel — rolls back atomically and the prior corpus is observably preserved (spec FR-019 strict-rollback). Append calls the existing `ingest_pdf` core unchanged inside its own transaction. A process-wide `asyncio.Lock` on the FastAPI app state implements the 409-Conflict reject for concurrent uploads (spec FR-028). During an in-flight ingest, the UI shows a Cancel button that aborts the HTMX request; the handler polls `request.is_disconnected()` at natural pipeline checkpoints (after page extraction, between embedding batches, before persistence) and raises `UploadCancelledError`, which the open transaction catches and rolls back. No new database migrations; no new persisted entities; no change to the query/citation path.

## Technical Context

**Language/Version**: Python 3.12 (unchanged from features 001/002; constitution Art IV.1).

**Primary Dependencies**: No new top-level dependencies. The feature reuses:
- `fastapi` + Starlette's `UploadFile` for multipart upload handling (streamed to a spooled temp buffer; no full-file memory load before validation).
- `python-multipart` (already in `pyproject.toml` from feature 002; FastAPI requires it for `Form()` / `File()` parsing).
- `jinja2` for new HTML partials (`_upload_confirm.html`, `_upload_success.html`, `_upload_error.html`).
- The existing `google-genai`-backed `GeminiProvider.embed` / `extract_pages_via_gemini` paths — the upload route calls into the same `rag.ingest.pipeline` code that `rag ingest <path>` uses (spec FR-017 / FR-022).
- HTMX 2.0.3 (already pinned in `base.html` from feature 002) for `hx-encoding="multipart/form-data"` and `hx-include` patterns.

**Storage**: Postgres 16 + pgvector, schema unchanged. Migrations `0001_init_vector_store.sql` (feature 001) and `0002_query_path.sql` (feature 002) provide everything we need:

- `source_document.file_hash` UNIQUE — drives append-side dedup (FR-018 / Feature 002 FR-004). Same SHA-256 of uploaded bytes; the ingest pipeline already short-circuits to `status="already_done"` when the hash exists.
- `chunk.source_document_id` FK `ON DELETE CASCADE` — drives replace-side clearing (FR-016). A single `DELETE FROM source_document` cascades to all chunks.
- Composite `chunk` UNIQUE on `(source_document_id, page_number, char_offset_start, char_offset_end)` — second-layer dedup defense.

**Testing**: Two-tier carried forward from feature 002. New unit tests (hermetic, fake providers + in-memory repository): replace-success, replace-rollback-on-embedding-failure, append-success, append-no-new-content (dedup), empty-corpus-no-confirm, concurrent-upload-409, non-PDF-rejection, oversize-rejection, cancel-during-confirmation (DB unchanged), cancel-during-ingest (DB rolled back). New integration tests (`RUN_INTEGRATION=1`): real-pgvector replace with rollback on simulated mid-transaction failure; real-pgvector append + dedup. Covers all six FR-025 categories.

**Target Platform**: Linux containers on the developer's Docker Desktop / Docker Engine, same as feature 002. No new host-side networking requirements.

**Project Type**: Single project. Continues the feature 001/002 layout — the upload endpoint is one new route on the existing FastAPI service, not a new compose service (matches spec's "delivered as HTMX route(s) on the existing FastAPI app" assumption).

**Performance Goals**:
- Spec SC-001: upload-via-UI with replace → queryable in under 3 minutes for a 50-page PDF. Same budget as `rag ingest <path>` CLI; the underlying pipeline is identical.
- Spec SC-006: clone-to-rendered-answer via UI under 5 minutes (empty-corpus path).
- Upload-specific latency target: PDF-magic-header validation and size-cap check MUST complete in under 100 ms so a bad upload errors out before any Gemini call. (Not surfaced in a spec SC; an implementation budget.)

**Constraints**:
- **25 MB default upload cap** (spec FR-015, clarification Q2). Env-var name: `RAG_MAX_UPLOAD_BYTES` (default `26214400`).
- **Strict rollback on replace failure** (spec FR-019, clarification Q1) — implemented as a single psycopg 3 async transaction wrapping clear-then-ingest.
- **Inline two-step confirmation in the response region** (spec FR-008, clarification Q3) — not a modal, not a separate page.
- **409 Conflict on concurrent upload** (spec FR-028, clarification Q4) — process-wide `asyncio.Lock` on the FastAPI app state.
- **Cancel during ingest rolls back the DB** (user `/speckit-plan` input, R-005) — handler polls `request.is_disconnected()`; open transaction catches `CancelledError` / `UploadCancelledError` and rolls back.
- **No streaming responses** (constitution Art VII) — upload result is returned whole; the HTMX spinner covers the latency.
- **Accessibility deferred** (user `/speckit-plan` input) — no ARIA labels, keyboard-navigation polish, or screen-reader testing added beyond what feature 002 already had. The minimal-UI stance from feature 002 continues.

**Scale/Scope**: Single user, single tab in the typical flow. The concurrent-upload guard catches the multi-tab pathological case. No queueing, no background workers, no progress streaming — the spinner is enough for the demo's reviewer.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution: `Nymbl RAG Assessment Constitution` v1.0.3 (amended 2026-05-12 to repin Art IV.5 embedding model to `gemini-embedding-001` with `output_dimensionality=768`).

| Article | Title | Status | Evidence / Note |
|---------|-------|--------|-----------------|
| I | Grounding Is Non-Negotiable | **PASS** | Feature 003 does not touch retrieval, generation, or the grounding judge. The query path is byte-identical to feature 002's. The upload flow's failure modes (cancel, rollback) preserve the invariant: a corpus is never in a half-state where queries could return less-grounded answers than before the upload. FR-019 (strict rollback) makes this contractual. |
| II | Citations Carry Real Provenance | **PASS** | Uploaded PDFs go through the same `ingest_pdf` pipeline as CLI-ingested ones (FR-017 / FR-022 / spec assumption "the ingest code path is the single source of truth"). Provenance fields are populated identically; citations from upload-ingested PDFs are structurally indistinguishable from CLI-ingested ones (FR-023). |
| III | Evaluation Before Demo | N/A this feature | The eval harness remains an outstanding deliverable (originally slated for feature 003 per feature 002's plan; that slot was reused for this UI work). The eval harness will need to land in a subsequent feature before final submission — flagged here so it doesn't get lost. The committed `data/sample.pdf` + the upload UI together make the eval harness easier to author when it lands. |
| IV | Stack Decisions Are Fixed | **PASS** | All Art IV pins inherited unchanged: Python 3.12 + uv ✓, FastAPI + Pydantic v2 ✓, Postgres 16 + pgvector ✓, Gemini File API for extraction ✓, `gemini-embedding-001` with `output_dimensionality=768` ✓, Gemini 2.5 Flash for generation ✓, docker compose unchanged ✓. The feature 002 declared deviation (Art IV.6 — grounding judge on a local OpenAI-API-compatible LLM) is **inherited unchanged**; feature 003 doesn't touch the judge. |
| V | Developer Experience | **PASS** | `make up` unchanged. README updated per FR-026 to document the upload flow. `.env.example` extended with `RAG_MAX_UPLOAD_BYTES`. No new CLI commands. The existing `rag ingest <path>` flow continues to work (FR-022). |
| VI | Code Quality Floor | **PASS** | Ruff + type hints carried forward (FR-024). The six FR-025 test categories (replace, append, empty-corpus, cancel-confirm, non-PDF, oversize) plus the two clarification-driven categories (concurrent-upload reject, cancel-during-ingest rollback) are all covered. Structured logging extends to upload events (FR-020) — every upload carries a `trace_id` through the same logging infrastructure feature 002 set up. |
| VII | Scope Discipline | **DEVIATION** — see Complexity Tracking | Feature 003 introduces user-driven multi-document corpora via the **append** flow. Article VII lists "Multi-document corpora or collections" as out-of-scope. Justification recorded in Complexity Tracking; the deviation is bounded (no per-document query filtering, no corpus-management UI, no multi-collection support — just additive ingest of one PDF at a time). |
| VIII | The Demo Is the Product | **PASS** | This feature directly improves the demo: a reviewer can swap PDFs without dropping back to the terminal (SC-006). README + slide-deck artifacts (Art VIII.5) will need a short update to mention the upload flow; the 30-minute demo budget (Art VIII.6) is unchanged. |

**Gate result**: **PASS with one declared deviation** (Art VII — user-driven multi-document via append). The deviation is justified inline per the same Art IV.8 pattern feature 002 used for its grounding-judge deviation, recorded in Complexity Tracking below, and bounded (no per-document filtering, no collection management — additive ingest only). All other articles pass without conditions.

**Post-Phase-1 re-check (2026-05-12)**: Re-evaluated after `research.md`, `data-model.md`, `contracts/`, and `quickstart.md` were written. No new violations surfaced. The Art VII deviation remains the single declared violation; the Phase 1 design (transactional replace, lock-based concurrent reject, disconnect-driven cancel) does not introduce any new tension with Art I, II, IV, or VI. Gate: still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/003-pdf-upload-ui/
├── plan.md              # This file
├── research.md          # Phase 0 — resolved decisions for this feature's layer
├── data-model.md        # Phase 1 — schema unchanged; transactional boundary documented
├── quickstart.md        # Phase 1 — developer walkthrough (clone → make up → upload via UI)
├── contracts/
│   ├── upload.md        # HTTP contract for POST /ui/upload (multipart + actions)
│   └── ui.md            # Updated UI surface (paperclip placement, confirmation partial, cancel)
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # NOT created here — /speckit-tasks output
```

### Source Code (repository root)

Exact file layout and module boundaries are intentionally **deferred to `/speckit-tasks`**. This feature adds:

- **Upload route**: a new `POST /ui/upload` HTMX endpoint registered alongside `POST /ui/query` in `src/rag/ui/routes.py`. Accepts multipart with `pdf` file and optional `action` (`replace` | `append`).
- **Templates**: new partials `_upload_confirm.html` (Replace/Append/Cancel), `_upload_success.html` (filename + chunk count + action label), `_upload_error.html` (reviewer-readable cause). Modified `base.html` to add the paperclip-overlay markup and a hidden upload form.
- **Static styles**: `src/rag/ui/static/styles.css` gains `.textarea-wrap`, `.paperclip-btn`, and upload-result panel rules. Visual styling intentionally minimal (no design system).
- **Repository**: new method `delete_all_source_documents()` on `ChunkRepository` (base + pgvector + in-memory). pgvector implementation issues `DELETE FROM source_document` — chunks cascade via the existing FK.
- **Pipeline**: a transactional wrapper around `ingest_pdf` that supports both append (existing path, in its own transaction) and replace (clear-all + ingest in a single transaction). The wrapper accepts a connection so the route handler owns the transaction lifecycle.
- **Concurrency**: a single `asyncio.Lock` stored on `FastAPI.state` (assigned in the existing lifespan setup). The upload route acquires it non-blocking via `lock.locked()` check before any work; if held, returns 409 immediately.
- **Cancellation**: `UploadCancelledError` exception type; the route handler polls `await request.is_disconnected()` between pipeline checkpoints. Raises through the open transaction context to trigger rollback.
- **Validation**: a small `rag.ingest.pdf_validate` module (or inlined in the route) that reads the first 5 bytes via `await upload.read(5)`, validates `b"%PDF-"`, then `await upload.seek(0)`. Size cap enforced via Starlette's `UploadFile` size check before any extraction call.
- **Logging**: extension to the existing structured-logging setup — `upload_received`, `upload_validated`, `upload_action_chosen`, `upload_clear_complete`, `upload_complete`, `upload_failed`, `upload_cancelled` events, all carrying `trace_id`.
- **Tests**: under `tests/unit/` and `tests/integration/`, covering all six FR-025 categories plus concurrent-upload and cancel-during-ingest.
- **README**: a new "Uploading PDFs from the UI" section under the existing CLI ingest section, documenting the paperclip flow and the replace-vs-append choice (FR-026).

**Structure Decision**: continues feature 001/002's single-project layout. No new top-level directories; the new code slots into the existing `src/rag/ui/`, `src/rag/ingest/`, `src/rag/repositories/` packages. Tasks own the concrete filenames and module boundaries within that layout.

## Complexity Tracking

> One declared violation. Justified per the Art IV.8 deviation-justification pattern (Art VII has no formal deviation clause but is governed by the same governance principle — justified inline, recorded in Complexity Tracking).

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| **Art VII deviation** — user-driven multi-document corpus via the **append** flow. Article VII lists "Multi-document corpora or collections" as out-of-scope. | (a) The user's spec for this feature explicitly requests both replace AND append behaviors as P1 user stories (US1, US2). Dropping append would force the reviewer to manually swap PDFs every time they want to extend the corpus, which is a worse demo than the CLI path that already supports incremental ingest. (b) Append exercises the schema's `source_document` table — feature 002 already created multiple-row support in the schema; this feature surfaces it through the UI without adding new schema or retrieval complexity. (c) The deviation is bounded: no per-document query filtering, no corpus-management UI, no document-list view, no collection metadata. The chunks remain a flat search space exactly as feature 002 designed. (d) Aligns with Art VIII (the demo is the product) — a reviewer can demonstrably show that the system handles two PDFs and cites the correct one for each question. | "Replace only" would (i) make the demo brittle — every new PDF means losing the current one, so the reviewer can't compare across documents; (ii) leave the schema's multi-document support unexercised, which is a wasted signal at hiring time (the candidate built it but can't show it works); (iii) cause friction in the live demo if the reviewer wants to test "what does the system do with two PDFs?" — a common question. The bounded scope of append (additive ingest, no filtering, no UI complexity) is the minimum that demonstrates multi-document capability without crossing into "corpus management" feature creep. |
