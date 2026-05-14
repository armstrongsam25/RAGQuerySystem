# Feature Specification: Nymbl UI Polish & UX Fixes

**Feature Branch**: `004-nymbl-ui-polish`
**Created**: 2026-05-13
**Status**: Draft
**Input**: User description: "implement the fixes and polish for this demo app based on the review document found here: @ui_ux_review.md . Also use the Nymbl design (colors and typography) when applying the polish to this Small RAG system (see @Nymbl-design.png) and @nymbl-brand.md."

## Clarifications

### Session 2026-05-13

- Q: When the backend fails, what should error messages contain (raw backend text vs. generic categories)? → A: Generic category only — show "Server error", "Network error", or "Invalid input" with a retry affordance. Never display backend response text or status codes in the UI.
- Q: What visual style should the query loading indicator take? → A: Pulsing text — single line of Geist Sans on a slow opacity pulse using the signal accent. Static line when `prefers-reduced-motion: reduce`. No spinner, no skeleton loader.
- Q: How should assistive technology be notified when the response region updates or an error appears? → A: The response/upload region is `aria-live="polite"` so answers are announced without interrupting; error inserts additionally carry `role="alert"` so failures preempt other speech.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Visible failure feedback during query and upload (Priority: P1)

When a backend call fails (timeout, 5xx, network drop, validation rejection), the user must immediately see a clear, human-readable error message and be able to retry. Today the loading indicator hangs forever and the submit button stays disabled, leaving the app looking frozen.

**Why this priority**: This is the only flaw in [ui_ux_review.md](../../ui_ux_review.md) tagged "Critical Workflow Flaw." Without it, a single backend hiccup makes the entire demo appear broken — a fatal first impression for the tech assessment reviewer. Every other polish item is moot if the app silently dies under load.

**Independent Test**: Force the query endpoint to return a 503 (or kill the API server mid-query). Submit a question. Within ~2 seconds the user should see an inline error banner explaining what went wrong, the loading indicator should clear, and the submit button should re-enable so they can retry.

**Acceptance Scenarios**:

1. **Given** the query API returns 503, **When** the user submits a question, **Then** the loading indicator clears within 2 seconds and an inline error message appears in the response region explaining the request failed and inviting retry.
2. **Given** the upload API returns an error mid-ingest, **When** the user is watching the progress indicator, **Then** the indicator stops, an inline error replaces it, and the upload form re-enables.
3. **Given** an error has been displayed, **When** the user submits a new query, **Then** the error clears and the normal flow resumes.
4. **Given** the network is offline, **When** the user submits a query, **Then** a network-specific error message appears within 5 seconds rather than the indicator hanging indefinitely.

---

### User Story 2 - Apply Nymbl visual identity (Priority: P1)

The demo currently uses generic flat styling with cool grays and a system sans-serif. It must be restyled to reflect the Nymbl brand: warm paper neutrals as surface, ink as primary text, the chartreuse signal color as a scalpel-applied accent on the single primary action, Fraunces serif for display/headings, Geist Sans for body/UI, and Geist Mono for code and citations. The 60/30/10 paper / stone / signal+ember balance from the brand guide governs every surface.

**Why this priority**: The user explicitly asked for the Nymbl design to be applied, and this is the second of two co-equal "must land" goals for the assessment delivery. A reviewer comparing the demo against the Nymbl marketing site should recognize the same visual language at a glance.

**Independent Test**: Open the app in a browser with the brand reference open beside it. Confirm: warm off-white background (not cool gray), serif headings with proper optical sizing, sans-serif body, exactly one chartreuse primary action per view, no purple, no pure white surfaces, no pure black text.

**Acceptance Scenarios**:

1. **Given** a fresh page load, **When** the user views any screen, **Then** the background is warm paper (not pure white or cool gray) and body text is ink-dark (not pure black) — both drawn from the brand color tokens.
2. **Given** the page renders, **When** a reviewer inspects typography, **Then** all display/heading text uses Fraunces (serif), all body and form text uses Geist Sans, and any code/citation/data uses Geist Mono.
3. **Given** the user looks at any single screen, **When** they identify accent color usage, **Then** the chartreuse signal color appears on at most one primary action per view (the Ask button or the Upload button, not both simultaneously highlighted) and is never used as a large fill.
4. **Given** display headings render, **When** measured against the brand type scale, **Then** they use the size/weight/optical-size combinations from the brand guide's type scale table.
5. **Given** the UI renders end-to-end, **When** scanning for forbidden patterns, **Then** there are zero purple gradients, zero `#FFFFFF` surfaces, zero `#000000` text fills, and the signal color is paired only with ink (never with paper).

---

### User Story 3 - Dark mode that respects system preference (Priority: P2)

The app should automatically switch to a dark theme when the user's OS reports a dark-mode preference, using the brand's defined dark palette (ink-900 as surface, paper-50 as foreground, ink-700 for elevated surfaces). Light mode remains the default for users with no preference set.

**Why this priority**: Modern web apps are expected to honor `prefers-color-scheme`. The brand guide already specifies the exact dark-mode token mapping, so this is a high-polish, low-risk addition that meaningfully improves the demo for reviewers who use dark OS themes.

**Independent Test**: With OS appearance set to dark, load the app — the page should render dark immediately on first paint with no flash of light content. Switch OS appearance to light and reload — the page should render light.

**Acceptance Scenarios**:

1. **Given** the OS appearance is set to dark, **When** the user loads the app, **Then** the page renders with ink-dark surfaces and paper-light text on first paint.
2. **Given** the OS appearance is set to light, **When** the user loads the app, **Then** the page renders the existing warm-paper light theme.
3. **Given** either mode, **When** the chartreuse signal accent appears, **Then** it remains chartreuse and paired with ink in both light and dark themes (signal does not invert).
4. **Given** dark mode is active, **When** body text and secondary text are inspected, **Then** all foreground/background pairings meet WCAG AA contrast (4.5:1 for body).

---

### User Story 4 - Polished loading indicator for queries (Priority: P2)

The query "Thinking…" italic text feels rudimentary compared to the upload phase's staged progress indicator. Replace it with a subtle, branded loading state (e.g., an animated pulse or spinner using brand colors) so the query phase feels equally crafted.

**Why this priority**: This is a visible polish gap directly between two adjacent user actions (upload vs. ask). It is purely additive and small, but it closes a noticeable inconsistency that a reviewer will spot on first run-through.

**Independent Test**: Submit a query that takes >1 second. The loading state should be a visually polished, branded animation rather than static italic text, and it should disappear cleanly when the response arrives.

**Acceptance Scenarios**:

1. **Given** a query is in flight, **When** the loading state is visible, **Then** it shows a branded animated indicator (not static italicized text).
2. **Given** the response arrives, **When** the indicator unmounts, **Then** there is no visible flicker, jump, or layout shift.
3. **Given** the indicator is animating, **When** observed for 10 seconds, **Then** the animation is smooth (no jank) and uses brand tokens for color.

---

### User Story 5 - Confirmation before replacing the ingested document (Priority: P3)

The current upload form silently replaces the ingested document the moment the user picks a file. Add a confirmation step so a user cannot accidentally destroy their indexed corpus by misclicking the file picker.

**Why this priority**: The README documents the replace-on-upload behavior intentionally, so this is not a correctness bug — it is a defensive-UX nicety. Lowest priority of the polish items; only matters once an ingested document is already present.

**Independent Test**: Upload a document. Then click upload again and pick a second file. A confirmation should appear before the replace happens; cancelling preserves the existing document.

**Acceptance Scenarios**:

1. **Given** no document is currently ingested, **When** the user selects a file, **Then** upload proceeds without a confirmation prompt.
2. **Given** a document is already ingested, **When** the user selects a replacement file, **Then** the user is prompted to confirm replacement before the upload starts.
3. **Given** the confirmation appears, **When** the user cancels, **Then** the existing document remains and no upload request is sent.

---

### Edge Cases

- The user submits a query while a prior query's error message is still visible — the new submission must clear the prior error.
- An error happens during ingestion *after* progress has advanced past 0% — the staged progress must stop where it is and the error must replace it inline, not stack underneath.
- A user with `prefers-color-scheme: dark` loads the page on a slow connection — the dark surfaces must apply on first paint without a flash of light content.
- A user with no `prefers-color-scheme` preference defaults to the light (paper) theme.
- The user's browser blocks the Google-hosted brand fonts — body and headings must fall back gracefully to the local serif and sans-serif fallback stacks defined in the brand guide.
- A query produces a response so long that scrolling is needed — the response area scrolls without breaking the surrounding layout or hiding the input.
- A reviewer with reduced-motion preference (`prefers-reduced-motion: reduce`) — animations must respect that setting and degrade to static states.

## Requirements *(mandatory)*

### Functional Requirements

**Error feedback (US1):**
- **FR-001**: System MUST display a user-visible error message in the response/upload region whenever a backend call fails with a non-2xx status, a network error, or a timeout exceeding 60 seconds.
- **FR-002**: System MUST clear any visible loading indicator and re-enable the relevant submit control within 2 seconds of an error occurring.
- **FR-003**: System MUST automatically clear a displayed error when the user initiates a new request of the same type.
- **FR-004**: Error messages MUST distinguish between server errors, validation errors, and network errors using fixed, generic category copy (e.g., "Server error", "Invalid input", "Network error") plus a retry affordance — the UI MUST NOT surface raw backend response bodies, `detail` fields, or HTTP status codes.

**Nymbl visual identity (US2):**
- **FR-005**: System MUST use Fraunces as the display/heading typeface, Geist Sans as the body/UI typeface, and Geist Mono for code/citation/data — with the fallback stacks defined in [nymbl-brand.md](../../nymbl-brand.md) §3.1.
- **FR-006**: System MUST use the brand color tokens (paper, ink, stone, signal, ember, and semantic colors) as defined in [nymbl-brand.md](../../nymbl-brand.md) §2.1–§2.3 — no `#FFFFFF` surfaces, no `#000000` text fills, no cool grays.
- **FR-007**: System MUST limit the signal (chartreuse) accent to one primary action per view and MUST NOT use it as a large fill or pair it with paper foreground.
- **FR-008**: System MUST apply the brand type scale from [nymbl-brand.md](../../nymbl-brand.md) §3.3 to display, heading, body, and caption text — including correct optical-size (`opsz`) settings on Fraunces.
- **FR-009**: System MUST follow the brand tracking and feature rules from §3.4 — tight negative tracking at display sizes, tabular numerals for any numeric data (e.g., similarity scores in citations).
- **FR-010**: System MUST NOT introduce purple gradients, gradients across multiple hues, or any third typeface beyond the two brand families plus mono.

**Dark mode (US3):**
- **FR-011**: System MUST switch to the brand's dark color tokens automatically when the user's OS reports `prefers-color-scheme: dark`.
- **FR-012**: System MUST render the correct theme on first paint without a flash of opposite-theme content.
- **FR-013**: System MUST keep the signal accent chartreuse in both light and dark themes (the accent does not invert).
- **FR-014**: System MUST maintain WCAG AA contrast (4.5:1 for body text, 3:1 for large text) in both themes.

**Loading polish (US4):**
- **FR-015**: System MUST present the query loading state as a single line of Geist Sans body text on a slow opacity pulse using the signal accent — no spinner glyph, no skeleton loader, no italic styling.
- **FR-016**: System MUST honor `prefers-reduced-motion: reduce` by rendering the same loading line statically (no opacity animation).

**Replace-document confirmation (US5):**
- **FR-017**: System MUST prompt the user to confirm replacement before uploading a new file when a previously ingested document is present.
- **FR-018**: System MUST allow the user to cancel the replacement, leaving the existing ingested document untouched.

**Accessibility (cross-cutting):**
- **FR-019**: The query response region and the upload status region MUST each be marked as `aria-live="polite"` so successful answers and progress updates are announced to assistive technology without interrupting current speech.
- **FR-020**: Error messages inserted into either region MUST additionally carry `role="alert"` so failures preempt other speech and are surfaced promptly to screen reader users.

### Key Entities

- **Error message**: A short, user-facing description of what went wrong (server / network / validation), a suggested next action (retry / refresh / check connectivity), and an inline display location anchored to the affected control (query response area or upload region).
- **Theme**: A coherent set of color tokens (background, foreground, muted, border, accent, accent-foreground) drawn from the brand palette, switched by OS preference.
- **Loading state**: A visual indicator (animated for users without reduced-motion, static for users with it) that occupies the response region for the duration of a pending backend call.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When the backend returns an error for any user-initiated request, 100% of those errors produce a visible inline message within 2 seconds, and the relevant submit control re-enables within the same 2 seconds.
- **SC-002**: A user can recover from an error and submit a successful follow-up request without reloading the page in 100% of error-then-retry sequences.
- **SC-003**: A first-time reviewer can correctly identify the Nymbl brand attributes (warm paper background, serif headings, chartreuse single-accent) within 5 seconds of opening the app, without being prompted.
- **SC-004**: All text/background pairings in both light and dark themes meet WCAG AA contrast (4.5:1 body, 3:1 large text), verified by an automated contrast check.
- **SC-005**: The page renders the correct theme on first paint in 100% of loads, with zero perceptible flash of opposite-theme content (>16ms flash = fail).
- **SC-006**: Every query loading state shows a branded animated indicator for users without reduced-motion preference, and a clean static indicator for users with it — 100% of the time.
- **SC-007**: Zero accidental document replacements: a user clicking the upload control while a document is already ingested encounters a confirmation step in 100% of attempts.
- **SC-008**: Visual audit produces zero instances of forbidden patterns: no `#FFFFFF`/`#000000` raw values in rendered styles, no purple gradients, no third typeface, no large signal-color fills.

## Assumptions

- Implementation will live inside the existing FastAPI + HTMX + Jinja templates app at [src/rag/ui/](../../src/rag/ui/); no rewrite to a JavaScript framework is in scope.
- The two brand fonts (Fraunces, Geist Sans, Geist Mono) will be loaded from their canonical free hosts (Google Fonts / vercel.com/font) — no offline/self-hosted variant is required for the assessment.
- Error messages are presented in English only; localization is out of scope.
- Dark mode follows OS preference automatically — a manual in-app theme toggle is out of scope for this feature.
- The replace-document confirmation uses a native browser confirm dialog (consistent with the existing "Clear document" affordance); a custom modal component is not required.
- The existing query and ingest backend APIs are unchanged by this feature — all changes are presentation-layer only.
- WCAG AA contrast is the target; AAA is not required for this demo.
- The reviewer audience is technical and uses a modern evergreen browser (recent Chrome, Edge, Firefox, or Safari); IE11 and legacy mobile are out of scope.
