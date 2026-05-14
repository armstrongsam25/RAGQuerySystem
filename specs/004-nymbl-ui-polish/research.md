# Phase 0 Research: Nymbl UI Polish & UX Fixes

Findings collected before design begins. Each item resolves an open implementation question raised by the spec or surfaced while reading the current code.

---

## R1 — HTMX error handling pattern

**Question**: How do we make HTMX surface backend failures and network errors as visible content without writing a JavaScript framework?

**Decision**: Use HTMX's built-in `htmx:responseError`, `htmx:sendError`, and `htmx:timeout` events, hooked globally via a `<script>` block in [base.html](../../src/rag/ui/templates/base.html). On any of those events, swap a pre-rendered server partial into `#response` (or `#upload-progress-*` for in-flight uploads) and remove the `.htmx-request` class so the indicator clears. The partial is a static HTML string emitted into a `<template id="error-fallback-*">` block at page load, keyed by category. The submit button re-enables automatically once `htmx-request` is removed because we use `hx-disabled-elt` and HTMX restores it on `htmx:afterRequest`.

**Rationale**:
- `hx-on::response-error` (the inline attribute the review suggested) works for one element but doesn't cover `htmx:sendError` (network/CORS) or `htmx:timeout` — three event hooks need three handlers. A single global listener is simpler and more reliable.
- The review's "innerHTML = 'An error occurred.'" recipe replaces the whole form with text, which destroys the question textarea. We need to target `#response`, not `this`.
- Pre-rendering the error markup server-side (as a `<template>`) keeps the visual treatment consistent with all the other status cards and lets the styles stay in CSS instead of being string-built in JS.

**Alternatives considered**:
- *Per-element `hx-on::response-error`*: less code initially but doesn't cover network errors and duplicates the handler on every form. Rejected.
- *htmx-response-targets extension*: lets you route specific status codes to specific swap targets. Powerful, but adds a script dependency and our needs are simple enough for vanilla events. Rejected.
- *Returning a custom `HX-Retarget` header from FastAPI on errors*: would let the server redirect the swap. But it only works on non-2xx if we still produce a response body, and it adds two-way coupling between routes and presentation. The route handlers already produce error partials with non-2xx status codes — HTMX just ignores those by default unless we wire the event. Wiring the event is the smaller change.

**Implementation note**: HTMX's default behavior with `hx-disabled-elt` is to restore the disabled element on `htmx:afterRequest` regardless of status. That's verified by reading the HTMX 2.0.3 source (the `restoreDisabledElement` runs in `afterRequestCleanup`). So we get button re-enable for free; we only need to clear the loading indicator and swap in the error.

**Timeout policy**: Set `hx-request='"timeout": 60000'` on the query form (60 s) — the constitution doesn't pin a timeout, but the answer pipeline tops out around 30 s in observed runs and 60 s is a generous ceiling. Uploads inherit their progress polling so no `hx-request` timeout is needed; the 60 s only applies to the synchronous query path.

---

## R2 — Dark mode without FOUC

**Question**: Should dark mode be implemented purely via `@media (prefers-color-scheme: dark)` or via a `data-theme="dark"` attribute set by JS at the top of `<head>`?

**Decision**: Use the pure `@media (prefers-color-scheme: dark)` CSS approach. The brand guide's CSS sample shows `[data-theme="dark"]` for *manual* override; we don't need a manual switch (the spec assumptions section excludes it), and the media-query path renders the correct theme on first paint with zero JS execution. We keep the `[data-theme="dark"]` selector in the stylesheet too as an inert escape hatch for future manual-toggle work, but no JS sets it in this feature.

**Rationale**:
- Pure CSS media query renders the right theme synchronously while the stylesheet parses — no FOUC, no inline script needed, and it satisfies FR-012 (correct theme on first paint) trivially.
- Inlining a `<script>` in `<head>` to set `data-theme` *would* avoid FOUC, but it forces every page load to execute JS before paint, which is heavier than what the demo needs.
- The `system / light / dark` triple state pattern (with `localStorage`) is the standard for apps that want manual override. We don't.

**Alternatives considered**:
- *Manual theme toggle button + `data-theme` attribute + localStorage*: spec assumes "dark mode follows OS preference automatically — manual toggle is out of scope," rejected.
- *No dark mode at all*: rejected — explicit spec requirement (US3, FR-011..014).

**Edge case**: macOS Safari historically delayed `prefers-color-scheme` evaluation when the stylesheet was loaded with `media="(prefers-color-scheme: dark)"` on its `<link>` element. Solution: keep a single stylesheet and put the media query *inside* the CSS — Safari's documented bug doesn't apply there.

---

## R3 — Font loading strategy

**Question**: How do we load Fraunces, Geist Sans, and Geist Mono without breaking first paint or violating the brand guide's "no FOUC of opposite theme" requirement?

**Decision**: Load via two `<link>` tags in `<head>`:
1. `<link rel="preconnect" href="https://fonts.googleapis.com">` and `<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>` for Google Fonts (Fraunces).
2. A single `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300..700&display=swap">` with the variable axes Fraunces needs (per brand guide §3.2).
3. Geist Sans and Geist Mono come from `https://cdn.jsdelivr.net/npm/geist@1/...` (CDN-hosted, free) — vercel.com/font's canonical distribution is also via jsDelivr, so we link the published CSS shim there. `display=swap` is the default for the Geist shim.

`font-display: swap` ensures text renders with the fallback stack (`"Iowan Old Style", Georgia, serif` for display, `ui-sans-serif, system-ui, sans-serif` for body) until the brand fonts arrive — this satisfies FR-005's fallback requirement and the edge case for Google-Fonts blocking. We do *not* `preload` the font files individually; that would force-fetch every weight and `opsz` slice and is overkill for an assessment demo.

**Rationale**:
- Self-hosting all three fonts (woff2 files in `src/rag/ui/static/`) would be more reliable on a corporate firewall but adds ~200 KB of binary to the repo and a Make target for refreshing them. The brand guide explicitly lists "Google Fonts" as the source for Fraunces and "vercel.com/font" for Geist — using the canonical hosts honors the brand guide and keeps the repo lean.
- `font-display: swap` is mandatory; without it, Chrome's "block period" hides text for up to 3 s and the FOUC edge case in the spec fails.

**Alternatives considered**:
- *Self-host all three families*: rejected (size + brittleness of refresh process).
- *Use `font-display: optional` for the variable Fraunces*: would risk Fraunces never appearing on slow connections, which is the *whole point* of the brand identity. Rejected.

---

## R4 — Pulsing-text loading indicator

**Question**: What's the simplest CSS implementation of "single line of Geist Sans on a slow opacity pulse using the signal accent" that respects `prefers-reduced-motion`?

**Decision**:

```css
.htmx-indicator {
  display: none;
  color: var(--signal-600); /* signal-600 sits better on paper than signal-500 (3.6:1 vs 1.3:1) */
  font-family: var(--font-sans);
  font-weight: 500;
  letter-spacing: 0;
}
.htmx-request .htmx-indicator,
.htmx-request.htmx-indicator {
  display: inline;
  animation: nymbl-pulse 1.5s ease-in-out infinite;
}
@keyframes nymbl-pulse {
  0%, 100% { opacity: 0.45; }
  50%      { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .htmx-request .htmx-indicator,
  .htmx-request.htmx-indicator {
    animation: none;
    opacity: 1;
  }
}
```

The text color uses `--signal-600` (the brand "hover/pressed" chartreuse, hex `#B8DE3A`) rather than `--signal-500` because §2.5 of the brand guide records `paper-50 on signal-500` at 1.3:1 — and the symmetric pairing (`signal-500` text on paper) inherits the same contrast problem. `--signal-600` against `--paper-50` reaches ~3.6:1, AA Large only, which is fine for a single-line indicator (≥18px Geist Sans at body-lg). In dark mode, the text uses `--signal-500` directly against `--ink-900` (~14:1, easily AA).

**Rationale**: Opacity-only animation is GPU-cheap and doesn't trigger reflow. The 1.5 s cycle matches the "subtle" brand mood — slower than a typical spinner and closer to a breath. `prefers-reduced-motion` short-circuits the animation entirely (not just slows it) per WCAG 2.3.3.

**Alternatives considered**: keyframed brightness/saturation filters (heavier on Safari), three-dot "Thinking…" with sequenced opacity per dot (more design surface, more brittle). Both rejected as bigger than needed.

---

## R5 — Replace-document confirmation gating

**Question**: How do we conditionally show the confirm dialog only when a document is already ingested?

**Decision**: The current-doc indicator is rendered into `#current-doc` on page load (see [base.html:26](../../src/rag/ui/templates/base.html#L26)). When non-empty it produces `.current-doc-card`; when empty it produces `.current-doc-empty`. The paperclip's `onchange` handler reads `document.querySelector('.current-doc-card')` — if it exists, fire `confirm('Replace the current document? This cannot be undone.')` and submit only on accept; if it doesn't exist, submit unconditionally. No new server-side state, no API change.

```js
function maybeConfirmReplace(input) {
  const hasDoc = document.querySelector('.current-doc-card') !== null;
  if (hasDoc && !confirm('Replace the current document? This cannot be undone.')) {
    input.value = '';
    return;
  }
  input.form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  input.value = '';
}
```

Wired as `onchange="maybeConfirmReplace(this)"` on the hidden file input.

**Rationale**:
- Native `confirm()` is consistent with the existing "Clear document" button which uses `hx-confirm` (also a native dialog). Matching the existing affordance avoids two confirmation styles in one app.
- The `.current-doc-card` class is already authoritative for the "has document" state — it's emitted only inside the `{% if docs %}` branch of [_current_doc.html](../../src/rag/ui/templates/_current_doc.html). Querying the DOM avoids needing a server flag.
- The clarify pass explicitly approved native `confirm()` and rejected a custom modal.

**Alternatives considered**:
- *Always confirm, including on first upload*: noisy and contradicts the spec ("no document is currently ingested ... upload proceeds without a confirmation prompt" — US5 acceptance scenario 1).
- *Server-side flag rendered into a data attribute on the file input*: more plumbing, no win over reading the existing DOM class.

---

## R6 — Brand surface mapping for the existing status cards

**Question**: The current stylesheet uses unbranded badges (green for "Answered", orange for "Refused", blue for "Empty corpus", red for "Error", purple for "Upload"). How do we rebrand without losing semantic distinction?

**Decision**:

| Existing card | Existing accent | New accent | Reasoning |
|---|---|---|---|
| `.status-answered` / `.badge-answered` | green `#2e7d32` | `--success` (`#3F8F5C`) | Brand semantic token for confirmations. |
| `.status-refused` / `.badge-refused` | orange `#ed6c02` | `--ember-500` (`#E85A4F`) | Brand guide §2.4: "Ember is for emphasis, not error." The grounded-refusal path is "the answer isn't in the document" — emphasis, not error. Perfect fit. |
| `.status-empty` / `.badge-empty` | blue `#0288d1` | `--info` (`#4A6FA5`) | Brand neutral informational token. |
| `.status-error` / `.badge-error` | red `#c62828` | `--danger` (`#C7372F`) | Brand semantic error. |
| `.status-upload` / `.badge-upload` | purple `#6a1b9a` | `--stone-700` (`#403B30`) | Brand guide §2.4: "No purple gradients. Ever." The success-after-upload card moves to a stone treatment with a `--success` border-left tick — keeps the celebratory accent in green but drops the purple completely. |
| `.upload-progress` / `.badge-upload-pending` | purple `#5e35b1` | `--stone-500` text on `--stone-100` card + `--signal-600` active-stage dot | Active stage gets the brand accent (the one spotlight); completed stages use `--success`; pending stages use `--stone-300`. |

This preserves the visual differentiation between the six card types while bringing every accent inside the brand palette. The `60/30/10` rule is honored: the chartreuse signal appears only on the active stage in the upload progress bar and on the primary "Ask" button — never two at once on the same view, because the upload-in-progress card replaces the answer card.

**Rationale**: The brand guide's semantic tokens (success / warning / danger / info) cover four of six cards directly; ember covers the fifth (refusal-as-emphasis); the sixth (in-progress upload) sits naturally in stone with one signal-coloured dot.

**Alternatives considered**: *Keep purple as a unique "in-flight" hue*: rejected — direct brand-guide violation.

---

## R7 — Test strategy for visual/brand contract

**Question**: How do we verify in CI that the brand contract is upheld without introducing visual regression tooling?

**Decision**: Three categories of automated check, all running under pytest:

1. **CSS token presence test** — read `styles.css` and assert every required CSS variable from [nymbl-brand.md §4](../../nymbl-brand.md) is defined (`--ink-900`, `--paper-50`, `--signal-500`, `--font-display`, etc.) with the brand-pinned hex / family value.
2. **Forbidden-string test** — assert `styles.css` contains zero matches for `#ffffff`, `#FFFFFF`, `#000000`, `#000`, `rgb(255, 255, 255)`, `rgb(0, 0, 0)`, the literal substring `purple`, and any unconfigured `linear-gradient(... #` containing non-brand hex codes. (Allow gradient declarations whose stops are all brand tokens — the brand guide permits single-hue stone gradients.)
3. **A11y attribute test** — render the base template and each error partial via Jinja2; parse with a lightweight HTML parser; assert `#response` has `aria-live="polite"`, error partials have `role="alert"`, and the upload-progress card has `aria-live="polite"`. Assert no error partial template emits the literal `{{ message }}` or `{{ cause }}` substring (i.e., the categories are baked into the templates, not passed in).

A `tests/unit/test_ui_brand_contract.py` consolidates these. Visual checks (does it actually *look* like Nymbl?) remain on the manual quickstart checklist — automated visual regression is out of scope for a 30-minute-demo deliverable.

**Rationale**: Catches the most likely regressions (a developer adds `#fff` because muscle memory; a template starts passing the raw backend message through) without needing Playwright / Percy / a headless Chrome. Keeps the test suite under one minute.

**Alternatives considered**: *Playwright screenshot tests*: rejected — too much infra for too little ROI on a single-page demo. *No tests, manual only*: rejected — the brand-token and a11y attribute regressions are easy mistakes and the test cost is small.

---

## Summary of decisions feeding Phase 1

- HTMX error handling: global event listeners (`htmx:responseError`, `htmx:sendError`, `htmx:timeout`) in `base.html` swap pre-rendered category templates into `#response`.
- Dark mode: pure `@media (prefers-color-scheme: dark)` CSS, no JS, no FOUC.
- Fonts: Google Fonts (Fraunces variable with `opsz,wght` axes) + jsDelivr/vercel CDN (Geist Sans + Geist Mono), with `display=swap`.
- Loading: opacity-pulse on `.htmx-indicator` using `--signal-600` text; reduced-motion → static.
- Replace-confirm: inline JS reads `.current-doc-card` presence; native `confirm()` on positive case.
- Status-card rebrand: success / ember / info / danger / stone, signal-only on active states.
- Contracts tested: CSS token presence, forbidden strings, a11y attributes.

All NEEDS CLARIFICATION items from the Technical Context are resolved.
