# Implementation Plan: Nymbl UI Polish & UX Fixes

**Branch**: `004-nymbl-ui-polish` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-nymbl-ui-polish/spec.md`

## Summary

Final polish pass on the assessment demo. Three deliverables, in priority order:

1. **Stop silent failures.** HTMX swallows non-2xx responses by default — the query and upload paths must render a visible error message and re-enable controls within 2 s on any 4xx/5xx, network drop, or timeout. The displayed copy is restricted to fixed generic categories (Server / Invalid input / Network) plus a retry affordance; the existing backend `detail` / `cause` strings stay in the response body for the log trail but never reach the visible UI (clarify decision, 2026-05-13). Error inserts carry `role="alert"` so screen readers preempt other speech; the `#response` region is `aria-live="polite"` for normal answer swaps.
2. **Replace the design system with the Nymbl brand foundations.** Drop the cool-gray, blue-accent token set in [styles.css](../../src/rag/ui/static/styles.css) and rebuild on the brand guide ([nymbl-brand.md](../../nymbl-brand.md)) — paper / ink surfaces, stone neutrals, signal chartreuse as a scalpel-applied single accent, Fraunces for display/headings (`opsz` set per size), Geist Sans for body/UI, Geist Mono for citations, page count, and chunk ids. Auto dark mode via `prefers-color-scheme`, no FOUC, no JS theme switch.
3. **Two small UX adjustments.** Replace the italic "Thinking…" line with a Geist Sans body line on a 1.5 s opacity pulse using the signal accent (static fallback under `prefers-reduced-motion: reduce`). Gate the paperclip upload so a confirmation appears only when a document is already ingested.

The feature touches presentation only — no route signatures, response schemas, or pipeline behavior change. All work lives under [src/rag/ui/](../../src/rag/ui/).

## Technical Context

**Language/Version**: Python 3.12 (constitution Article IV.1; unchanged)
**Primary Dependencies**: FastAPI + Pydantic v2 (server), Jinja2 templates (server), HTMX 2.0.3 (client, already pinned at [base.html:13](../../src/rag/ui/templates/base.html#L13)). No new server-side deps. No new JS framework — vanilla HTMX events and a small inline JS handler for the replace-confirmation are sufficient.
**Storage**: N/A for this feature (Postgres + pgvector unchanged).
**Testing**: pytest (existing), with new tests under [tests/unit/test_ui_routes.py](../../tests/unit/test_ui_routes.py) for the error-rendering contract and new contract tests for the CSS token surface and a11y attributes. No visual regression framework — rely on template assertions for structural checks and a manual checklist for visual polish.
**Target Platform**: Modern evergreen browsers (Chrome / Edge / Firefox / Safari, current and N-1). No IE, no legacy mobile.
**Project Type**: Existing single-project FastAPI + HTMX web service. UI lives under [src/rag/ui/](../../src/rag/ui/) (routes + Jinja templates + a single static CSS file). No frontend build step.
**Performance Goals**: First paint of correct theme under 100 ms after stylesheet parses (no FOUC). Pulse animation ≤16 ms frame budget on a 2017-class laptop. Error display latency ≤2 s from upstream failure to visible message (FR-001).
**Constraints**: WCAG AA contrast (4.5:1 body, 3:1 large text) in both light and dark themes; `prefers-reduced-motion: reduce` must degrade the indicator to static; the signal accent is never used as a large fill and never paired with paper foreground; one Fraunces display element per view.
**Scale/Scope**: Single-page app, one ingested PDF at a time, single user. No multi-tenant, no localization. The polish only affects ~10 partial templates + 1 stylesheet + 1 base template.

## Constitution Check

*Re-evaluated after Phase 1 design — no new violations introduced.*

| Article | Verdict | Notes |
|---|---|---|
| I — Grounding Is Non-Negotiable | PASS | Presentation-layer-only; the grounding pipeline (refusal path, retrieval threshold, post-gen check) is untouched. The refusal partial keeps its semantic meaning; only its visual treatment changes. |
| II — Citations Carry Real Provenance | PASS | Citation rendering retains page number, quoted span, and stable chunk_id. The chunk_id gets a Geist Mono treatment with tabular-nums per brand guide §3.4, which is a typographic upgrade — no data omitted. |
| III — Evaluation Before Demo | PASS | No retrieval, ranking, or judge path changes. Existing eval set + Recall@k/MRR remain valid. |
| IV — Stack Decisions Are Fixed | PASS | Stays on FastAPI + Jinja2 + HTMX + plain CSS. No new frontend framework, no Tailwind, no theme-switch JS library. Fraunces, Geist Sans, and Geist Mono are loaded from their canonical free hosts (Google Fonts and vercel.com/font respectively) as link/preload tags — no build step, no npm dep. |
| V — Developer Experience | PASS | `make up` still brings the app up. No new env vars. `.env.example` unchanged. The single CSS file remains under [src/rag/ui/static/styles.css](../../src/rag/ui/static/styles.css); no asset pipeline. |
| VI — Code Quality Floor | PASS | New tests under `tests/unit/`. No bare excepts in the small JS confirmation handler. Type hints on the unchanged Python (no new Python code is required beyond minor template-context tweaks). |
| VII — Scope Discipline | PASS | The constitution explicitly accepts "a minimal Streamlit page or single HTMX route" — polishing the HTMX route within the same scope envelope is fine. No multi-document corpora, no auth, no observability bolt-ons. |
| VIII — The Demo Is the Product | PASS | Polish materially improves the live-query walkthrough portion of the 30-minute demo. README screenshots (if any) will be refreshed in this branch. Commit history will be kept narratable. |

No violations to justify — Complexity Tracking section omitted.

## Project Structure

### Documentation (this feature)

```text
specs/004-nymbl-ui-polish/
├── plan.md                  # This file
├── research.md              # Phase 0 output
├── data-model.md            # Phase 1 output (view-model types)
├── quickstart.md            # Phase 1 output (manual verification recipe)
├── contracts/
│   ├── css-tokens.md        # The CSS variables the stylesheet MUST expose
│   ├── error-rendering.md   # Generic-category copy + role="alert" + status mapping
│   ├── a11y.md              # aria-live / role="alert" / prefers-reduced-motion contract
│   └── typography.md        # Font loading + type scale + tracking rules
└── checklists/
    └── requirements.md      # Created by /speckit-specify
```

### Source Code (repository root)

Only paths under [src/rag/ui/](../../src/rag/ui/) and [tests/unit/](../../tests/unit/) change. The route handlers in [src/rag/ui/routes.py](../../src/rag/ui/routes.py) need a small adjustment: the `_error.html` / `_upload_error.html` template contexts gain a `category` key (one of `server` / `validation` / `network` / `concurrent` / `rate_limited`); the raw `cause` / `message` strings move to log lines only and are no longer rendered. No new files in `src/`.

```text
src/rag/ui/
├── routes.py                                  # MODIFY — pass `category` instead of raw cause/message to error templates
├── static/
│   └── styles.css                             # REWRITE — brand tokens, type scale, dark mode, pulse animation
└── templates/
    ├── base.html                              # MODIFY — link brand fonts, add prefers-color-scheme hook, replace #thinking markup, add replace-confirmation handler, wire role="alert" container
    ├── _answered.html                         # MODIFY — eyebrow + Fraunces heading; Geist Mono on chunk_id; tabular-nums
    ├── _refused.html                          # MODIFY — generic refusal copy, ember accent for the badge (alert that isn't error)
    ├── _no_documents.html                     # MODIFY — generic "no document" treatment
    ├── _error.html                            # MODIFY — emit category-coded copy only; add role="alert"; keep retry CTA
    ├── _current_doc.html                      # MODIFY — Geist Mono on filename meta, brand surfaces
    ├── _upload_in_progress.html               # MODIFY — brand colors on the stage bar; pulse animation respects prefers-reduced-motion
    ├── _upload_success.html                   # MODIFY — brand surfaces; success uses --success token
    └── _upload_error.html                     # MODIFY — category-coded copy only; add role="alert"; remove raw `cause` block

tests/unit/
├── test_ui_routes.py                          # MODIFY — assert error partials emit category copy only (no raw cause/message)
└── test_ui_brand_contract.py                  # NEW — assert CSS tokens exist; assert templates carry expected a11y attrs; assert no #FFFFFF / #000000 / purple-gradient strings in styles.css
```

**Structure Decision**: Stay inside the existing single-project layout. No new package, no build step. The two unit-test files plus the one rewritten stylesheet and the touched-up Jinja templates are the entire delta. This keeps the diff narratable for Article VIII.

## Complexity Tracking

> No Constitution violations. This section is intentionally empty.
