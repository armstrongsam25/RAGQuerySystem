# Phase 1 Data Model: Production-Polish Code Review Pass

**Branch**: `005-code-review-polish` | **Date**: 2026-05-14
**Companion plan**: [plan.md](plan.md) | **Companion research**: [research.md](research.md)

This document defines the entities the polish-pass deliverables manipulate. None of these become database tables — they are the row shapes of markdown / JSONL artifacts the pass produces and consumes.

---

## Entity: Finding

A single issue surfaced by the code review. Each finding becomes one row (or one bullet block) in `findings.md`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string `FND-NNN` | yes | Zero-padded, sequential, assigned at the time the finding is written. Never reused. |
| `area` | string | yes | File path (`src/rag/query/pipeline.py`) or module/directory (`src/rag/ui/`) the finding applies to. For cross-file findings (e.g., README claim vs. Makefile target), list all relevant paths separated by ` ; `. |
| `severity` | enum: `critical` / `major` / `minor` | yes | Defined in the findings document itself per FR-001a (see also: examples below). |
| `category` | enum: `correctness` / `security` / `style` / `doc` / `scope` | yes | One category per finding. If a finding spans multiple categories, split it into two findings. |
| `description` | string (markdown allowed) | yes | What the issue is, in one or two sentences. Specific enough that someone unfamiliar with the codebase can locate the problem. |
| `suggested_remediation` | string (markdown allowed) | yes | What the fix should look like, even if not adopted. |
| `disposition` | enum: `fixed` / `deferred` / `won't fix` | yes | Critical findings MUST be `fixed` (FR-001b). Major/minor may be any. |
| `rationale` | string (markdown allowed) | conditional | Required when disposition is `deferred` or `won't fix`. Article VII reference, explicit constraint, or judgment call (FR-003). |
| `commit_ref` | string (short SHA or commit subject) | conditional | Required when disposition is `fixed` (FR-002). |

### Severity definitions (rendered verbatim in findings.md per FR-001a)

- **critical** — a defect that, if shipped, materially damages the hiring signal or violates a load-bearing constitution article. Examples: a committed secret, a broken refusal path, a lint failure, a failing test, a missing eval harness (Article III), a citation missing required provenance fields (Article II), a Dockerfile that doesn't build on a fresh clone.
- **major** — a defect that a senior reviewer would notice and form a negative impression from, but which doesn't itself break the demo. Examples: a public function missing a type hint, an exception handler with a weak error message, README drift on a `make` target name, dead but harmless code in a hot module, an overlong docstring describing what well-named code already says.
- **minor** — a polish item that improves the reading impression but is low-cost to defer. Examples: a naming inconsistency between two helpers, a comment that could be sharper, a slightly long line that ruff allowed.

### Validation rules

- `id` MUST match `^FND-\d{3}$` and MUST be unique within the document.
- When `disposition = fixed`, `commit_ref` MUST be non-empty AND `rationale` MAY be omitted.
- When `disposition ∈ {deferred, won't fix}`, `rationale` MUST be non-empty AND `commit_ref` MAY be omitted.
- `severity = critical` AND `disposition ≠ fixed` is a constraint violation (FR-001b). The findings document MUST NOT contain such a row at merge time.
- The findings document MUST contain at least one row each in the `correctness`, `style`, and `doc` categories (otherwise the review wasn't comprehensive enough — a sanity check, not a strict gate).

### State transitions

```text
                  draft (added during review)
                       │
            ┌──────────┼──────────────┐
            ▼          ▼              ▼
          fixed     deferred      won't fix
            │          │              │
            └──────────┴──────────────┴── (terminal at merge)
```

A finding can be re-classified (e.g., escalated from `major` to `critical` after seeing the eval impact) while in `draft`. After a disposition is set and committed it MAY be revised only by an explicit, narrated update — not silent edit.

---

## Entity: EvalResult

A single number from one eval run. Rows live in `evals/results.jsonl` (machine-readable) and are aggregated into `evals/results.md` (the table referenced from the README per FR-014). The pre-polish and post-polish snapshots live in `eval-baseline.md` and `eval-final.md` respectively, in this feature directory.

| Field | Type | Required | Notes |
|---|---|---|---|
| `metric` | enum: `recall_at_5` / `mrr` / `refusal_precision` / `answer_quality_judge` | yes | One row per metric per run. |
| `value` | float | yes | 0.0–1.0 for all four metrics. |
| `n_questions` | int | yes | Number of questions contributing to this metric (questions outside the metric's category are excluded). |
| `model_versions` | object | yes | `{embedding: "gemini-embedding-001@768", generation: "gemini-2.5-flash", judge: "gemini-2.5-flash-lite"}` — captures what produced the number. |
| `timestamp` | ISO-8601 | yes | When the run completed. |
| `delta_vs_baseline` | float \| null | conditional | Present in `eval-final.md` only; null in baseline. Positive = improvement, negative = regression. |
| `ship_disposition` | enum: `ship` / `don't ship` \| null | conditional | Filled in `eval-final.md` if `delta_vs_baseline < 0` (a regression). The developer makes an explicit call per Clarifications Q1. |

### Validation rules

- `value` MUST be in `[0.0, 1.0]`.
- `n_questions` MUST be ≥ 1.
- If `delta_vs_baseline < 0` and `metric ∈ {recall_at_5, mrr, refusal_precision}` (deterministic metrics), the regression is suspect and SHOULD trigger investigation before `ship_disposition = ship`.
- `answer_quality_judge` regressions are advisory only — judge variance is a known confound (research Decision 6).

---

## Entity: ComplianceItem

A single row in either `contracts/nymbl-assessment-compliance.md` or `contracts/constitution-compliance.md`. The compliance matrices are the readable proof that the system satisfies both the Nymbl PDF rubric and the project constitution.

| Field | Type | Required | Notes |
|---|---|---|---|
| `requirement_id` | string | yes | `NYM-1`, `NYM-2.1`, `ART-I`, `ART-VI.5`, etc. Source-document anchored. |
| `requirement_text` | string | yes | Verbatim quote from the source document (PDF or constitution). |
| `source` | enum: `Nymbl-PDF` / `Constitution-Art-N` | yes | Where the requirement lives. |
| `evidence` | string (markdown allowed) | yes | Paths plus line ranges where the requirement is implemented (`src/rag/query/pipeline.py:42-87`). If gap, leave empty. |
| `status` | enum: `satisfied` / `partial` / `gap` | yes | At-a-glance status. |
| `notes` | string (markdown allowed) | optional | Caveats, related findings (`see FND-007`), or pointer to the disposition. |

### Validation rules

- `status = gap` MUST be linked to at least one open `Finding` in `findings.md` (otherwise the gap is unowned).
- `evidence` MAY be empty only when `status = gap`.
- Compliance matrices are append-only during the polish pass — rows are never deleted, only updated.

---

## Cross-entity relationships

```text
                  Finding ─────────────────────┐
                     │  links via              │
                     │  notes/rationale        │
                     ▼                         │
              ComplianceItem (status=gap)      │
                     │                         │
                     │ source:                 │
                     ▼                         │
           Nymbl-PDF must-have   OR    Constitution Article
                                               │
                                               │
                                               ▼
                                          EvalResult
                                          (Article III)
```

- A `Finding` can be referenced from a `ComplianceItem.notes` (typically when `status = gap` and the gap is tracked as a finding).
- An `EvalResult` is the evidence for `ComplianceItem`s whose source is Article III (the eval discipline article).
- The branch's commit history is the authoritative source for `Finding.commit_ref` and is itself the entity referenced in spec.md's "Polish Changelog" key entity.

---

## Out of scope for this data model

- Per-finding cost or effort estimates — over-engineering for a one-shot pass.
- Reviewer/owner fields — single developer, single branch.
- Priority numerical scoring — severity tier is sufficient.
- Cross-branch tracking of findings — each `/speckit-*` feature has its own findings file if/when it does this style of pass.
