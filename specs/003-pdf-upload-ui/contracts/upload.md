# Contract: `POST /ui/upload`

**Feature**: [003-pdf-upload-ui](../spec.md)
**Plan**: [plan.md](../plan.md)
**Date**: 2026-05-12

## Surface

One new HTMX route, registered alongside the existing `POST /ui/query` in `src/rag/ui/routes.py`.

**Method**: `POST`
**Path**: `/ui/upload`
**Encoding**: `multipart/form-data`
**Response content type**: `text/html` (an HTMX partial for swap into `#response`)

## Request body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pdf` | file (`application/pdf`, but validated by magic header) | Yes (on every POST, including the second one — see FR-013) | The uploaded PDF. Max size `RAG_MAX_UPLOAD_BYTES` (default 25 MiB ≈ 26,214,400 bytes). |
| `action` | string (`replace` \| `append` \| `cancel`) | No on first POST; Yes on second POST | Drives the dispatch. Missing → server decides whether to confirm or proceed directly. |

The two-POST flow:

```text
POST /ui/upload         (pdf only)
  ↓ corpus non-empty?
     no  → run ingest as "append" (semantically; empty corpus has nothing to append to or replace)
            → return _upload_success.html | _upload_error.html
     yes → return _upload_confirm.html (Replace/Append/Cancel buttons)

POST /ui/upload         (pdf + action=replace|append|cancel)
  ↓ action
     replace → clear all source_documents, then ingest in same transaction
                → return _upload_success.html | _upload_error.html
     append  → ingest in transaction
                → return _upload_success.html (incl. no_new_content) | _upload_error.html
     cancel  → return _upload_cancelled.html, no DB work
```

## Response — success cases

### Confirmation prompt (first POST, non-empty corpus)

- **Status**: `200 OK`
- **Body**: `_upload_confirm.html` partial swapped into `#response` (per HTMX `hx-target`)
- **Headers**: `X-RAG-Trace-Id: <trace_id>`

Rendered content (template variables):

```text
filename        # the uploaded file's name (filename attribute of the multipart part)
size_mb         # round(upload.size / 1024 / 1024, 1)
doc_count       # SELECT count(*) FROM source_document
```

Each of the three buttons posts back to `/ui/upload` with `hx-include="#upload-form"` and `hx-vals='{"action": "<choice>"}'`.

### Ingest success (any POST that completed an ingest)

- **Status**: `200 OK`
- **Body**: `_upload_success.html` partial swapped into `#response`
- **Headers**: `X-RAG-Trace-Id: <trace_id>`

Rendered content (template variables):

```text
filename             # display name from the upload
action               # "replace" | "append"
chunks_inserted      # int — 0 if no_new_content (dedup hit)
no_new_content       # bool — True if file_hash matched an existing source_document
```

When `no_new_content == True`, the template renders the FR-018 "no new content" message ("This PDF was already in the knowledge base — no new chunks were created.") rather than the generic success message — distinct messaging required by FR-004.

### Pre-action cancel

- **Status**: `200 OK`
- **Body**: `_upload_cancelled.html` (small partial: "Upload cancelled. The knowledge base is unchanged.")
- **Headers**: `X-RAG-Trace-Id: <trace_id>`

No database operations are performed; the corpus is observably identical to its pre-POST state (FR-012).

## Response — failure cases

All failures return `_upload_error.html` swapped into `#response`. The template branches on a `cause` variable to render a reviewer-readable message:

| Cause | HTTP Status | Message rendered | When |
|-------|-------------|------------------|------|
| `invalid_pdf` | `400` | "This file is not a valid PDF. The PDF magic header (`%PDF-`) was not found in the first bytes." | Magic-header check failed (FR-014). |
| `oversize` | `413` | "Upload too large. Max size: 25 MB (26,214,400 bytes). Your file: {actual_mb} MB. Adjust `RAG_MAX_UPLOAD_BYTES` to raise the cap." | Size cap exceeded (FR-015). |
| `concurrent_upload` | `409` | "Another upload is in progress (started at {started_at}). Please retry once it completes." | App-state lock held (FR-028). |
| `extraction_failed` | `503` | "PDF extraction failed: {gemini_error_message}. Your existing documents are unchanged." | Upstream Gemini File API failure during page extraction. The "your existing documents are unchanged" suffix appears only for replace failures (FR-027). |
| `embedding_failed` | `503` | "Embedding generation failed: {gemini_error_message}. Your existing documents are unchanged." | Upstream Gemini embedding failure mid-ingest. FR-027 suffix as above for replace. |
| `persistence_failed` | `503` | "Database write failed: {db_error_message}. Your existing documents are unchanged." | Postgres error during insert. FR-027 suffix as above. |
| `cancelled` | (no response — client disconnected) | n/a | Client closed the connection or aborted the request mid-ingest. Server detects via `request.is_disconnected()`, rolls back the transaction, emits `upload_cancelled` log. No response is sent (client is gone). |

Every response carries `X-RAG-Trace-Id: <trace_id>`. For the `cancelled` case there is no response, but the `trace_id` appears in the structured log (the only place a debugger can find it).

## Behavior guarantees

These are the behaviors `/speckit-tasks` and the test suite will verify:

1. **Two-POST flow shape**: A non-empty corpus + missing `action` always returns the confirmation partial — never starts an ingest. Source: FR-008, FR-010.
2. **Empty corpus skips confirmation**: A zero-doc corpus + any POST (with or without `action`) proceeds directly to ingest as if `action=append`. Source: FR-011.
3. **File re-validation on second POST**: The server runs magic-header + size checks again on the second POST. A second POST that smuggles a different file or omits `pdf` is rejected. Source: FR-013.
4. **Replace is atomic**: A replace POST that fails after the `DELETE FROM source_document` step leaves the corpus observably unchanged (row count + content). Source: FR-019.
5. **Append preserves prior corpus**: An append POST never deletes any pre-existing `source_document` or `chunk` row. Source: FR-017.
6. **Append is idempotent on identical content**: Two append POSTs of the same PDF produce one `source_document` row and one set of chunks; the second POST's response has `no_new_content=True`. Source: FR-018.
7. **Concurrent uploads get 409**: While one POST is between request entry and response, any second POST returns 409 immediately. Source: FR-028.
8. **Cancel during in-flight ingest rolls back**: A client disconnect during the ingest portion of a POST causes the open transaction to roll back; corpus row counts are unchanged. Source: user `/speckit-plan` input + R-005.
9. **Citation behavior unchanged**: Citations returned by `POST /query` and `POST /ui/query` after a successful upload are byte-identical in structure to citations after a CLI `rag ingest`. Source: FR-023.

## Logging contract

Every request emits at least two structured log records (`upload_received` and one of `upload_complete` / `upload_failed` / `upload_rejected_*` / `upload_cancelled`). The full event list is in `research.md → R-009`. Every event carries:

- `trace_id` — unique per request, propagates into `ingest_pdf` events from the existing pipeline.
- `event` — the event name.
- `elapsed_s` (on terminal events) — wall-clock seconds since `upload_received`.

The route emits these via the existing `rag.log.get_logger(__name__)` + `TRACE_LOG_KEY` machinery feature 002 set up. No new logging dependencies.

## Out-of-band behavior

- **CLI `rag ingest <path>` continues to work unchanged**. The CLI calls `ingest_pdf` (the path-based wrapper), which is unaffected by the connection-passing refactor. Source: FR-022.
- **Query endpoints (`POST /query`, `POST /ui/query`) are unmodified**. Source: FR-023.
- **`/health` continues to report the highest applied migration version**. Since no new migration ships, the version remains `0002_query_path.sql`.

## Open items deferred to `/speckit-tasks`

- Exact connection-passing signature on `ChunkRepository` methods (kwarg name, default value).
- Whether the upload route handler lives in `src/rag/ui/routes.py` (extending the existing module) or a new `src/rag/ui/upload.py` module that registers itself.
- Whether `_upload_success.html` and `_upload_cancelled.html` share a template via inheritance or are distinct files.
- Exact wording of the no-new-content message (the FR-018 distinct messaging requirement allows latitude on phrasing).
