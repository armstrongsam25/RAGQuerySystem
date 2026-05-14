# Phase 1 Data Model: Nymbl UI Polish & UX Fixes

This feature changes no persisted entities — Postgres + pgvector + the chunk schema are unchanged. The "data model" here is the small set of view-model shapes that flow from the route handlers into the Jinja templates, plus the visual token vocabulary they reference.

---

## V1 — `ErrorView` (template context for `_error.html` and `_upload_error.html`)

The clarify pass locked error display to a fixed-category vocabulary. Templates render only the category — not raw backend strings.

| Field | Type | Allowed values | Source |
|---|---|---|---|
| `category` | `str` (enum-coded) | `"server"`, `"validation"`, `"network"`, `"concurrent"`, `"rate_limited"` | Computed in [routes.py](../../src/rag/ui/routes.py) from the caught exception type. |
| `trace_id` | `str` (UUID) | n/a | Existing — unchanged. Rendered into HTML comment for log correlation. |
| `prior_corpus_intact` | `bool` | `True` / `False` | Existing — unchanged. Only the upload template uses it. |

**Mapping from backend exception to `category`**:

| Backend signal | `category` |
|---|---|
| `ValueError` raised by `answer_question` (bad input) | `validation` |
| `UpstreamProviderError` (Gemini / pgvector failure) | `server` |
| `RateLimitedError` (Gemini 429) | `rate_limited` |
| `InvalidPDFError` (magic-header validation) | `validation` |
| Oversize upload (FR-015 size cap) | `validation` |
| Concurrent upload (FR-028) | `concurrent` |
| `UploadCancelledError` | (not rendered as error — the existing cancelled flow stays) |
| Generic `Exception` in `_run_upload_task` | `server` |
| HTMX `htmx:sendError` (DOM-side network failure) | `network` (client-side template, never server-rendered) |
| HTMX `htmx:timeout` (60 s exceeded) | `network` |

**Field semantics**:
- `cause` and `message` keys (currently passed to `_upload_error.html`) are *removed from the template context*. The route handlers continue to *log* the same strings under their existing keys — no log fidelity is lost; only the visible UI text is restricted.

**Rationale**: This is the implementation of FR-004 + the 2026-05-13 clarify decision. By moving the category mapping into the route handler, the templates stay free of branching and the contract test (R7.3) can assert the category-coded strings are baked into the template, not threaded from the backend.

---

## V2 — `LoadingState` (DOM-only, not a server-side type)

Driven by HTMX class toggling on the form element:

| Class on form | Indicator visible? | Animation? |
|---|---|---|
| (none) | No | n/a |
| `.htmx-request` | Yes (`.htmx-indicator` opens) | `nymbl-pulse 1.5s ease-in-out infinite`, unless `prefers-reduced-motion: reduce` |

No Python type. The presence/absence of `.htmx-request` *is* the state. The upload flow keeps its richer staged progress view — that is a separate component (`.upload-progress-stages` with `--done` / `--active` / `--pending` modifiers) and is rebranded per R6, not redesigned.

---

## V3 — `Theme` (CSS-only, not a server-side type)

Driven entirely by `prefers-color-scheme`:

| OS preference | Active CSS variables |
|---|---|
| (no preference / light) | The base `:root` token set: `--bg: var(--paper-50)`, `--fg: var(--ink-900)`, `--border: var(--stone-100)`, `--accent: var(--signal-500)`, `--accent-fg: var(--ink-900)` |
| `prefers-color-scheme: dark` | Override block inside `@media (prefers-color-scheme: dark) { :root { ... } }` reapplies: `--bg: var(--ink-900)`, `--fg: var(--paper-50)`, `--fg-muted: var(--stone-300)`, `--border: var(--ink-700)`. `--accent` and `--accent-fg` stay identical (signal does not invert — FR-013). |

The stylesheet *also* defines a dormant `[data-theme="dark"]` selector with the same tokens so a future manual-toggle feature can reach for it without rewriting the cascade. No JS sets `data-theme` in this feature.

---

## V4 — `BrandToken` vocabulary (the CSS custom-property surface)

The stylesheet MUST define all of the following as CSS custom properties at `:root`. The contract test (R7.1) reads `styles.css` and asserts presence.

| Token group | Tokens | Defined values |
|---|---|---|
| Ink | `--ink-900`, `--ink-700` | `#0A0A0F`, `#1F2028` |
| Paper | `--paper-50`, `--paper-100` | `#F5F1E8`, `#EDE7D9` |
| Signal | `--signal-500`, `--signal-600` | `#DAFE5D`, `#B8DE3A` |
| Ember | `--ember-500` | `#E85A4F` |
| Stone | `--stone-50`, `--stone-100`, `--stone-200`, `--stone-300`, `--stone-500`, `--stone-700` | per brand guide §2.2 |
| Semantic | `--success`, `--warning`, `--danger`, `--info` | per brand guide §2.3 |
| Type families | `--font-display`, `--font-sans`, `--font-mono` | per brand guide §3.1 (full fallback stacks) |
| Type scale | `--text-display-2xl`, `--text-display-xl`, `--text-display-lg`, `--text-heading-xl`, `--text-heading-lg`, `--text-heading-md`, `--text-heading-sm`, `--text-body-lg`, `--text-body-md`, `--text-body-sm`, `--text-caption`, `--text-mono-md`, `--text-mono-sm` | size/line-height pairs per brand guide §3.3 |
| Surface aliases | `--bg`, `--fg`, `--fg-muted`, `--border`, `--accent`, `--accent-fg` | mapped from the core tokens above per V3 |
| Motion | `--motion-pulse-duration` | `1.5s` |

The contract test does not assert every alias is *used* in the rest of the stylesheet — only that the tokens are defined. The aliases are forward-compatible hooks; the type-scale tokens may be applied via utility classes or directly in element selectors as appropriate.

---

## V5 — A11y attributes (template context, fixed at template author time)

Not a runtime type — these are fixed attributes the templates MUST emit. The contract test asserts their presence after rendering.

| Element | Required attributes |
|---|---|
| `<section id="response">` (in `base.html`) | `aria-live="polite"` |
| `<div id="current-doc">` (in `base.html`) | `aria-live="polite"` |
| `.upload-progress` container (in `_upload_in_progress.html`) | `aria-live="polite"` (already implicit via parent, but we add it explicitly for clarity) |
| The root `<div>` of `_error.html` | `role="alert"` |
| The root `<div>` of `_upload_error.html` | `role="alert"` |
| The client-side network-error template that JS inserts | `role="alert"` |

---

## Relationships

- `ErrorView.category` → drives copy in `_error.html` / `_upload_error.html` (a six-line `{% if %}` ladder), which is wrapped in `role="alert"` (V5) and uses the `--danger` token from `BrandToken` (V4).
- `LoadingState` (DOM-only) → consumes `--signal-600` and `--motion-pulse-duration` from `BrandToken`.
- `Theme` → swaps the surface aliases inside `BrandToken`; everything else stays referenced through those aliases so dark mode "just works."
- The route handlers in `routes.py` are the only producer of `ErrorView`; no other code path constructs error template contexts.

---

## Out-of-scope

- The `QueryAnswered`, `QueryRefused`, `QueryNoDocuments`, and `ErrorResponse` Pydantic models in [src/rag/query/responses.py](../../src/rag/query/responses.py) are unchanged. Only the *template contexts* derived from them change.
- The chunk schema, embedding dimensionality, and ingest pipeline are unchanged.
- The `UploadJob` shape in [src/rag/ui/upload_jobs.py](../../src/rag/ui/upload_jobs.py) is unchanged.
