# `findings.md` — Authoritative Schema

**Branch**: `005-code-review-polish`
**Used by**: the polish pass to produce `specs/005-code-review-polish/findings.md` — a first-class committed deliverable per Article VIII.1 (Clarifications Q4).

The findings document is the **narratable artifact** the developer walks through during the 30-minute demo to demonstrate triage discipline. It MUST be readable in isolation — a Nymbl reviewer SHOULD be able to read `findings.md` without simultaneously having the diff open and still understand what was found, what was fixed, and what was deliberately deferred.

This schema is authoritative. Deviations are themselves a finding.

## Required structure

```markdown
# Code Review Findings — Production Polish Pass

**Branch**: `005-code-review-polish`
**Captured**: <ISO date>
**Reviewer**: <name>
**Total findings**: <N>  (critical: <Nc> · major: <Nm> · minor: <Nn>)

## How to read this document

<one paragraph: severity definitions, disposition meanings, how to cross-reference commits>

## Severity definitions

- **critical** — <verbatim from data-model.md, with concrete examples>
- **major** — <verbatim from data-model.md>
- **minor** — <verbatim from data-model.md>

## Summary table

| ID | Area | Severity | Category | Disposition | Commit / Rationale |
|---|---|---|---|---|---|
| FND-001 | … | … | … | … | … |
| FND-002 | … | … | … | … | … |
| … |

## Findings

### FND-001 — <one-line summary>

- **Area**: <file or module>
- **Severity**: <critical | major | minor>
- **Category**: <correctness | security | style | doc | scope>
- **Description**:
  <one or two sentences describing the issue>
- **Suggested remediation**:
  <what the fix should look like>
- **Disposition**: <fixed | deferred | won't fix>
- **Commit ref** (if fixed): `<short SHA> — <subject line>`
- **Rationale** (if deferred / won't fix): <one or two sentences>

### FND-002 — …

…

## Eval delta summary

(populated after eval-final.md is written)

| Metric | Baseline | Final | Delta | Ship? |
|---|---|---|---|---|
| recall_at_5 | … | … | … | … |
| mrr | … | … | … | … |
| refusal_precision | … | … | … | … |
| answer_quality_judge | … | … | … | … |

## Known unfixed constitutional obligations

(items deliberately deferred outside this branch)

- **Article VIII.5 — Slide deck** — Out of scope per Clarifications Q6. Developer responsibility outside spec-kit.

## Compliance snapshot at merge

(updated final values, copied from contracts/ matrices when polish is complete)

- Nymbl PDF must-haves: <X> / <Y> satisfied
- Constitution articles: <X> / <Y> satisfied (load-bearing: I, II, III, IV, V, VI, VII, VIII)
```

## Required content invariants

1. **Header counts MUST match the summary table.** If the summary table shows 23 rows, `Total findings: 23` MUST appear in the header.
2. **Every finding in the summary table MUST have a corresponding `### FND-NNN` detail section.** No summary-only rows.
3. **Every `critical` finding MUST have a `Disposition: fixed` and a `Commit ref:` line.** This enforces FR-001b at the document level.
4. **Every `deferred` and `won't fix` finding MUST have a non-empty `Rationale:` line.** This enforces FR-003.
5. **The "Eval delta summary" section MUST be present and filled** before merge. Empty cells are not acceptable — fill with measured numbers.
6. **The "Known unfixed constitutional obligations" section MUST include Article VIII.5** at minimum, citing Clarifications Q6.
7. **The summary table SHOULD group rows by severity** (criticals first, then majors, then minors) so a reader scanning top-down sees the highest-impact items first.

## Optional but recommended

- A **"Process notes"** section at the bottom describing the order findings were discovered, any false-positive candidates that were ruled out (e.g., a vulture hit on a CLI entrypoint that was reachable dynamically), and any tooling output (gitleaks summary, mypy strict count) that informed the review.
- A **"What I would do next"** section if the developer wants to surface ideas that didn't fit in this branch but should land in future features. Items here are NOT findings — they are forward-looking notes for the demo's "next steps" segment.

## What MUST NOT appear in `findings.md`

- Findings about files explicitly out of scope per FR-010c (prior specs, `.specify/templates/`, `.venv/`, constitution file unless touched via its own governance). If a finding is logically against frozen content, it belongs in a future feature spec, not here.
- Speculative defects without evidence ("might be broken if...") — every finding MUST cite a concrete file/line or quoted snippet.
- Praise notes — `findings.md` is a defect log. Positive observations go in the demo deck (which is out of scope here) or the README.
