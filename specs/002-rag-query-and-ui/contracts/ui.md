# UI Contract — HTMX routes on FastAPI

Two routes on the existing FastAPI app deliver the browser UI per the 2026-05-12 Q1 clarification. The UI is the demo-friendly face of the JSON `POST /query` endpoint; both routes call the same underlying query function (R-018).

## Routes

### `GET /` — page shell

Renders the base Jinja2 template:

- `<form>` with a single `<textarea name="question">`, a submit button, and an empty `<div id="response">`.
- HTMX wiring on the form: `hx-post="/ui/query"`, `hx-target="#response"`, `hx-swap="innerHTML"`, `hx-indicator="#thinking"`.
- A hidden `<span id="thinking">Thinking…</span>` that HTMX un-hides via `hx-indicator` during the in-flight period (spec FR-021).
- A single `<link>` to one CSS file. No external CSS frameworks. No analytics, no third-party scripts (spec FR-022).
- Single inline `<script>` tag pinning the htmx.org version with SRI hash. No other JS.

Status: 200, `Content-Type: text/html; charset=utf-8`.

### `POST /ui/query` — form submit, returns HTML partial

Accepts `application/x-www-form-urlencoded` with `question=<string>`. Validation mirrors the JSON endpoint (non-empty, length cap). Calls the shared query function with `trace_id=uuid4().hex`. Renders one of three Jinja2 partials based on the query response's `status`:

- **`_answered.html`** — `<div class="status-answered">` containing the answer paragraph and a `<ul class="citations">` of `<li>` items, each with the page number badge, the 400-char quoted span (truncated cue if `truncated=true`), and the chunk_id in a `<small>` tag for reviewer cross-referencing (spec FR-019).
- **`_refused.html`** — `<div class="status-refused">` with the refusal message and a small badge labeled "Not in document". No citations rendered. Visually distinct CSS class so the styling separation is obvious to a glancing reviewer (spec FR-020).
- **`_no_documents.html`** — `<div class="status-empty">` showing the corpus-empty message and the ingest command in a `<code>` block (spec FR-014). Visually distinct from refusal.

All three partials include a trailing HTML comment `<!-- trace_id: <hex> -->` so the trace can be located by inspecting the rendered page during demo dry-runs (R-019). No visible trace surface — the comment is for the developer, not the reviewer.

Status: 200 on every success path (including refused / no_documents — those are not error states). 400 / 503 are returned with the JSON Error shape but `Accept`-negotiated to HTML; the UI partial in those cases renders a `<div class="status-error">` with the error code and message.

## Visual states — invariants (spec FR-020)

The three success states (`answered`, `refused`, `no_documents`) **MUST** be visually distinguishable at a glance. The contract specifies CSS class names; the exact colors and badges are implementation choices left to tasks.

| State | CSS class | Required cue |
|-------|-----------|--------------|
| Answered | `status-answered` | Answer text + citation list visible. Citation count and page badges visible. |
| Refused | `status-refused` | "Not in document" badge prominently visible. No citation block rendered. |
| No documents | `status-empty` | Ingest command rendered in a `<code>` element. No citation block rendered. |
| Error (400/503) | `status-error` | Error code visible (e.g., "upstream_gemini"). |

## What is intentionally NOT in the UI

- No client-side history (no localStorage, no IndexedDB).
- No multi-turn / chat history. The response area is replaced on every submit.
- No streaming partial responses (constitution Art VII).
- No authentication. The unauthenticated localhost UI assumes a local-dev trust boundary (spec Assumptions).
- No favicon battle, no dark mode toggle, no copy-to-clipboard, no share button. Polish is out of scope.

## Templates checked into the repo

| Template | Role |
|----------|------|
| `base.html` | Page shell, htmx script, form, response div, indicator. |
| `_answered.html` | Partial returned when `status=answered`. |
| `_refused.html` | Partial returned when `status=refused`. |
| `_no_documents.html` | Partial returned when `status=no_documents`. |
| `_error.html` | Partial returned on 400 / 503. |

Path under repo root is a task-level choice — see plan.md "Project Structure" → deferred.
