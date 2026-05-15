# Eval results

**Run timestamp**: 2026-05-15T00:00:53.772240+00:00
**Questions**: 12 total · 9 retrieval · 3 out-of-scope
**Model versions**:
- `embedding`: `gemini-embedding-2@768`
- `generation`: `gemini-2.5-flash`
- `judge`: `gemini-2.5-flash`

## Headline metrics

| Metric | Value | n |
|---|---|---|
| Recall@5 | 1.000 | 9 |
| MRR | 1.000 | 9 |
| Answer quality (judge) | 1.000 | 9 |
| Refusal precision | 1.000 | 3 |

## Per-question detail

| ID | Category | Expected pages | Retrieved (top-5) | Status | Refusal cause |
|---|---|---|---|---|---|
| q-000-example-factoid | factoid | 2 | 2, 3, 3, 1, 1 | answered | — |
| q-000-example-out-of-scope | out_of_scope | — | 1, 2, 3, 3, 3 | refused | judge_no_supporting_spans |
| q-001-factoid-clear-liquids | factoid | 2 | 2, 3, 1, 3, 2 | answered | — |
| q-002-factoid-non-compliance | factoid | 2 | 2, 3, 1, 3, 3 | answered | — |
| q-003-factoid-medications | factoid | 2 | 2, 3, 3, 1, 1 | answered | — |
| q-004-factoid-baker-street | factoid | 3 | 3, 1, 2, 1, 3 | answered | — |
| q-005-synthesis-fasting-summary | synthesis | 2 | 2, 3, 3, 1, 1 | answered | — |
| q-006-synthesis-diabetic-patient | synthesis | 2 | 2, 1, 3, 3, 3 | answered | — |
| q-007-factoid-irene-adler | factoid | 1 | 1, 3, 2, 1, 3 | answered | — |
| q-008-factoid-cases-studied | factoid | 3 | 3, 1, 2, 3, 1 | answered | — |
| q-009-out-of-scope-weather | out_of_scope | — | 1, 2, 3, 3, 2 | refused | judge_no_supporting_spans |
| q-010-out-of-scope-recipe | out_of_scope | — | 2, 3, 1, 3, 1 | refused | judge_no_supporting_spans |
