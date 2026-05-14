# Contract: UI Surface (updates to feature 002's HTMX UI)

**Feature**: [003-pdf-upload-ui](../spec.md)
**Plan**: [plan.md](../plan.md)
**Date**: 2026-05-12

This document tracks the additions and changes to the HTMX UI established in feature 002. The query-form surface (`POST /ui/query`, `_answered.html`, `_refused.html`, `_no_documents.html`, `_error.html`) is **unchanged**. The query path's contract from feature 002 continues to apply verbatim.

## URL surface (delta)

| Route | Status | Notes |
|-------|--------|-------|
| `GET /` | unchanged | Renders `base.html`. Markup is extended to include the paperclip overlay and hidden upload form, but the surface (one URL, server-rendered HTML) is unchanged. |
| `GET /ui/static/*` | unchanged | Static asset mount. `styles.css` gains new rules; no new files required. |
| `POST /ui/query` | unchanged | Feature 002's contract. |
| `POST /ui/upload` | **NEW** | See [`upload.md`](./upload.md) for the full contract. |

No new routes beyond `/ui/upload`. No JavaScript files added (HTMX 2.0.3 already pinned from feature 002 is sufficient; one small inline `onchange` handler is needed on the file input).

## `base.html` — additions

The existing `<form hx-post="/ui/query">` (textarea + Ask button) is preserved. Two additions:

1. **The textarea is wrapped in a `<div class="textarea-wrap">`** that establishes the positioning context for the paperclip overlay.

2. **A separate hidden upload form** is added (still inside `<main>`, alongside the question form):

```html
<form id="upload-form"
      hx-post="/ui/upload"
      hx-encoding="multipart/form-data"
      hx-target="#response"
      hx-indicator="#thinking">
  <input type="file"
         id="pdf-file"
         name="pdf"
         accept="application/pdf"
         hidden
         onchange="this.form.dispatchEvent(new Event('submit'))">
</form>
```

3. **The paperclip control** is a `<label for="pdf-file">` positioned absolutely inside `.textarea-wrap`:

```html
<div class="textarea-wrap">
  <textarea id="question" name="question" rows="3" maxlength="1000" required ...></textarea>
  <label for="pdf-file" class="paperclip-btn" title="Attach PDF">📎</label>
</div>
```

The `<label>` opens the file picker via native HTML semantics — no JS required for opening. The `onchange` handler on the file input triggers HTMX form submission on file selection. This is the one inline JS line in the entire feature.

The paperclip uses the **U+1F4CE PAPERCLIP** glyph (📎) — no icon-font dependency, no SVG file. If a future style pass swaps in an SVG, the change is template-local.

## `styles.css` — additions

New rules (target file: `src/rag/ui/static/styles.css`):

- `.textarea-wrap` — `position: relative;` so the absolute-positioned paperclip anchors to the textarea container.
- `.paperclip-btn` — `position: absolute; bottom: 0.5rem; right: 0.5rem;` with `cursor: pointer;` and a hover state. Visually unobtrusive; sits in the textarea's bottom-right corner so it doesn't overlap typed text (the textarea's `padding-right` is bumped slightly to reserve space).
- `.upload-confirm` — styles for the inline confirmation partial: padded block, distinct background so it's not mistaken for a query response, three buttons stacked or inline.
- `.upload-success`, `.upload-error`, `.upload-cancelled` — visually distinct result panels (FR-004 / FR-005 / FR-007). Different border or background colors from `_answered.html` / `_refused.html` / `_no_documents.html` so reviewers can identify upload vs query outcomes at a glance (SC-007).

Styling is intentionally minimal — no design system, no color palette beyond what feature 002 already uses, no responsive breakpoints. Accessibility deferred per user `/speckit-plan` input.

## New templates

| File | Purpose | Trigger |
|------|---------|---------|
| `_upload_confirm.html` | The Replace / Append / Cancel partial swapped into `#response` when the first POST sees a non-empty corpus. | First POST to `/ui/upload`, corpus non-empty. See `upload.md`. |
| `_upload_success.html` | Success panel: filename, action performed, chunk count, or distinct "no new content" message when dedup fires. | Successful ingest (replace or append). |
| `_upload_error.html` | Error panel: reviewer-readable cause, "your existing documents are unchanged" suffix on replace failures (FR-027). | Any upload failure with an HTTP response. |
| `_upload_cancelled.html` | Brief "upload cancelled, knowledge base unchanged" partial. | Pre-action cancel (second POST with `action=cancel`). |

Existing templates (`base.html`, `_answered.html`, `_refused.html`, `_no_documents.html`, `_error.html`) are not modified except for the `base.html` additions above.

## In-flight cancellation UX

When an ingest is running (between the confirmation choice and the response arrival), the existing `#thinking` indicator ("Thinking…") is visible. To support the user-requested cancel-during-ingest behavior:

- The `#thinking` element grows a sibling Cancel button rendered as part of the same indicator block: `<button onclick="htmx.find('#upload-form')?.dispatchEvent(new Event('htmx:abort'))">Cancel upload</button>`.
- Clicking the button triggers HTMX's `htmx:abort` event, which aborts the in-flight XHR.
- The server-side handler detects the disconnect at its next checkpoint and rolls back (R-005).
- After abort, HTMX leaves the previous `#response` content in place (nothing new was swapped). The reviewer sees the page in a queryable state with the prior corpus intact — matches the "your existing documents are unchanged" promise.

This is the only place the upload UI diverges visibly from feature 002's pattern. The Cancel button is intentionally minimal; per the accessibility deferral it lacks `aria-label` or focus-trap behavior.

## Behavior guarantees (UI-side delta)

These complement the route-level guarantees in `upload.md`:

1. **Question form and upload form are independent**. Submitting the question form (`POST /ui/query`) never carries the file input; submitting the upload form (`POST /ui/upload`) never carries the question text. Source: spec FR-002.
2. **Paperclip click opens the OS file picker**. Native `<label for=...>` semantics; no custom JS.
3. **File selection auto-submits**. `onchange="this.form.dispatchEvent(new Event('submit'))"` fires the upload form's HTMX submit. The reviewer does not need a separate "upload" button.
4. **Confirmation partial reuses the same file input**. The `<input type="file">` element stays mounted in the DOM across the confirmation render; the Replace/Append buttons use `hx-include="#upload-form"` to resubmit the file with the chosen action. Source: R-002, R-008.
5. **Upload outcomes are visually distinct from query outcomes**. Different border / background colors on `_upload_success.html` / `_upload_error.html` vs `_answered.html` / `_refused.html`. Source: FR-004, FR-006, SC-007.
6. **Spinner has a Cancel button during ingest**. Clicking it aborts the request via HTMX `htmx:abort` and triggers server-side rollback. Source: R-005.
7. **No external network calls**. The page continues to talk only to the local backend; the paperclip and styling additions add no third-party assets. Source: FR-007.

## Out of scope (deferred to a future feature or never)

- **Drag-and-drop file zone** — spec out-of-scope, R-001.
- **Multi-file selection** — spec out-of-scope, FR-001.
- **Per-page ingest progress** — spec out-of-scope, FR-003 (spinner suffices).
- **Document list / corpus inspector UI** — Article VII; the deviation is bounded to additive ingest only.
- **Accessibility polish** (ARIA labels, keyboard navigation, screen-reader testing) — user `/speckit-plan` input.
- **Mobile / responsive styling** — feature 002 already deferred this; carries forward.
- **Theming / dark mode** — feature 002 deferred; carries forward.
