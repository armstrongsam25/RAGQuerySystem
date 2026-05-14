# Contract: Typography

Implements FR-005, FR-008, FR-009, and FR-010 against [nymbl-brand.md §3](../../../nymbl-brand.md).

## Font loading

[base.html](../../../src/rag/ui/templates/base.html) `<head>` MUST contain, in order:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300..700&display=swap">
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/geist@1.3.1/dist/geist.css">
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/geist@1.3.1/dist/geist-mono.css">
```

- Fraunces is loaded with the `opsz` and `wght` variable axes so per-size optical sizing works.
- Geist Sans and Geist Mono are loaded from the jsDelivr-hosted `geist` npm package — Vercel's recommended CDN distribution.
- All three families use `font-display: swap` (the default in Google Fonts' `display=swap` query param and the default in the Geist package CSS). This guarantees the fallback stack renders immediately and Fraunces / Geist swap in when ready (FR-005 fallback edge case).
- No `preload` of individual woff2 files — the file count makes preloading wasteful for a demo.

The stylesheet MUST reference fonts through the `--font-display`, `--font-sans`, and `--font-mono` custom properties only; no raw `font-family: "Fraunces", ...` declarations elsewhere.

## Per-element typography mapping

| Element / selector | Family | Size | Weight | Other |
|---|---|---|---|---|
| `body` | sans | `--text-body-md` (16/24) | 400 | letter-spacing 0 |
| `header h1` | display | `--text-heading-lg` (28/34) | 500 | opsz 36, letter-spacing −0.02em |
| `.subtitle` | sans | `--text-body-md` | 400 | color `--fg-muted` |
| `.input-group textarea` | sans | `--text-body-md` | 400 | — |
| `.btn-ask` | sans | `--text-body-md` | 600 | letter-spacing 0 |
| `.paperclip-btn` (icon only) | (svg) | n/a | n/a | — |
| `.btn-clear` | sans | `--text-body-sm` (14/20) | 600 | letter-spacing +0.04em |
| `.badge` | sans | `--text-caption` (12/16) | 500 | letter-spacing +0.04em, text-transform: uppercase (eyebrow style per §3.5) |
| `.answer` | sans | `--text-body-lg` (18/28) | 400 | max-inline-size 68ch (§3.5) |
| `h3` (citations heading) | sans | `--text-caption` | 500 | uppercase, letter-spacing +0.04em — eyebrow treatment |
| `.citation blockquote` | sans | `--text-body-md` | 400 | italic OFF (the brand replaces decorative italic with stone-toned color); color `--fg-muted` |
| `.page-badge` | mono | `--text-mono-sm` (12/18) | 400 | font-feature-settings: "tnum" (tabular-nums), "ss01", "zero", "cv11" |
| `.chunk-id` | mono | `--text-mono-sm` | 400 | same mono features as page-badge; color `--fg-muted` |
| `.current-doc-label` | sans | `--text-caption` | 500 | uppercase, letter-spacing +0.04em — eyebrow |
| `.current-doc-name` | sans | `--text-body-md` | 600 | color `--fg`; underline on hover only |
| `.current-doc-meta` | mono | `--text-mono-sm` | 400 | tabular-nums |
| `.upload-progress-filename` | mono | `--text-mono-sm` | 400 | tabular-nums |
| `.upload-progress-stage-label` | sans | `--text-caption` | 600 | uppercase, letter-spacing +0.04em — eyebrow |
| `.upload-progress-message` | sans | `--text-body-md` | 400 | — |
| `.htmx-indicator` (pulse) | sans | `--text-body-lg` | 500 | color `--signal-600` in light, `--signal-500` in dark |
| `footer small` | sans | `--text-body-sm` | 400 | color `--fg-muted` |

## Hierarchy rules (brand guide §3.5)

- One display-tier element per view. The `header h1` is the display-tier element; nothing else on the page may use `--text-display-*` or `--text-heading-xl`.
- Heading + eyebrow pattern: where used (e.g., the "Citations" heading), the eyebrow is the caption-style uppercase label and the heading sits directly below — no horizontal rule between them.
- Body line length: any prose container (`.answer`, `.refusal-message`, success/error body copy) MUST have `max-inline-size: 68ch` applied.

## Feature flags (brand guide §3.4)

- Mono containers (`.page-badge`, `.chunk-id`, `.current-doc-meta`, `.upload-progress-filename`) MUST declare:
  ```css
  font-feature-settings: "ss01", "zero", "cv11";
  font-variant-numeric: tabular-nums;
  ```
- All quantitative text in the UI (page numbers, chunk counts, page counts, byte sizes if shown, elapsed seconds) MUST sit inside a mono-styled element so tabular-nums applies. The Geist Sans body retains proportional figures.

## Forbidden patterns

The stylesheet MUST NOT contain:
- Any `font-family` declaration that does not reference `var(--font-display)`, `var(--font-sans)`, or `var(--font-mono)`.
- Any `font-style: italic` (the brand replaces italic emphasis with color/weight per §3.4 implication; the existing `.htmx-indicator` italic and `blockquote` italic are explicit removals).
- Any third typeface beyond the two families plus mono (§5 don't list).
