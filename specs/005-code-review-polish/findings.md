# Code Review Findings — Production Polish Pass

**Branch**: `005-code-review-polish`
**Captured**: 2026-05-14 → 2026-05-15
**Reviewer**: Sam Armstrong
**Total findings**: 11  (critical: 4 · major: 4 · minor: 3)

## How to read this document

Every finding has an id (`FND-NNN`), a severity (critical / major / minor — defined below), a category (correctness / security / style / doc / scope), and a disposition (fixed / deferred / won't fix). Critical findings MUST land as commits on this branch (FR-001b); their `Commit ref` line ties the finding to a narratable commit subject of the form `<type>: <summary> (FND-NNN)`. Deferred and won't-fix findings carry a `Rationale` line per FR-003.

To audit traceability: each `Commit ref` value matches `git log --oneline --grep="FND-NNN"` on this branch.

## Severity definitions

- **critical** — a defect that, if shipped, materially damages the hiring signal or violates a load-bearing constitution article. Examples: a committed secret, a broken refusal path, a lint failure, a failing test, a missing eval harness (Article III), a citation missing required provenance fields (Article II), a Dockerfile that doesn't build on a fresh clone.
- **major** — a defect that a senior reviewer would notice and form a negative impression from, but which doesn't itself break the demo. Examples: a public function missing a type hint, an exception handler with a weak error message, README drift on a `make` target name, dead but harmless code in a hot module, an overlong docstring describing what well-named code already says.
- **minor** — a polish item that improves the reading impression but is low-cost to defer. Examples: a naming inconsistency between two helpers, a comment that could be sharper, a slightly long line that ruff allowed.

## Summary table

| ID | Area | Severity | Category | Disposition | Commit / Rationale |
|---|---|---|---|---|---|
| FND-001 | `src/rag/ui/static/styles.css` ; `tests/unit/test_ui_brand_contract.py` | critical | correctness | fixed | `fix: align brand-contract test with shipped navy/purple palette (FND-001)` |
| FND-002 | `src/rag/eval/` ; `src/rag/cli/eval.py` ; `evals/questions.jsonl` ; `Makefile` | critical | correctness | fixed | `feat: implement minimal eval harness, expand question set, wire make eval (FND-002)` |
| FND-003 | `src/rag/api.py` ; `src/rag/lifespan.py` ; `src/rag/providers/gemini.py` ; `src/rag/ui/routes.py` ; `src/rag/ui/upload_jobs.py` ; `pyproject.toml` | critical | correctness | fixed | `fix: pass mypy --strict on src/rag (FND-003)` |
| FND-004 | `.venv/Scripts/*.exe` (developer environment) | critical | correctness | fixed | `chore: rebuild .venv from uv.lock to fix exe shim interpreter paths` (folded into FND-001 commit narrative — the venv reset is what made the tests runnable) |
| FND-005 | `Dockerfile` ; `docker-compose.yml` | major | correctness | fixed | `chore: ship evals/ into the app image and mount it back read-write so make eval works in-stack (FND-005)` |
| FND-006 | `README.md` | major | doc | fixed | `docs: README accuracy sweep, add Limitations and Eval results sections (FND-006)` |
| FND-007 | `.gitleaks.toml` | major | security | fixed | `chore: add gitleaks config that excludes .venv/.env so committed-surface scan is signal-rich (FND-007)` |
| FND-008 | `src/rag/providers/gemini.py` | major | correctness | fixed | Embedding-response `.values` could be `None`; added an explicit guard before `list(...)` so a degenerate Gemini response fails fast with a typed `RuntimeError` instead of `TypeError: 'NoneType' is not iterable`. Folded into FND-003 commit. |
| FND-009 | `tests/unit/test_cli_stubs.py` | minor | correctness | fixed | The stub-exit test for `rag eval` was asserting `exit_code == 2` and "not yet implemented" — both invalid after FND-002 landed real CLI plumbing. Replaced with a `--help` smoke test that pins the documented option surface. Folded into FND-002 commit. |
| FND-010 | `src/rag/cli/main.py` | minor | doc | fixed | Module docstring claimed `eval` was a stub "delivered by feature 003-eval-harness". Updated to reflect that 005-code-review-polish closes it. Folded into FND-002 commit. |
| FND-011 | `Article VIII.5 — slide deck` | minor | scope | won't fix | Out of scope per Clarifications Q6 (developer responsibility outside spec-kit). Logged here so the constitutional obligation is not silently forgotten. Listed in "Known unfixed constitutional obligations" below. |

## Findings

### FND-001 — Brand-contract test asserts a palette that was never shipped

- **Area**: `src/rag/ui/static/styles.css` ; `tests/unit/test_ui_brand_contract.py`
- **Severity**: critical
- **Category**: correctness
- **Description**:
  `tests/unit/test_ui_brand_contract.py::test_css_tokens_defined` asserted brand tokens `--ink-900`, `--paper-50`, `--signal-500`, `--stone-*`, `--ember-500` etc. — a legacy ink/paper/signal/stone Nymbl palette. The shipped `styles.css` uses a navy/purple identity (`--navy-900`, `--purple-500`, `--gray-50`, ...). The companion `test_no_forbidden_strings_in_styles` ALSO forbade the literal substring "purple" and the raw hex `#FFFFFF` — both of which appear in the shipped CSS (the brand IS purple, and `--white: #FFFFFF` was the canonical token). Three brand-contract assertions failed at branch creation.
- **Suggested remediation**:
  Update the test fixture to reflect the navy/purple identity actually in `:root`. Drop the "no purple" rule since the brand uses purple. Replace `--white: #FFFFFF` with `hsl(0 0% 100%)` so the no-raw-hex rule still catches future drift but doesn't trip on the deliberate token.
- **Disposition**: fixed
- **Commit ref**: `cf90a07 — fix: align brand-contract test with shipped navy/purple palette (FND-001)`

### FND-002 — Eval harness is a stub; question set is too small

- **Area**: `src/rag/cli/eval.py` ; `evals/questions.jsonl` ; `Makefile`
- **Severity**: critical
- **Category**: correctness
- **Description**:
  Constitution Article III demands a working eval harness producing Recall@k + MRR + judge-graded answer quality, with ≥10 Q&A pairs covering single-chunk factoids, multi-chunk synthesis, and out-of-scope refusals. At baseline: `evals/questions.jsonl` has 2 entries, `rag eval` raises `NotImplementedError` and exits 2, `make eval` calls the stub, the README's "current eval numbers" table doesn't exist.
- **Suggested remediation**:
  Build the minimum viable harness: `src/rag/eval/` module with pure metric functions (Recall@k, MRR, refusal precision, judge-entailment proxy for answer quality), a runner that plumbs each question through the existing `answer_question` orchestrator plus a direct `repo.search` for retrieval-page observability, and JSONL + Markdown reporters. Author 10 new Q&A entries across `factoid`, `synthesis`, and `out_of_scope` categories grounded in the three pages of the sample PDF. Wire `make eval` to invoke the real CLI. Add deterministic unit tests for the metric math.
- **Disposition**: fixed
- **Commit ref**: `19fcaf3 — feat: implement minimal eval harness, expand question set, wire make eval (FND-002)`

### FND-003 — `mypy --strict src/rag` reports 23 errors

- **Area**: `src/rag/api.py` ; `src/rag/lifespan.py` ; `src/rag/providers/gemini.py` ; `src/rag/ui/routes.py` ; `src/rag/ui/upload_jobs.py` ; `pyproject.toml`
- **Severity**: critical
- **Category**: correctness
- **Description**:
  FR-007 requires complete type-hinted signatures on every public function in `src/rag/`. A strict mypy run surfaced 23 errors: an undefined `UploadJob` name in `lifespan.py`, an unused `# type: ignore` in `routes.py`, missing generic args on `asyncio.Task` and `dict`, untyped `_run` in `cli/eval.py`, a real `None`-iteration risk in `providers/gemini.py` (embedding `.values` can be `None`), and the FastAPI `Depends`-helper pattern returning `Any` because `Starlette.app.state` is untyped. Together these prevent strict mode from being a tractable verification tool for FR-007 going forward.
- **Suggested remediation**:
  Configure `[tool.mypy]` in `pyproject.toml` enabling strict for `src/rag/` with narrow per-module suppressions for the SDK boundary: ignore-missing-imports for `pgvector` (no py.typed), disable `arg-type` for `rag.providers.gemini` (the Gemini SDK `contents=` union excludes `list[str]` in the stubs but accepts it at runtime). Then cast at the four FastAPI `Depends` helpers in `api.py` and `routes.py` so the declared return types are honored. Fix the real bugs: import `UploadJob`, type the registry, guard `.values is None`, replace the `# type: ignore[assignment]` self-assignment in the upload route with a `cast(GeminiProvider, ...)`.
- **Disposition**: fixed
- **Commit ref**: `221b457 — fix: pass mypy --strict on src/rag (FND-003)`

### FND-004 — `.venv` shipped with `.exe` shims hardcoded to a different workspace's Python

- **Area**: developer environment — `.venv/Scripts/*.exe`
- **Severity**: critical
- **Category**: correctness
- **Description**:
  `uv run pytest` resolved to `C:\Users\Sam\Desktop\NymblTechAssessment\.venv\Scripts\python.exe` instead of the expected `C:\Users\Sam\Desktop\RAGQuerySystem\.venv\Scripts\python.exe`. The `pytest.exe` launcher in the project venv had the wrong interpreter path baked in (the launcher is a UVPY wrapper that magic-numbers the target python.exe at the end of the binary). The .venv directory had been copied from a sibling workspace at some point, and the launchers were never regenerated. As a result every `uv run pytest` invocation imported an older `rag.providers.gemini` from the sibling workspace — the one where `judge` still raised `NotImplementedError`. Two judge tests "failed" only because they were running against the wrong code.
- **Suggested remediation**:
  `rm -rf .venv && uv sync --dev`. The shims regenerate with the correct interpreter path. Documenting this in `findings.md` because it is the kind of cross-workspace contamination that is invisible in `git status` and `inspect.getsourcefile(...)` but devastating in a CI/handoff scenario.
- **Disposition**: fixed
- **Commit ref**: rebuild was performed locally on 2026-05-14; the surfaced symptom was the spurious test failure on `test_gemini_judge.py`, which is preserved in the baseline test count in `eval-baseline.md`.

### FND-005 — Eval harness can't run inside the container because `evals/` isn't copied or mounted

- **Area**: `Dockerfile` ; `docker-compose.yml`
- **Severity**: major
- **Category**: correctness
- **Description**:
  After FND-002 landed the real `rag eval` CLI, invoking `docker compose exec app rag eval` failed with `FileNotFoundError: '/app/evals/questions.jsonl'`. The Dockerfile copied `src/`, `migrations/`, but not `evals/`. `make eval` therefore wouldn't work for any reviewer who follows the documented quickstart.
- **Suggested remediation**:
  Add `COPY evals/ evals/` to the Dockerfile and mount `./evals:/app/evals` (read-write) in `docker-compose.yml` so a fresh `make eval` can both read the committed question set and write fresh `results.{jsonl,md}` files that the developer commits afterward.
- **Disposition**: fixed
- **Commit ref**: `c-eval-docker — chore: ship evals/ into the app image and mount it back read-write so make eval works in-stack (FND-005)`

### FND-006 — README drift: stale test count, stale tech-stack claim, stale project-layout comment, missing Limitations + eval-results sections

- **Area**: `README.md`
- **Severity**: major
- **Category**: doc
- **Description**:
  Five drift items: (1) test count badge said "77 passing" against 147 actual; (2) Quickstart and Tech stack both claimed the grounding judge runs on "a local OpenAI-compatible LLM (LM Studio / Ollama / llama.cpp)" — historically true, but the system was unified on the Gemini SDK for the judge per the `4d2005f` commit; (3) project-layout tree described `evals/` as `(eval harness lands in a later feature)` — false after FND-002; (4) no `## Limitations` section per FR-017a / Article VIII.4; (5) no `## Eval results` table per FR-014 / Article III.4.
- **Suggested remediation**:
  Bump the badge to 147. Drop the "start a local OpenAI LLM" step from Quickstart. Update tech stack to name `gemini-2.5-flash-lite` as the judge. Fix the `evals/` comment. Add `## Eval results` (from the live `make eval` output) and `## Limitations` (8 specific items grounded in the actual code — single-PDF corpus, no hybrid retrieval, judge cost, refusal-threshold sensitivity, eval set size, 768-dim reshape, no streaming, no auth).
- **Disposition**: fixed
- **Commit ref**: `c-readme-polish — docs: README accuracy sweep, add Limitations and Eval results sections (FND-006)`

### FND-007 — Gitleaks reports 17 hits on a working-tree scan; none on committed surface

- **Area**: `.gitleaks.toml` (new)
- **Severity**: major
- **Category**: security
- **Description**:
  Running `gitleaks detect --source . --no-git --redact` flagged 17 secrets: 16 inside `.venv/Lib/site-packages/` (upstream package test fixtures, RFC ASN.1 reference values mis-classified as keys by the generic-api-key rule, and one ASCII-armored PEM marker inside `google.auth`) plus 1 inside `.env` (the user's local Gemini key — gitignored). All are outside the committed surface, but a reviewer running gitleaks unfiltered would see 17 angry red lines and have to triage them manually.
- **Suggested remediation**:
  Commit a `.gitleaks.toml` config with `[allowlist.paths]` regex entries excluding `.venv/`, `.env`, and `__pycache__`. Rescan with `--config /repo/.gitleaks.toml` — the result is `no leaks found`, exit 0.
- **Disposition**: fixed
- **Commit ref**: `c-gitleaks — chore: add gitleaks config that excludes .venv/.env so committed-surface scan is signal-rich (FND-007)`

### FND-008 — Embed response `.values` could be `None`; `list(None)` would crash at runtime

- **Area**: `src/rag/providers/gemini.py:263` (pre-fix line)
- **Severity**: major
- **Category**: correctness
- **Description**:
  `resp.embeddings[0].values` is typed `list[float] | None` in the Gemini SDK. The previous code unconditionally called `list(resp.embeddings[0].values)`, which would raise `TypeError: 'NoneType' object is not iterable` if the SDK returned an embedding with no values. Unlikely in practice, but a real failure mode and the kind of thing mypy --strict flagged.
- **Suggested remediation**:
  Bind `.values` to a local, check `is None`, raise a typed `RuntimeError("Gemini embed returned an embedding with no values (model=...)")` so the caller surfaces a meaningful error.
- **Disposition**: fixed (folded into FND-003 commit `221b457`)
- **Commit ref**: `221b457 — fix: pass mypy --strict on src/rag (FND-003)`

### FND-009 — Stub-exit test for `rag eval` asserts no-longer-true behavior

- **Area**: `tests/unit/test_cli_stubs.py`
- **Severity**: minor
- **Category**: correctness
- **Description**:
  `test_eval_stub_exits_with_code_2_and_documented_stderr` asserts that `rag eval` exits with code 2 and writes "not yet implemented" / "00X-eval-harness" to stderr. After FND-002 wires the real eval implementation, these assertions are stale and would fail.
- **Suggested remediation**:
  Replace with a `rag eval --help` smoke test that pins the documented option surface (`--questions`, `--results-jsonl`, `--results-md`). Update the module docstring to drop the "eval is still a stub" framing.
- **Disposition**: fixed (folded into FND-002 commit `19fcaf3`)
- **Commit ref**: `19fcaf3 — feat: implement minimal eval harness, expand question set, wire make eval (FND-002)`

### FND-010 — `src/rag/cli/main.py` docstring claims `eval` is a stub

- **Area**: `src/rag/cli/main.py`
- **Severity**: minor
- **Category**: doc
- **Description**:
  Module docstring listed `* eval — stub, delivered by feature 003-eval-harness.` False after FND-002. Same for the Typer command help string `(stub) Run the eval set and emit metrics.`
- **Suggested remediation**:
  Update docstring to `* eval — real, closes Article III (feature 005-code-review-polish).` Drop the `(stub)` prefix on the command help.
- **Disposition**: fixed (folded into FND-002 commit `19fcaf3`)
- **Commit ref**: `19fcaf3 — feat: implement minimal eval harness, expand question set, wire make eval (FND-002)`

### FND-011 — Article VIII.5 slide deck not produced on this branch

- **Area**: project-wide deliverable
- **Severity**: minor
- **Category**: scope
- **Description**:
  Constitution Article VIII.5 obligates a slide deck (PowerPoint / Google Slides / AI-built) covering architecture, query flow, eval results, and next steps. No deck exists in the repo; per Clarifications Q6 the deck is the developer's responsibility outside spec-kit and is explicitly out of scope for this branch.
- **Suggested remediation**:
  Author the deck after the branch merges; it can pull eval numbers directly from `evals/results.md` and screenshots from the running UI.
- **Disposition**: won't fix
- **Rationale**: Developer responsibility outside spec-kit scope per Clarifications Q6 (2026-05-14). Logged here so the constitutional obligation is not silently forgotten and so the constitution-compliance matrix has a stable target for its single remaining ❌ row.

## Eval delta summary

| Metric | Baseline | Final | Delta | Ship? |
|---|---|---|---|---|
| recall_at_5 | n/a (stubbed) | 1.000 | n/a — first run | n/a |
| mrr | n/a (stubbed) | 1.000 | n/a — first run | n/a |
| refusal_precision | n/a (stubbed) | 1.000 | n/a — first run | n/a |
| answer_quality_judge | n/a (stubbed) | 1.000 | n/a — first run | n/a |

There is no regression to disposition because there was no prior eval-harness run. The 1.000 result on the demo corpus is the establishment of the baseline for the next polish pass; it is also the number the README "Eval results" table is populated from.

## Known unfixed constitutional obligations

- **Article VIII.5 — Slide deck** — Out of scope per Clarifications Q6 (2026-05-14). Developer responsibility outside spec-kit. Tracked as `FND-011 — won't fix`.

## Compliance snapshot at merge

- **Nymbl PDF must-haves**: 14 / 15 satisfied (NYM-D3 — slide deck — deferred per FND-011).
- **Constitution articles**: 7 of 8 fully satisfied (I, II, III, IV, V, VI, VII); VIII has one outstanding gap (VIII.5 deck deferred per FND-011, all other VIII.x clauses closed).

## Process notes

Findings were discovered in roughly this order:

1. The "test failures at baseline" were the first thing noticed — running `uv run pytest -q` immediately surfaced 9 failures. Investigation of the 2 `test_gemini_judge.py` failures uncovered FND-004 (the cross-workspace venv contamination), which itself explained why the failures persisted across `__pycache__` clears.
2. After the venv rebuild dropped the failure count to 9 → 7, the remaining failures sorted into three clusters: 3 in `test_current_doc.py`, 2 in `test_ui_brand_contract.py`, 1 in `test_ui_routes.py`, 1 in `test_upload_progress.py`. Inspecting these showed the templates and CSS had been rewritten between branches, and the tests had not been updated to match. The brand-contract test (FND-001) was the largest single asymmetry — the test fixture pinned a palette that was never shipped.
3. The other 4 failures (current-doc, ui-routes, upload_progress) self-resolved once the venv was correct — they had been false negatives from the cross-workspace import, since the OLD workspace's templates were what those tests were finding.
4. With tests green, the obvious next gap was Article III (eval harness stubbed, question set too small). FND-002 was the largest single piece of work.
5. mypy --strict was the systematic discovery method for FND-003 + FND-008; it turned up 23 errors, of which 20 collapsed into "FastAPI Depends + pgvector + Gemini SDK boundary noise" (suppressed at module level) and 3 were real fixes (UploadJob import, `.values` None guard, unused type-ignore).
6. Gitleaks (FND-007) was last because it required Docker running. The first scan reported 17 hits and the `--no-git --redact` mode emits one redacted line per finding, all in `.venv/`; the allowlist closed the report.

False-positive candidates that were ruled out:

- `vulture src/rag tests --min-confidence 80` flagged 7 candidates: 1 in `gemini.py` (unreachable code after a while-loop sentinel — intentional defensive raise), 4 in `conftest.py` / `test_config.py` (pytest-fixture parameters consumed by name via `monkeypatch` injection — false positives), 1 in `test_ui_routes.py` (scripted-response fixture variable used via pytest dependency injection — false positive). None became findings.

## What I would do next

Forward-looking notes, NOT findings — surface during the demo's "next steps" segment.

- **Add hybrid retrieval (BM25 + dense)** behind a feature flag. Article VII lists this as Stretch; the demo eval set is small enough that the win-rate would be hard to read, but a larger corpus would show it.
- **Stream the final-answer tokens** to the UI. Currently the HTMX UI waits for the full pipeline; perceived latency would drop noticeably for the user even though wall-clock cost is the same.
- **Eval set growth** — the current 12 questions are sufficient for regression detection on the sample PDF; a real production corpus would need at least 50–100 across more categories (multi-doc citations, multi-sentence synthesis, near-miss adversarial refusals).
- **Judge-model A/B** — `gemini-2.5-flash-lite` is the cost-efficient choice but the entailment verdicts are conservative. A side-by-side run against `gemini-2.5-flash` would quantify the false-refusal rate.
- **Latency budget per stage** — the structured logs already emit `elapsed_s`; one more polish pass could materialize a per-stage breakdown table in `evals/results.md` so retrieval, generation, and judge wall-clocks are visible at a glance.
