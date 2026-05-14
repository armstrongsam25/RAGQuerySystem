# Quickstart: PDF Upload from the Web UI

**Feature**: [003-pdf-upload-ui](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-05-12

This walkthrough is what a fresh-clone reviewer follows once feature 003 is merged. It supersedes feature 002's UI-only flow by adding the paperclip-upload path.

## Prerequisites

Same as feature 002:

- Docker + Docker Compose
- A `GEMINI_API_KEY` exported (or set in `.env`)
- A local OpenAI-API-compatible server running (LM Studio, Ollama, llama.cpp, etc.) configured to back the grounding judge — feature 002's `.env.example` lists the required variables

No new prerequisites for feature 003.

## Bring the stack up

```sh
make up
```

Wait for both services (`app` and `db`) to report healthy. Open the UI:

```sh
open http://localhost:8000/         # macOS
xdg-open http://localhost:8000/     # Linux
start http://localhost:8000/        # Windows PowerShell
```

You see the question form with a paperclip (📎) icon in the bottom-right corner of the textarea.

## First-time upload (empty corpus)

The fastest path to a queryable system, without ever touching the terminal again:

1. Click the **paperclip icon (📎)** in the textarea. The OS file picker opens.
2. Select a PDF (e.g., the committed `data/sample.pdf` from feature 002 if you cloned with it, or any PDF on your machine).
3. The form auto-submits. The "Thinking…" indicator appears.
4. Because the corpus is empty, the server skips the confirmation step (FR-011) and ingests directly.
5. After ingest completes (under 3 minutes for a 50-page PDF — SC-001), an upload-success panel appears showing the filename, the chunk count, and "Added to knowledge base."
6. Type a question into the textarea, click **Ask**. You see an answer with citations.

Total time from `make up` to rendered answer in the browser: under 5 minutes (SC-006).

## Replace the current PDF with a new one

1. Click the paperclip, pick a different PDF, file auto-submits.
2. The server detects the non-empty corpus and returns a confirmation panel with three buttons: **Replace existing — clears all current documents (cannot be undone)**, **Add to existing — preserves current documents**, **Cancel**.
3. Click **Replace existing**. The "Thinking…" indicator reappears with a **Cancel upload** button beside it.
4. The server clears the existing corpus, then ingests the new PDF — all in a single transaction. If anything fails, the prior corpus is fully restored (FR-019 strict rollback).
5. On success, the upload-success panel shows the new filename, chunk count, and "Replaced previous documents."
6. Queries now return answers grounded only in the new PDF. A question whose answer was only in the previous PDF returns a refusal or `no_documents` (SC-003).

## Append a second PDF to grow the corpus

1. Click the paperclip, pick a second PDF.
2. On the confirmation panel, click **Add to existing**.
3. The server ingests the new PDF without touching the existing chunks.
4. Subsequent queries can return citations from either document; each citation's page number resolves to the document it came from (SC-002).

If you append a PDF that's already been ingested (same bytes, same SHA-256), you see a distinct "no new content" message rather than a generic success — the dedup invariant fired (FR-018).

## Cancel an upload mid-flight

1. Pick a large PDF, click **Replace existing** at the confirmation panel.
2. While the "Thinking…" indicator is visible, click the **Cancel upload** button beside it.
3. The in-flight request is aborted. The server detects the disconnect at its next pipeline checkpoint, rolls back the open transaction, and emits an `upload_cancelled` structured log.
4. The prior corpus is observably unchanged (row counts identical to pre-upload). Queries continue to work against the prior PDF.

## Error cases you can hit on purpose

| Scenario | Expected UI behavior |
|----------|----------------------|
| Drop a non-PDF file (rename `.docx` to `.pdf` first to bypass the file picker filter) | `_upload_error.html` with cause `invalid_pdf`, HTTP 400. Corpus untouched. |
| Upload a file > 25 MB (or smaller if you've set `RAG_MAX_UPLOAD_BYTES`) | `_upload_error.html` with cause `oversize`, HTTP 413. Naming both the cap and your file size. Corpus untouched. |
| Submit a second upload while one is in flight (use two browser tabs) | The second submit gets `_upload_error.html` with cause `concurrent_upload`, HTTP 409. First upload continues unaffected. |
| Disconnect from Gemini mid-ingest (revoke API key, kill network) | `_upload_error.html` with cause `extraction_failed` or `embedding_failed`, HTTP 503. For replace: prior corpus is intact. |

## Useful CLI parity (still works)

The pre-existing CLI ingest path is unchanged:

```sh
docker compose exec app rag ingest /path/inside/container/to/your.pdf
```

CLI-ingested and UI-uploaded PDFs are structurally indistinguishable in the database (FR-023). You can mix and match — upload via UI, ingest more via CLI, query via either UI or `POST /query`.

## Configuration cheatsheet

New environment variable for this feature:

| Variable | Default | Purpose |
|----------|---------|---------|
| `RAG_MAX_UPLOAD_BYTES` | `26214400` (25 MiB) | Maximum size of an uploaded PDF. Exceeding it returns HTTP 413 (FR-015). |

All other variables (`GEMINI_API_KEY`, `GROUNDING_JUDGE_BASE_URL`, etc.) are unchanged from feature 002.

## What to walk through during a 30-minute demo

For the live demo (Article VIII.6), the upload UI gives you a much richer narrative than the CLI-only flow:

1. **Architecture walk-through** (~5 min) — covers feature 001 (schema, providers) + 002 (query path, grounding judge) + 003 (upload UI). The slide deck (Art VIII.5) does most of this.
2. **Live demo on the committed sample PDF** (~10 min) — ask a few in-scope questions, then ask an out-of-scope one and show the refusal.
3. **Live demo of replace** (~5 min) — click the paperclip, pick a *different* PDF the reviewers brought (or a second committed sample), choose Replace, watch the strict-rollback transactional behavior. Ask a question whose answer was in the old PDF, see `no_documents` or refusal — this is the credibility moment.
4. **Live demo of append** (~3 min) — bring back the first PDF via append, show that both PDFs are queryable and citations resolve to the correct one.
5. **Limitations / Q&A** (~7 min) — multi-document corpus is bounded (no filtering), no auth, no eval harness landed yet (still slated for a follow-up feature), accessibility deferred. The honest list per Art VIII.4.

## Future work flagged for follow-up features

- **Eval harness** (Article III) — still outstanding. The original feature-003 slot was reused for this UI work; the eval harness needs its own feature.
- **Postgres advisory lock** for the concurrent-upload guard — required if the deployment ever runs Uvicorn with multiple workers. Today's single-worker setup makes the in-process `asyncio.Lock` sufficient.
- **`source_document.upload_source`** column to record CLI vs UI provenance — useful telemetry but not load-bearing for the demo.
- **Accessibility pass** — ARIA labels, keyboard navigation, screen-reader testing. Explicitly deferred per the user's `/speckit-plan` input.
