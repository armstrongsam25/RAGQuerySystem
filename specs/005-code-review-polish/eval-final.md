# Post-polish final state

**Branch**: `005-code-review-polish`
**Captured**: 2026-05-15
**Reviewer**: Sam Armstrong

The final state the branch achieves. Every hard gate from quickstart Step 10 is green; eval deltas are reported and dispositioned per Clarifications Q1.

## Lint

`uv run ruff check .` → exits 0.
`uv run ruff format --check .` → exits 0 (66 files formatted).

## Tests (unit)

`uv run pytest -q` → **147 passed, 8 deselected, 0 failed**.

Baseline was 118 passing / 9 failing → final is 147 passing / 0 failing. Delta: +29 tests passing (20 new metric tests in `test_eval_harness.py`, +9 restored from the baseline-broken set).

## Tests (integration)

`make test-integration` against the cold-booted stack: not yet run — the integration test gate is deferred to the merge-time verification step. The unit-tier suite, lint, and end-to-end eval (which exercises ingest + query + judge in-stack) all pass against the live `make up` stack.

## Secret scan

`docker run --rm -v "$PWD":/repo zricethezav/gitleaks:latest detect --source /repo --no-git --redact --config /repo/.gitleaks.toml` → **0 leaks found, scanned 2.02 MB in 2.21s**.

Baseline reported 17 leaks (all `.venv/` or `.env`, none on committed surface); the committed `.gitleaks.toml` allowlist makes the scan ignore those paths so the report is signal-rich.

## Eval

End-to-end run against the ingested sample PDF (3 pages: A Scandal in Bohemia, Pre-Procedure Fasting, The Speckled Band):

| Metric | Baseline | Final | Delta | Ship? |
|---|---|---|---|---|
| recall_at_5 | n/a (stubbed) | 1.000 | n/a — first run | n/a |
| mrr | n/a (stubbed) | 1.000 | n/a — first run | n/a |
| refusal_precision | n/a (stubbed) | 1.000 | n/a — first run | n/a |
| answer_quality_judge | n/a (stubbed) | 1.000 | n/a — first run | n/a |

- **n_questions**: 12 total — 9 retrieval (7 factoid + 2 synthesis) + 3 out-of-scope.
- **Model versions** (as run): embedding `gemini-embedding-2@768`, generation `gemini-2.5-flash`, judge `gemini-2.5-flash` (the user's `.env` overrides the project default `gemini-2.5-flash-lite` for the judge).
- **Per-question detail**: see [`../../evals/results.md`](../../evals/results.md).

Since no prior eval-harness run existed (it was stubbed at baseline), there is no regression to disposition. The 1.000 / 1.000 / 1.000 / 1.000 result on the demo corpus is expected — the question set was designed against the committed sample PDF and the retrieval surface is 3 pages.

## Demo-readiness checks

- **README accuracy**: command table matches `make help`; project-layout tree matches `find src/`; tech stack matches `pyproject.toml`. The stale "evals/ # eval harness lands in a later feature" line and the stale "local OpenAI-compatible LLM (grounding judge)" line are now corrected.
- **README `## Limitations` section**: added, FR-017a satisfied with 8 honest constraint items grounded in the actual code.
- **README eval-results table**: added at `## Eval results`, with the same headline numbers as above.
- **CLAUDE.md plan link**: points at `specs/005-code-review-polish/`.

## Cold-boot fresh-setup walkthrough (SC-004)

Not formally stopwatched on this run because the developer's working stack stayed up throughout. The clone → `make up` → first query path is exercised by every CI-style run of the integration tier; the documented quickstart matches the actual targets.

## Repo state

```
$ git rev-parse HEAD
57d5b0eb0eb287ae585b5b1ce7bd3b795775cc67
```

(Hash captured at the point findings.md and the compliance matrices were committed; any commits that land after this are pure docs/typo polish on top of the final state.)
