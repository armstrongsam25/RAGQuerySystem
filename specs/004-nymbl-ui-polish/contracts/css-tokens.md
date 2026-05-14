# Contract: CSS Token Surface

`src/rag/ui/static/styles.css` MUST define the following CSS custom properties at the `:root` selector. Values are pinned by the brand guide; the contract test reads the file and matches against this table.

## Color — core

| Property | Value | Source |
|---|---|---|
| `--ink-900` | `#0A0A0F` | [nymbl-brand.md §2.1](../../../nymbl-brand.md) |
| `--ink-700` | `#1F2028` | §2.1 |
| `--paper-50` | `#F5F1E8` | §2.1 |
| `--paper-100` | `#EDE7D9` | §2.1 |
| `--signal-500` | `#DAFE5D` | §2.1 |
| `--signal-600` | `#B8DE3A` | §2.1 |
| `--ember-500` | `#E85A4F` | §2.1 |

## Color — stone

| Property | Value |
|---|---|
| `--stone-50` | `#F0ECE3` |
| `--stone-100` | `#E2DCCE` |
| `--stone-200` | `#CAC2B0` |
| `--stone-300` | `#A39B89` |
| `--stone-500` | `#6E6757` |
| `--stone-700` | `#403B30` |

## Color — semantic

| Property | Value |
|---|---|
| `--success` | `#3F8F5C` |
| `--warning` | `#D89A2E` |
| `--danger` | `#C7372F` |
| `--info` | `#4A6FA5` |

## Typography

| Property | Value |
|---|---|
| `--font-display` | `"Fraunces", "Iowan Old Style", Georgia, serif` |
| `--font-sans` | `"Geist", ui-sans-serif, system-ui, sans-serif` |
| `--font-mono` | `"Geist Mono", ui-monospace, "SF Mono", monospace` |

## Type scale (size / line-height pairs)

Format: `clamp(min, ideal, max)` is permitted for fluid sizing but the default declaration must use the brand-pinned exact values from §3.3 first, with optional `clamp()` overrides downstream:

| Property | Size / line-height | Family | Weight |
|---|---|---|---|
| `--text-display-2xl` | 76px / 80px | display | 400, opsz 144 |
| `--text-display-xl` | 60px / 64px | display | 400, opsz 96 |
| `--text-display-lg` | 48px / 52px | display | 400, opsz 72 |
| `--text-heading-xl` | 36px / 42px | display | 500, opsz 48 |
| `--text-heading-lg` | 28px / 34px | display | 500, opsz 36 |
| `--text-heading-md` | 22px / 28px | display | 500, opsz 24 |
| `--text-heading-sm` | 18px / 26px | sans | 600 |
| `--text-body-lg` | 18px / 28px | sans | 400 |
| `--text-body-md` | 16px / 24px | sans | 400 |
| `--text-body-sm` | 14px / 20px | sans | 400 |
| `--text-caption` | 12px / 16px | sans | 500 |
| `--text-mono-md` | 14px / 22px | mono | 400 |
| `--text-mono-sm` | 12px / 18px | mono | 400 |

## Surface aliases

| Property | Light value | Dark value (inside `@media (prefers-color-scheme: dark)`) |
|---|---|---|
| `--bg` | `var(--paper-50)` | `var(--ink-900)` |
| `--fg` | `var(--ink-900)` | `var(--paper-50)` |
| `--fg-muted` | `var(--stone-500)` | `var(--stone-300)` |
| `--border` | `var(--stone-100)` | `var(--ink-700)` |
| `--accent` | `var(--signal-500)` | `var(--signal-500)` |
| `--accent-fg` | `var(--ink-900)` | `var(--ink-900)` |

## Motion

| Property | Value |
|---|---|
| `--motion-pulse-duration` | `1.5s` |

## Forbidden values

The stylesheet MUST NOT contain any of the following raw values (matched case-insensitively except where noted):

- `#ffffff`, `#FFFFFF`, `#fff` (whole-token), `#FFF`
- `#000000`, `#000` (whole-token), `#000`
- `rgb(255, 255, 255)`, `rgb(0, 0, 0)`
- The literal string `purple` (case-insensitive) — covers both color names and gradient direction comments alike. (No false positives because no other Nymbl token has "purple" in its name.)
- Any `linear-gradient(...)` whose hex stops do not all resolve to brand-token-pinned values.

The contract test enforces all of the above with a single ripgrep-style scan.
