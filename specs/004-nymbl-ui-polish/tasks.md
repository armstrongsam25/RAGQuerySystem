---

description: "Task list for feature 004 — Nymbl UI Polish & UX Fixes"
---

# Tasks: Nymbl UI Polish & UX Fixes

**Input**: Design documents from [/specs/004-nymbl-ui-polish/](./)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Tests are included because the contracts explicitly enumerate assertion-style checks (error-rendering categories, a11y attributes, CSS token presence). These are contract tests against the templates and stylesheet — not a TDD ceremony, just verifying the visible promises stay true.

**Organization**: Phases proceed in priority order from [spec.md](./spec.md). Within each user story, tasks split across files are marked `[P]` for parallel execution. The foundation must complete before any user-story work begins because every story touches the brand-token surface.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps task to a user story (US1–US5)
- All paths are repository-relative

## Path Conventions

Single-project FastAPI + HTMX layout. UI lives under [src/rag/ui/](../../src/rag/ui/); tests under [tests/](../../tests/). No build step.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify the workspace is in a known-good state before any presentation-layer changes land.

- [X] T001 Verify branch is `004-nymbl-ui-polish`, the spec/plan/research/data-model/contracts/quickstart files exist under `specs/004-nymbl-ui-polish/`, `make test` is green against the current `main`-equivalent code, and `make lint` (ruff) is clean. Capture baseline output for comparison after the feature lands.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Replace the cool-gray / blue-accent token vocabulary with the Nymbl brand foundations and load the brand fonts. Every user story below references these tokens, so this phase blocks all of them.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Add Nymbl font loading to `<head>` in `src/rag/ui/templates/base.html`: `<link rel="preconnect" href="https://fonts.googleapis.com">`, `<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>`, `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300..700&display=swap">`, and the two `geist@1.3.1` jsDelivr stylesheets per [contracts/typography.md](./contracts/typography.md).
- [X] T003 Replace the `:root` block in `src/rag/ui/static/styles.css` with the full brand-token surface per [contracts/css-tokens.md](./contracts/css-tokens.md): ink, paper, signal, ember, stone, semantic colors, the three font-family stacks, the type-scale tokens, the surface aliases (`--bg`, `--fg`, `--fg-muted`, `--border`, `--accent`, `--accent-fg`), and `--motion-pulse-duration: 1.5s`. Light-mode values only — dark mode and `[data-theme="dark"]` are deferred to US3.
- [X] T004 [P] Create `tests/unit/test_ui_brand_contract.py` with `test_css_tokens_defined`: read `src/rag/ui/static/styles.css` and assert every brand token from `contracts/css-tokens.md` is declared at `:root` with the brand-pinned value. Use plain regex / string assertions; no full CSS parser.

**Checkpoint**: Brand vocabulary lives in the stylesheet and fonts load on every page. The app now renders with brand colors but `_error.html`, the loading pulse, dark mode, and the replace-confirm gate are all still legacy. `T004` passes; the other contract tests do not yet exist.

---

## Phase 3: User Story 1 — Visible failure feedback (Priority: P1) 🎯 MVP

**Goal**: Backend failures, network drops, and timeouts produce a visible inline error card within 2 seconds. The card carries `role="alert"` so screen readers preempt; the submit control re-enables; the indicator clears; a Retry CTA is present.

**Independent Test**: Stop the DB (`docker compose stop db`), submit a query. Within 2 s a "Server error" card appears with body copy "Something went wrong on our end. Please try again." and a Retry button. The card does NOT contain the raw psycopg/connection-error text. Bring the DB back up, click Retry, query succeeds. Also verifiable with `tests/unit/test_ui_routes.py` and `tests/unit/test_ui_brand_contract.py` for the role/category contracts.

### Tests for User Story 1

- [X] T005 [P] [US1] Add five route tests to `tests/unit/test_ui_routes.py`: `test_query_503_renders_server_category`, `test_query_400_renders_validation_category`, `test_upload_409_renders_concurrent_category`, `test_upload_413_renders_validation_category`, `test_upload_invalid_pdf_renders_validation_category`. Each MUST assert the visible body contains the brand-pinned category copy AND does not contain raw backend strings (e.g., status codes, `psycopg`, `Gemini`, `RateLimited`, the literal cap-bytes value). Follow the assertions enumerated in [contracts/error-rendering.md](./contracts/error-rendering.md).
- [X] T006 [P] [US1] Add `test_error_partials_carry_role_alert` and `test_error_templates_dont_emit_raw_backend_strings` to `tests/unit/test_ui_brand_contract.py`: render `_error.html` and `_upload_error.html` directly and assert the root `<div>` carries `role="alert"`; grep the template source files for the substrings `{{ cause }}`, `{{ message }}`, and `{{ error.message }}` and assert zero matches.

### Implementation for User Story 1

- [X] T007 [US1] In `src/rag/ui/routes.py`, change every place that renders `_error.html` or `_upload_error.html` to pass `{"category": "<value>", "trace_id": trace_id, "prior_corpus_intact": ...}` instead of the existing `{"error": err.model_dump()}` / `{"cause": ..., "message": ...}` context. Use the mapping table in [contracts/error-rendering.md](./contracts/error-rendering.md) (`ValueError` → `validation`, `UpstreamProviderError` → `server`, `RateLimitedError` → `rate_limited`, concurrent-upload guard → `concurrent`, `InvalidPDFError` → `validation`, oversize → `validation`, generic `Exception` → `server`). Keep all existing log lines unchanged so logging fidelity is preserved.
- [X] T008 [P] [US1] Rewrite `src/rag/ui/templates/_error.html`: root `<div class="status-card status-error" role="alert">` with a `{% if category == "server" %}` ladder over the five categories, emitting the brand-pinned heading + body copy from `contracts/error-rendering.md`. Include a Retry button for all categories except `concurrent`. The Retry button re-fires the query form via HTMX (`hx-post="/ui/query"`, `hx-include="closest form, [name=question]"`). Strip the existing `{{ error.error }}` / `{{ error.message }}` interpolation entirely.
- [X] T009 [P] [US1] Rewrite `src/rag/ui/templates/_upload_error.html`: root `<div class="status-card status-upload-error" role="alert">` with the same five-category ladder; Retry button for all categories except `concurrent` and triggers the hidden file input (`onclick="document.getElementById('pdf-file').click()"`). Keep the existing `prior_corpus_intact` block since that's user-reassurance copy, not backend text. Strip `{{ cause }}` and `{{ message }}` interpolations.
- [X] T010 [US1] In `src/rag/ui/templates/base.html`: add `aria-live="polite"` to `<section id="response">` (replace the existing attribute or confirm it's present) and to `<div id="current-doc">`. Add `aria-live="polite"` to `.upload-progress` root in `src/rag/ui/templates/_upload_in_progress.html`.
- [X] T011 [US1] In `src/rag/ui/templates/base.html`: add `<template>` blocks at the end of `<body>` (before the closing tag) with ids `error-fallback-network` containing the brand-pinned `network` category markup (mirrors `_error.html` for the `network` case, including `role="alert"` and a Retry button). These are the static fallbacks the client-side JS will clone in.
- [X] T012 [US1] In `src/rag/ui/templates/base.html`: append an inline `<script>` block at the end of `<body>` (after the `<template>` blocks) that registers three listeners on `document.body`: `htmx:sendError` and `htmx:timeout` clone the `#error-fallback-network` template content into `event.detail.requestConfig.target` (default `#response`) and remove the `.htmx-request` class from the issuing form. `htmx:responseError` is a no-op (server-rendered error partial already swapped in by HTMX). The script MUST NOT log or expose `event.detail.xhr.responseText`. Keep it under 30 lines.
- [X] T013 [US1] In `src/rag/ui/templates/base.html`: on the query form `<form hx-post="/ui/query" ...>`, add `hx-request='"timeout": 60000'` so queries error out client-side after 60 s (FR-001 timeout edge case). Upload form does not need a timeout (it polls).
- [X] T014 [US1] In `src/rag/ui/static/styles.css`: add or update `.status-error` to use `border-left-color: var(--danger)`; `.badge-error` uses `background: color-mix(in srgb, var(--danger) 12%, var(--bg))` and `color: var(--danger)`. Add `.btn-retry` styling — outlined ink-on-paper button matching the `.btn-clear` shape, but with `--fg` instead of `--danger`. (`.btn-retry` is referenced by the Retry CTA in T008/T009.)

**Checkpoint**: User Story 1 is complete and independently testable. `make test` runs T005 + T006 green. Manual: kill the DB, submit a query, the error card appears within 2 s and Retry works. Screen reader announces errors preempting other speech.

---

## Phase 4: User Story 2 — Apply Nymbl visual identity (Priority: P1)

**Goal**: Every visible surface uses brand tokens, every text element uses the brand type families with the right size/weight/feature flags, the chartreuse signal accent appears on at most one primary action per view, no purple, no `#FFFFFF`/`#000000`, no third typeface. Citations gain Geist Mono with tabular numerals.

**Independent Test**: Open the app, walk through the visual brand audit checklist in [quickstart.md §2](./quickstart.md). Specifically: sample the background pixel (must be `#F5F1E8`), confirm Fraunces on the page heading and Geist on body, count chartreuse elements on screen (exactly one — the Ask button), verify no purple anywhere. Plus `tests/unit/test_ui_brand_contract.py::test_no_forbidden_strings_in_styles` passes.

### Tests for User Story 2

- [X] T015 [P] [US2] Add `test_no_forbidden_strings_in_styles` and `test_aria_attributes_on_base_template` to `tests/unit/test_ui_brand_contract.py`: the first reads `src/rag/ui/static/styles.css` and asserts zero matches for `#ffffff`, `#FFFFFF`, `#fff` (whole-token via `\b`), `#000000`, `#000` (whole-token), `rgb(255, 255, 255)`, `rgb(0, 0, 0)`, and the case-insensitive literal `purple`. The second renders `base.html` via Jinja2 and asserts `#response`, `#current-doc`, and the upload-progress root carry `aria-live="polite"`.

### Implementation for User Story 2

- [X] T016 [US2] In `src/rag/ui/static/styles.css`: migrate the global `body` rule to `font-family: var(--font-sans); font-size: 16px; line-height: 24px; color: var(--fg); background: var(--bg);`. Migrate `header h1` to `font-family: var(--font-display); font-size: 28px; line-height: 34px; font-weight: 500; font-variation-settings: "opsz" 36; letter-spacing: -0.02em;`. Migrate `.subtitle` to `color: var(--fg-muted); font-size: 16px;`. Drop all references to `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue"` (replaced by `--font-sans`).
- [X] T017 [US2] In `src/rag/ui/static/styles.css`: migrate `.input-group` to `background: var(--bg); border: 1px solid var(--border); border-radius: 12px;`. `.input-group:focus-within` uses `border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 35%, transparent);`. Textarea uses `--font-sans`, `color: var(--fg)`. The `.input-group-actions` strip uses `background: transparent; border-left: 1px solid var(--border);`. The paperclip-btn hover/focus rebinds to `var(--accent)` tints (using `color-mix(in srgb, var(--signal-500) 12%, transparent)` for the hover bg and `var(--ink-900)` for hovered icon color since signal+ink is the brand-approved pairing). `.btn-ask` becomes `background: var(--accent); color: var(--accent-fg); font-weight: 600; border-radius: 8px;` with `:hover` background `var(--signal-600)`. `.btn-ask:disabled` uses `background: var(--stone-200); color: var(--fg-muted);`. Focus shadow uses signal-tinted color-mix.
- [X] T018 [US2] In `src/rag/ui/static/styles.css`: migrate `.current-doc-card` background to `var(--bg)`, border to `var(--border)`. `.current-doc-label` becomes the eyebrow pattern: `font-family: var(--font-sans); font-size: 12px; line-height: 16px; font-weight: 500; color: var(--fg-muted); text-transform: uppercase; letter-spacing: 0.04em;`. `.current-doc-name` uses `font-family: var(--font-sans); font-weight: 600; color: var(--fg);` (drop the legacy accent-blue color). `.current-doc-meta` becomes `font-family: var(--font-mono); font-size: 12px; line-height: 18px; color: var(--fg-muted); font-variant-numeric: tabular-nums; font-feature-settings: "ss01", "zero", "cv11";`. `.btn-clear` uses `--danger` for border + color, hover fills with `--danger` and uses `--bg` as foreground.
- [X] T019 [US2] In `src/rag/ui/static/styles.css`: rebrand `.status-card` to `background: var(--bg); border-left: 6px solid var(--fg-muted); border-radius: 8px;` and remove the legacy hard-coded shadow value (replace with `box-shadow: 0 1px 2px color-mix(in srgb, var(--fg) 6%, transparent);`). Status modifiers: `.status-answered` → `border-left-color: var(--success)`, `.status-refused` → `var(--ember-500)`, `.status-empty` → `var(--info)`, `.status-error` → `var(--danger)` (already done in T014), `.status-upload` → `var(--stone-700)`, `.status-upload-error` → `var(--danger)`. Badge backgrounds use `color-mix(in srgb, <token> 14%, var(--bg))` and text uses the token directly.
- [X] T020 [US2] In `src/rag/ui/static/styles.css`: rebrand the upload-progress stage bar. `.upload-progress` border-left becomes `var(--stone-700)`. `.badge-upload-pending` background uses `color-mix(in srgb, var(--stone-700) 12%, var(--bg))` with stone-700 text. `.upload-progress-stage-dot` default → `background: var(--bg); border-color: var(--border); color: var(--fg-muted);`. `--done` dot uses `--success` background+border and `--accent-fg` text. `--active` dot uses `var(--signal-500)` background, `var(--ink-900)` foreground, and `var(--signal-600)` border. `--pending` dot uses `var(--stone-200)` border, `var(--stone-300)` text. Replace the `upload-stage-pulse` keyframe rgba values with `color-mix` against `--signal-500`. The `upload-spinner` border color inherits via `currentColor` so it follows the badge text color — no change needed. `.upload-progress-stage-label` becomes the eyebrow pattern (sans, 12px, 600, uppercase, +0.04em).
- [X] T021 [US2] In `src/rag/ui/static/styles.css`: rebrand citations. `h3` (existing rule) becomes the eyebrow pattern: `font-family: var(--font-sans); font-size: 12px; line-height: 16px; font-weight: 500; color: var(--fg-muted); text-transform: uppercase; letter-spacing: 0.04em;`. `.page-badge` becomes `font-family: var(--font-mono); font-size: 12px; line-height: 18px; background: color-mix(in srgb, var(--accent) 20%, var(--bg)); color: var(--ink-900); padding: 0.1rem 0.5rem; border-radius: 3px; font-variant-numeric: tabular-nums; font-feature-settings: "ss01", "zero", "cv11";`. `blockquote` drops `font-style: italic`, uses `border-left: 3px solid var(--border); color: var(--fg-muted); font-family: var(--font-sans);`. `.chunk-id` uses `font-family: var(--font-mono); font-size: 12px; line-height: 18px; color: var(--fg-muted); font-feature-settings: "ss01", "zero", "cv11";`. `pre` / `code` background → `var(--paper-100)` (or stone-50 in light mode); `code` font-family → `var(--font-mono)`.
- [X] T022 [P] [US2] In `src/rag/ui/static/styles.css`: add `max-inline-size: 68ch` to `.answer`, `.refusal-message`, `.upload-progress-message`, and any other prose container (header `<p class="subtitle">`). This implements brand-guide §3.5 (62–74 char line length, hard-cap 68ch).
- [X] T023 [P] [US2] In `src/rag/ui/static/styles.css`: migrate `footer` and `footer small`. `footer` uses `font-family: var(--font-sans); color: var(--fg-muted); font-size: 14px; line-height: 20px;`. `footer a` uses `color: var(--accent-fg)` with `text-decoration: underline; text-decoration-color: var(--signal-600);` so the underline reads as a Nymbl-signal accent rather than the legacy blue.
- [X] T024 [P] [US2] Globally find-replace remaining legacy `--color-accent` / `--color-text` / `--color-text-muted` / `--color-bg` / `--color-card-bg` / `--color-border` / `--color-border-strong` / `--color-text-subtle` / `--color-danger` / `--color-danger-dark` / `--color-accent-dark` / `--shadow-sm` / `--shadow-focus` references in `src/rag/ui/static/styles.css` so they all use the brand aliases (`--fg`, `--fg-muted`, `--bg`, `--border`, `--accent`, `--danger`). Remove the legacy custom-property declarations from `:root` once all references are migrated. This is the "no stragglers" cleanup task — easy to forget, hard to detect by eye, but the `test_no_forbidden_strings_in_styles` test indirectly catches the hex literals that backed them.
- [X] T025 [P] [US2] In `src/rag/ui/templates/_answered.html`, wrap the `chunk_id` value in a `<code>` tag so it picks up the mono treatment (`<small class="chunk-id">chunk_id: <code>{{ c.chunk_id }}</code></small>`). No other template changes for US2.

**Checkpoint**: User Story 2 is complete. App now renders fully Nymbl-branded in light mode. `make test` runs T015 green plus T004/T005/T006 still pass. Manual: walk the quickstart §2 brand audit.

---

## Phase 5: User Story 3 — Dark mode that respects system preference (Priority: P2)

**Goal**: Auto-switch to ink-on-paper-inverted theme when `prefers-color-scheme: dark` is reported, with no FOUC and the signal accent preserved.

**Independent Test**: Set OS appearance to dark, reload — page renders dark on first paint (no flash of light). Switch OS back to light, reload — page renders light. Quickstart §3.

### Implementation for User Story 3

- [X] T026 [US3] In `src/rag/ui/static/styles.css`: add `@media (prefers-color-scheme: dark) { :root { --bg: var(--ink-900); --fg: var(--paper-50); --fg-muted: var(--stone-300); --border: var(--ink-700); /* --accent + --accent-fg unchanged so signal stays chartreuse-on-ink */ } }`. Place the block immediately after the light-mode `:root` declaration.
- [X] T027 [US3] In `src/rag/ui/static/styles.css`: add a dormant `[data-theme="dark"] { ... same overrides ... }` block right after the media query. No JS sets `data-theme` in this feature — this is an escape hatch for a future manual-toggle work item.
- [X] T028 [US3] In `src/rag/ui/static/styles.css`: inside `@media (prefers-color-scheme: dark)`, add overrides for the few elements that need explicit dark-mode treatment beyond the surface-alias swap:
  - `.htmx-indicator` → `color: var(--signal-500)` (signal-500 reads better against ink than signal-600).
  - `.input-group-actions` → `background: transparent;` (no change, just confirm cascade order is right).
  - `.status-card box-shadow` → `box-shadow: 0 1px 2px color-mix(in srgb, var(--ink-900) 40%, transparent);` (deeper shadow on dark surface).
  - Any badge using `color-mix(...12%, var(--bg))` will recompute against the new `--bg` automatically — no change needed.
  - `pre`, `code` background → `var(--ink-700)` (inside the dark media block).
- [X] T029 [US3] Manual verification only — open the app with OS in dark mode and walk the quickstart §3 checkboxes. No new automated test (visual rendering is out of scope for the unit test suite per [research.md R7](./research.md)).

**Checkpoint**: Dark mode renders correctly on first paint, signal stays chartreuse, all five status cards have legible contrast against the new dark surface. `make test` still green; quickstart §3 passes.

---

## Phase 6: User Story 4 — Polished pulsing loading indicator (Priority: P2)

**Goal**: Replace the italic "Thinking…" text with a Geist Sans body-lg line pulsing on a 1.5 s opacity cycle using the signal-600 accent; static under `prefers-reduced-motion: reduce`.

**Independent Test**: Submit a query that takes >1 second. The "Thinking…" line pulses between 0.45 and 1.0 opacity smoothly. Toggle OS reduce-motion on, reload, submit again — line is static at full opacity. Quickstart §5.

### Implementation for User Story 4

- [X] T030 [US4] In `src/rag/ui/static/styles.css`: replace the existing `.htmx-indicator { display: none; color: var(--color-text-muted); font-style: italic; }` rule with the brand-pinned version: `.htmx-indicator { display: none; color: var(--signal-600); font-family: var(--font-sans); font-size: 18px; line-height: 28px; font-weight: 500; letter-spacing: 0; }` and update the two follow-up rules (`.htmx-request .htmx-indicator` and `.htmx-request.htmx-indicator`) to `display: inline; animation: nymbl-pulse var(--motion-pulse-duration) ease-in-out infinite;`.
- [X] T031 [US4] In `src/rag/ui/static/styles.css`: add the keyframe block: `@keyframes nymbl-pulse { 0%, 100% { opacity: 0.45; } 50% { opacity: 1; } }`. Place it near the other `@keyframes` (around the existing `upload-spin` and `upload-stage-pulse`).
- [X] T032 [US4] In `src/rag/ui/static/styles.css`: add `@media (prefers-reduced-motion: reduce) { .htmx-request .htmx-indicator, .htmx-request.htmx-indicator, .upload-progress-stage--active .upload-progress-stage-dot { animation: none; opacity: 1; } }` per [contracts/a11y.md](./contracts/a11y.md). Place it after the keyframes so cascade order works.

**Checkpoint**: Loading state pulses politely; reduced-motion users see static text. Quickstart §5 passes.

---

## Phase 7: User Story 5 — Replace-document confirmation (Priority: P3)

**Goal**: Gate the paperclip upload so picking a new PDF triggers a native confirm dialog when (and only when) a document is already ingested.

**Independent Test**: Start with no document → paperclip → pick PDF → upload proceeds with no prompt. With a doc ingested → paperclip → pick PDF → confirm dialog appears. Cancel → existing doc unchanged. OK → upload proceeds. Quickstart §6.

### Implementation for User Story 5

- [X] T033 [US5] In `src/rag/ui/templates/base.html`: extend the inline `<script>` block (added in T012) with a `maybeConfirmReplace(input)` helper that reads `document.querySelector('.current-doc-card')` to detect "has document," runs `confirm('Replace the current document? This cannot be undone.')` only when one exists, clears `input.value` on cancel, and dispatches the form submit on accept. Copy is anchored to the exact wording in [research.md R5](./research.md).
- [X] T034 [US5] In `src/rag/ui/templates/base.html`: replace the `onchange="this.form.dispatchEvent(...)"` handler on `<input type="file" id="pdf-file">` with `onchange="maybeConfirmReplace(this)"`. Keep the file input otherwise unchanged.

**Checkpoint**: Replace-confirm gates only when needed; first upload still seamless. Quickstart §6 passes.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final verification, README refresh, and demo dry-run per constitution Article VIII.

- [X] T035 [P] Run `make test` and confirm all five route tests (T005), all four contract tests (T004 + T006 + T015), every prior-feature test, and the existing UI test still pass. Capture the test count and elapsed time for the PR description.
- [X] T036 [P] Run `make lint` (ruff) and confirm zero new warnings. The inline `<script>` block in `base.html` is HTML, not Python — no ruff scope.
- [X] T037 Walk the full [quickstart.md](./quickstart.md) §2–§7 manually in a real browser (Chrome AND Firefox at minimum — Safari if available). Tick every checkbox. Note any visual oddities. Run the screen reader smoke test (§7) with VoiceOver or NVDA.
- [X] T038 If `README.md` contains screenshots of the prior UI, replace them with refreshed light + dark mode pairs of the new design. Update any README narrative that describes the UI surface (status-card colors, loading indicator description) to match the new behavior. Per constitution Article VIII.3 — the README MUST stand alone.
- [X] T039 Demo dry-run: time a full architecture walkthrough + live query + limitations rundown end-to-end against this branch. Confirm it fits in the 30-minute budget (Article VIII.6). The polish should not add demo runtime — it lives in the live-query visual surface only.

**Checkpoint**: Feature is demo-ready. Final commit follows.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 only; no prereqs.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS every user story phase.
- **US1 / US2 / US3 / US4 / US5**: Depend on Foundational. Within a single-developer execution they run sequentially in priority order (P1 → P2 → P3); within a parallel-team execution US3 + US4 + US5 can begin once US1 and US2 stabilize (they all touch `styles.css`).
- **Polish (Phase 8)**: Depends on every user story being complete.

### Within-File Dependencies (single-developer order)

`src/rag/ui/static/styles.css` is touched by:
- T003 (foundation `:root`)
- T014 (US1 status-error + retry button)
- T016, T017, T018, T019, T020, T021, T022, T023, T024 (US2)
- T026, T027, T028 (US3)
- T030, T031, T032 (US4)

When working solo, follow the task order; the file diff is cumulative and idempotent (every later task assumes the brand tokens from T003 exist).

`src/rag/ui/templates/base.html` is touched by:
- T002 (foundation font links)
- T010, T011, T012, T013 (US1)
- T033, T034 (US5)

Solo: in numerical order. Parallel: not safe — same file.

### Parallel Opportunities

- **In Foundation**: T002 (base.html) and T004 (test file) run parallel to T003 (styles.css). T002 ∥ T003 ∥ T004.
- **In US1 tests**: T005 (route tests) ∥ T006 (contract tests, different test file).
- **In US1 implementation**: T008 (`_error.html`) ∥ T009 (`_upload_error.html`) — different files. T007 (routes.py) is also independent of the templates and can run first. T010–T013 all touch `base.html` — sequential. T014 touches `styles.css` — independent of the template work.
- **In US2**: T015 (test additions) ∥ T022 (max-inline-size) ∥ T023 (footer) ∥ T024 (legacy-token cleanup) ∥ T025 (`_answered.html`) — five different concerns, three different files. The core T016–T021 sequence on `styles.css` is sequential.
- **In Polish**: T035 (test) ∥ T036 (lint) run together.

---

## Parallel Example: User Story 1

```bash
# Foundation finished. Launch in parallel:
Task: "T005 — Add five route tests to tests/unit/test_ui_routes.py"
Task: "T006 — Add role/no-leak contract tests to tests/unit/test_ui_brand_contract.py"

# Tests in place. Now launch the template work in parallel with the route refactor:
Task: "T007 — Refactor routes.py to pass category-coded contexts"
Task: "T008 — Rewrite _error.html"
Task: "T009 — Rewrite _upload_error.html"

# Then sequentially on base.html (same file):
Task: "T010 — Add aria-live attributes"
Task: "T011 — Add <template> blocks for client-side errors"
Task: "T012 — Wire HTMX event listeners"
Task: "T013 — Add hx-request timeout to query form"

# CSS work runs whenever (different file):
Task: "T014 — .status-error / .btn-retry styling"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001).
2. Complete Phase 2: Foundational (T002, T003, T004) — BLOCKS all stories.
3. Complete Phase 3: User Story 1 (T005–T014).
4. **STOP and VALIDATE**: Run `make test`, then manually verify the four error scenarios in quickstart §4.
5. The MVP is "the app no longer silently freezes on backend failures." Even shipping just this would close the only `Critical` finding in [ui_ux_review.md](../../ui_ux_review.md).

### Incremental Delivery

1. Setup + Foundation → brand tokens live.
2. + US1 → silent failures fixed (MVP demoable).
3. + US2 → full Nymbl visual identity in light mode.
4. + US3 → dark mode.
5. + US4 → pulsing indicator polish.
6. + US5 → replace-confirm gate.
7. + Polish → README refresh, demo dry-run, commit.

Each increment is independently demoable and adds visible value.

### Solo Strategy (most likely for this assessment)

Linear execution, T001 → T039. The dependency graph is shallow enough that solo execution loses nothing to a team-parallel run. Commit boundaries: one commit per phase (or per logical sub-phase within US2 if the diff gets large), narratable per Article VIII.

---

## Notes

- The brand-token migration is mechanical but extensive — most of US2 is replacing one CSS variable name with another. Use the contracts file as the source of truth, not memory.
- The legacy `--color-*` and `--shadow-*` custom properties are deleted in T024. Until that task runs, both legacy and brand tokens coexist; that's fine — the legacy tokens just become unused. T024 is the cleanup pass that removes them.
- Every task in this list maps cleanly to an FR in [spec.md](./spec.md) or a contract assertion in [contracts/](./contracts/). If a future task arises that doesn't, pause and ask whether the spec needs updating before adding work.
- Commit messages follow constitutional clean-history rules. Recommended cadence: one commit per phase (`feat(ui): foundation — brand tokens + font loading`, `feat(ui): US1 — visible error feedback`, etc.).
