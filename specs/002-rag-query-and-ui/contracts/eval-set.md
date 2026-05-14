# Eval Set Contract — `evals/questions.jsonl`

This contract pins the shape of the eval set so feature 003 (the eval harness) can be implemented without renegotiating the schema. Feature 002 scaffolds `evals/questions.jsonl` with one or two illustrative entries; feature 003 owns the ≥10 hand-curated entries constitution Art III.1 mandates.

## Format

One JSON object per line. UTF-8. No surrounding array. Blank lines and lines starting with `//` MUST be tolerated by readers — comment lines are convenient for grouping during authoring.

## Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | yes | Stable identifier, e.g. `q-001`. Used to correlate eval-output rows back to the source set. |
| `question` | string | yes | The natural-language question, exactly as it would be sent to `POST /query`. |
| `expected_answer` | string \| null | yes | Free-text reference answer for in-scope questions. `null` when the question is intentionally out-of-scope (the correct system outcome is refusal). |
| `expected_pages` | integer[] | yes | Page numbers (1-indexed, matching PDF page numbering) where supporting evidence lives. Empty list (`[]`) when `expected_answer` is null. |
| `category` | enum | yes | One of: `factoid`, `synthesis`, `out_of_scope`. Matches constitution Art III.1's three required categories. |
| `notes` | string \| null | no | Free-text authoring notes (e.g., "tests numbered-list extraction across page break"). Surfaced in eval-failure diagnostics; not used by the harness for scoring. |

## Validation rules

- `id` MUST be unique across the file.
- `category=out_of_scope` ⇒ `expected_answer=null` AND `expected_pages=[]`.
- `category` ∈ {`factoid`, `synthesis`} ⇒ `expected_answer != null` AND `len(expected_pages) >= 1`.
- `expected_pages` values MUST be positive integers (page numbers are 1-indexed; matches the `chunk.page_number CHECK > 0` constraint).
- `question` MUST be non-empty and MUST NOT exceed the API's question length cap (1000 chars per the OpenAPI contract).

A reader that encounters an invalid line MUST log the line number and the violation, then continue — the harness is expected to score what it can and surface invalid entries separately.

## Example entries (illustrative; not the real eval set)

```jsonl
// Single-chunk factoid
{"id":"q-001","question":"How long must patients fast before the procedure?","expected_answer":"At least 8 hours.","expected_pages":[12],"category":"factoid","notes":null}

// Multi-chunk synthesis
{"id":"q-002","question":"What conditions disqualify a patient from same-day discharge?","expected_answer":"Uncontrolled hypertension, recent MI within 6 months, or unstable airway.","expected_pages":[14,17,18],"category":"synthesis","notes":"requires combining the discharge criteria table on p14 with the contraindications list on p17-18"}

// Intentionally out-of-scope — system MUST refuse
{"id":"q-003","question":"What is the boiling point of water at sea level?","expected_answer":null,"expected_pages":[],"category":"out_of_scope","notes":null}
```

## Why JSONL, not JSON-array

- Streamable. A partially-written file is still parseable line-by-line, so failures during authoring tools don't corrupt the whole set.
- `git diff` reads cleanly on insertion of a new question — single-line additions, no array-comma juggling.
- The eval harness can short-circuit on the first failure without holding the rest of the file in memory.

## What feature 003 will read this schema to do

- Drive a regression harness that runs each `question` through the real query path (shared with `rag query`).
- Score retrieval against `expected_pages` using **Recall@k** and **MRR** per constitution Art III.2.
- Score `expected_answer != null` rows for answer quality via the same LLM-as-judge that runs in production (Art IV.6-deviation grounding judge), wired separately as a judging task (R-015's `judge` returns `entailed` + supports, which is the same signal eval needs).
- Score `expected_answer == null` rows as "system refused → pass" / "system answered → fail."
- Persist results into a check-in-able report committed under `evals/results/` for the README to point at (Art III.4 — README must display current eval numbers).

None of those are implemented in this feature; they are the feature-003 surface. This document exists so when feature 003 is specified the schema discussion is over before it starts.
