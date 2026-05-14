# Phase 1 Data Model: PDF Upload from the Web UI

**Feature**: [003-pdf-upload-ui](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-05-12

## Scope

**No schema changes.** Feature 003 reuses the schema produced by migrations `0001_init_vector_store.sql` (feature 001) and `0002_query_path.sql` (feature 002). No new tables, no new columns, no new indexes, no new constraints.

What this file documents:

1. Which existing schema elements are load-bearing for this feature.
2. The transactional boundary the application code wraps around them.
3. The runtime entities (request / response shapes) that flow through the upload route, since they're new even though no persisted state is.

Runtime entities (`Upload Request`, `Upload Response`, `Corpus State`) are pinned in `spec.md → Key Entities`. This document elaborates how they map to the database state and the wire format.

## Load-bearing schema elements (inherited, unchanged)

| Element | Source | Why feature 003 needs it |
|---------|--------|--------------------------|
| `source_document.file_hash TEXT UNIQUE` | Migration 0002 | Re-uploading the same PDF via **append** computes the same SHA-256, hits the UNIQUE constraint, and short-circuits to `status="already_done"` in the existing ingest pipeline. Maps to spec FR-018 / Feature 002 FR-004. |
| `chunk.source_document_id` FK with `ON DELETE CASCADE` | Migration 0001 | The **replace** flow deletes from `source_document`; the cascade removes all chunks atomically, satisfying spec FR-016's "clearing MUST cascade so no chunk rows are left orphaned." |
| Composite UNIQUE on `chunk(source_document_id, page_number, char_offset_start, char_offset_end)` | Migration 0001 | Second-layer dedup defense — even if the source_document layer somehow missed (it can't, given the file_hash UNIQUE), chunk-level uniqueness prevents duplicates. |
| `chunk` provenance columns (`source_document_id`, `page_number`, `char_offset_start`, `char_offset_end`, `raw_text`) | Migration 0001 | Article II provenance carried forward; uploads use the same `ingest_pdf` pipeline so these fields are populated identically to the CLI path (spec FR-017, FR-023). |

## Transactional boundary

The application wraps the upload's database operations in a **single psycopg 3 async transaction** for both replace and append. The transaction is owned by the route handler and acquired via a single connection from the pool.

```text
async with pool.acquire() as conn:
    async with conn.transaction():
        if action == "replace":
            await repo.delete_all_source_documents(connection=conn)
        await ingest_pdf_core(
            pdf_bytes=...,
            display_filename=...,
            connection=conn,        # threaded through the pipeline
            ...,
        )
```

This boundary delivers three properties without additional locking:

1. **Strict rollback** (FR-019): if any inner statement raises — `RuntimeError` from Gemini, `psycopg 3 async.PostgresError`, `UploadCancelledError`, `asyncio.CancelledError` — `conn.transaction().__aexit__` rolls back, observably preserving the pre-upload state.
2. **Concurrent-query isolation** (FR-016): Postgres MVCC ensures that concurrent SELECTs (the `/query` and `/ui/query` paths) see the pre-transaction snapshot until commit. No application-level read lock is needed.
3. **Cascade-on-delete coherence**: the `DELETE FROM source_document` issued at the top of a replace runs in the same transaction as the subsequent INSERTs, so the deleted-then-recreated rows commit (or roll back) as one atomic unit.

The repository methods (`delete_all_source_documents`, `ensure_source_document`, `add_chunks`) accept an optional `connection: psycopg 3 async.Connection | None = None` parameter. When `None`, they acquire-and-release their own connection (the existing behavior for `rag ingest <path>` and other callers). When supplied, they execute against the caller's connection, letting the caller own the transaction lifecycle. This is a small additive change to `rag.repositories.base.ChunkRepository`; the existing CLI and HTTP query paths are unaffected.

## New repository operation

| Method | Signature | Behavior |
|--------|-----------|----------|
| `delete_all_source_documents(*, connection=None) -> int` | New on `ChunkRepository` (base + pgvector + in-memory impls) | Issues `DELETE FROM source_document` (chunks cascade). Returns the count of deleted documents. Used by the replace flow before re-ingest. |

No existing repository methods need new behavior — they just need the optional `connection` parameter threaded through to honor a caller-owned transaction.

## Runtime entity → wire format

### Upload Request (spec Key Entities)

| Spec entity field | HTTP encoding | Notes |
|-------------------|--------------|-------|
| File bytes | multipart/form-data field `pdf` | Streamed by Starlette to a spooled temp buffer. |
| Original filename | multipart `pdf.filename` | Display + logging only (per FR-018, never used for dedup). |
| Reported content type | multipart `pdf.content_type` | Logged for observability; magic-header check is authoritative. |
| Action selector | multipart form field `action` | Optional on first POST (server returns confirm partial); required on second POST as `replace` / `append` / `cancel`. |

### Upload Response (spec Key Entities)

The wire response is `text/html` (HTMX partial), not JSON. The "outcome" + "cause" fields in the spec map to which template is rendered:

| Spec outcome | Template | Notes |
|--------------|----------|-------|
| `succeeded` | `_upload_success.html` | Renders filename, action label ("Replaced" / "Added to"), and chunk count. |
| `no_new_content` | `_upload_success.html` with `no_new_content` flag | Same template, different rendering branch — distinct "no new content" message per FR-018. |
| `failed` (cause: `invalid_pdf`) | `_upload_error.html` | HTTP 400. |
| `failed` (cause: `oversize`) | `_upload_error.html` | HTTP 413. |
| `failed` (cause: `concurrent_upload`) | `_upload_error.html` | HTTP 409. |
| `failed` (cause: `extraction_failed` / `embedding_failed` / `persistence_failed`) | `_upload_error.html` | HTTP 503. |
| Pre-action `cancel` | `_upload_cancelled.html` (small) | HTTP 200. Renders a brief "upload cancelled" notice; corpus row counts unchanged. |
| (Confirmation step) | `_upload_confirm.html` | HTTP 200. Renders Replace / Append / Cancel buttons. |

Every response carries an `X-RAG-Trace-Id` header (the same pattern feature 002 uses on `/ui/query` responses) so structured logs and rendered UI can be correlated during a demo.

### Corpus State (spec Key Entities)

Derived view; not persisted. Computed at upload-route entry via `SELECT count(*) FROM source_document`. Drives the confirmation-vs-direct-ingest branch (FR-008 vs FR-011):

```text
if corpus_state.document_count > 0 and action is None:
    return _upload_confirm.html
elif corpus_state.document_count == 0 and action is None:
    proceed_with_ingest(action="append")  # synthetic — semantically identical to append on empty
elif action in ("replace", "append"):
    proceed_with_ingest(action=action)
elif action == "cancel":
    return _upload_cancelled.html
```

The corpus state read is **not** transactional with the subsequent write — it's a quick `count()` to decide which template to render. Between the read and the action-confirmation second POST, another upload could in principle change the state (but is prevented by the upload lock, R-003). On the second POST, the server re-evaluates: an `action=append` against a now-empty corpus is harmless (functionally identical); an `action=replace` against a now-empty corpus simply clears nothing and ingests.

## State transitions (upload lifecycle)

Still no formal schema state machine. The upload run, like ingest, lives in application state and logs:

```text
upload_received
   → upload_validated (magic + size pass)
        | upload_rejected_{invalid_pdf, oversize}    (terminal failure)
   → [if corpus non-empty + action=None]
        → render _upload_confirm.html (HTTP 200, no DB work)
   → upload_action_chosen (action=replace|append|cancel from second POST)
        | action=cancel → render _upload_cancelled.html (terminal, no DB work)
   → [open transaction]
        → upload_clear_complete (replace only)
        → ingest_started, file_hash_computed, ...
            (existing ingest_pdf log sequence, threaded through the same trace_id)
        → ingest_complete OR ingest_already_done
   → [commit transaction]
   → upload_complete
        | any exception above → [rollback] → upload_failed OR upload_cancelled
```

Failure at any pre-commit stage rolls back the entire transaction — so `source_document` and `chunk` row counts are observably identical to their pre-upload values for any failure mode that started a transaction. Pre-transaction failures (invalid_pdf, oversize, concurrent_upload) don't touch the database at all.

## Validation rules — spec → schema/transaction traceability

| Spec requirement | Where enforced |
|------------------|----------------|
| FR-014 (PDF magic-header validation before any DB mutation) | Application: route handler reads first 5 bytes and validates `b"%PDF-"` before opening a transaction. |
| FR-015 (configurable max upload size, default 25 MB) | Application: route handler checks `upload.size` against `settings.RAG_MAX_UPLOAD_BYTES`. |
| FR-016 (clear cascades; no orphaned chunks) | Schema: existing `chunk.source_document_id` FK with `ON DELETE CASCADE` (feature 001). |
| FR-017 (append uses the same ingest path as `rag ingest`) | Application: append route invokes `ingest_pdf_core` (extracted from the existing `ingest_pdf` body) with a caller-owned connection. |
| FR-018 (no duplicate chunks on re-upload) | Schema: `source_document.file_hash` UNIQUE + composite `chunk` UNIQUE (both from feature 002 / 001). Application: existing `ensure_source_document` short-circuit returns `(id, created=False)` on hash collision. |
| FR-019 (strict rollback on replace failure) | Schema: transactional semantics. Application: route handler wraps clear-then-ingest in a single `conn.transaction()`. |
| FR-020 (structured log records for upload events) | Application: new log events listed in research.md R-009, all carrying `trace_id`. |
| FR-028 (process-wide 409 on concurrent upload) | Application: `asyncio.Lock` on `app.state.upload_lock`, `locked()` pre-check before acquire. |
| (User /speckit-plan input) Cancel-during-ingest rolls back | Schema: transactional semantics. Application: route handler polls `request.is_disconnected()` between pipeline checkpoints; raised exception causes transaction rollback. |

## Open seams (still deferred to future migrations / features)

- `source_document.upload_source TEXT` to record whether a document arrived via CLI or UI — useful for observability but not load-bearing for this feature.
- A `corpus_event` audit-log table to record clear / append / replace events with timestamps — overkill for the demo's scope; structured logs cover the same need.
- Per-document soft-delete (would enable undo for replace) — explicitly out of scope per spec assumption "Replace is destructive and irreversible."

These remain available without breaking changes to the current schema, exactly as feature 002's open seams remained available.
