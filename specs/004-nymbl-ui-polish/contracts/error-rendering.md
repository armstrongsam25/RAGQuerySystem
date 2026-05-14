# Contract: Error Rendering

Implements FR-001..004 and the 2026-05-13 clarify decision (no raw backend text in the UI).

## Visible copy by category

The error templates emit **exactly one** of the following user-visible strings as the body text of the error card, based on `ErrorView.category` (see [data-model.md V1](../data-model.md)). The strings are hard-coded into the templates and MUST NOT be parameterized or replaced via translation files in this feature.

| `category` | Visible heading | Visible body copy | Retry CTA |
|---|---|---|---|
| `server` | "Server error" | "Something went wrong on our end. Please try again." | "Retry" button |
| `validation` | "Invalid input" | "We couldn't process that request. Please review and try again." | "Retry" button |
| `network` | "Network error" | "Couldn't reach the server. Check your connection and try again." | "Retry" button |
| `concurrent` | "Upload in progress" | "Another upload is running. Wait for it to finish, then try again." | (no retry; auto-dismisses on next status change) |
| `rate_limited` | "Service busy" | "We're hitting upstream rate limits. Please wait a moment and try again." | "Retry" button |

The retry button:
- For query errors: re-triggers `hx-post="/ui/query"` with the existing question textarea value.
- For upload errors: re-opens the file picker (clicks the hidden `#pdf-file` input).
- Concurrent: rendered without a retry button; the upload-progress card already polls and will dismiss this card automatically when the prior upload finishes.

## Status code mapping (server-rendered errors)

The route handler in [src/rag/ui/routes.py](../../src/rag/ui/routes.py) MUST return the HTTP status codes already in place (no change), and MUST map the caught exception to `category` before rendering:

| Exception caught | HTTP status | `category` |
|---|---|---|
| `ValueError` from query path | 400 | `validation` |
| `UpstreamProviderError` | 503 | `server` |
| `RateLimitedError` (in upload task) | 503 | `rate_limited` |
| Concurrent-upload guard hit | 409 | `concurrent` |
| `InvalidPDFError` | 400 | `validation` |
| Oversize | 413 | `validation` |
| Any other `Exception` in `_run_upload_task` | 500 | `server` |

## Client-side errors (HTMX events)

A single `<script>` block at the bottom of [base.html](../../src/rag/ui/templates/base.html) MUST register three event listeners on `document.body`:

| HTMX event | Triggers | Renders into |
|---|---|---|
| `htmx:responseError` | Non-2xx response | (no-op — the server already returned an error partial that HTMX swaps in via the global `htmx-response-targets`-equivalent we wire) |
| `htmx:sendError` | Network failure / CORS / DNS | The `network` template from `<template id="error-fallback-network">` is cloned into the appropriate target (`#response` for query, `#upload-progress-*` for upload). |
| `htmx:timeout` | `hx-request` timeout exceeded (60 s for queries) | Same as `htmx:sendError`. |

The script MUST:
1. Identify the swap target from `event.detail.requestConfig.target` (HTMX populates this).
2. Clone the relevant `<template>` content into that target via `innerHTML = templateContent.innerHTML`.
3. Remove the `.htmx-request` class from the form that issued the request, so the loading indicator clears.
4. Re-enable any disabled submit elements — though HTMX's own `afterRequest` cleanup handles this for `hx-disabled-elt`, so this is defensive only.

The script MUST NOT:
- Read or log `event.detail.xhr.responseText`.
- Mutate the URL, history, or any localStorage.
- Insert any text not present in the `<template>` blocks.

## Logging fidelity

The server-side log lines stay unchanged. The `upload_failed`, `ui_upstream_failure`, `upload_rejected_invalid_pdf`, `upload_rejected_oversize`, and `upload_rejected_concurrent` log events MUST continue to include their existing `cause`, `error`, `provider`, and trace_id fields. Only the *rendered HTML* changes — the operator's ability to diagnose from logs is unaffected.

## Contract test assertions

`tests/unit/test_ui_routes.py` MUST be extended with:

1. `test_query_503_renders_server_category`: mock `answer_question` to raise `UpstreamProviderError`; POST `/ui/query`; assert response status 503, response body contains "Server error" *and does not contain* the raw exception message or status code.
2. `test_query_400_renders_validation_category`: POST `/ui/query` with input that triggers `ValueError`; assert body contains "Invalid input" and not the raw `ValueError` message.
3. `test_upload_409_renders_concurrent_category`: force the concurrent-upload guard; assert response body contains "Upload in progress" and not the raw `"Another upload is in progress..."` string.
4. `test_upload_413_renders_validation_category`: send oversize PDF; assert body contains "Invalid input" and does not surface the size cap details to the user.
5. `test_upload_invalid_pdf_renders_validation_category`: send bad-magic PDF; assert body contains "Invalid input" only.
6. `test_error_partials_carry_role_alert`: render `_error.html` and `_upload_error.html` directly; assert the root `<div>` carries `role="alert"`.

## Out-of-scope (intentionally)

- The exact wording of the five copy lines above is the spec author's call; future translation files may parameterize them. Today they are constants.
- Auto-retry on transient 503s is *not* implemented — the user clicks Retry.
