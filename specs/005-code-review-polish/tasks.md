---

description: "Task list for Production-Polish Code Review Pass (branch 005-code-review-polish)"
---

# Tasks: Production-Polish Code Review Pass

**Input**: Design documents from [specs/005-code-review-polish/](.)
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Test tasks are included only where explicitly required — (a) verifying the existing refusal-path test (FR-011) and citation-construction test (FR-012) still cover their invariants, and (b) one new unit test for the eval-harness metric computation built in this branch (quickstart Step 5). No other new tests are introduced; the polish pass uses existing test suites as a regression net.

**Organization**: Tasks are grouped by user story. User Story 1 (P1 — demo-blocking defects eliminated) is the MVP and dominates the work. User Story 3 (P1 — post-polish verification) runs after US1's critical fixes land. User Story 2 (P2 — senior-quality reading) is selective major/minor fixes the developer judges worth the churn.

## Format: `[TaskID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks).
- **[Story]**: User story this task belongs to (US1, US2, US3). Setup, Foundational, and Polish phases carry no story label.

## Path Conventions

Single project at repo root. Source under [src/rag/](../../src/rag/), tests under [tests/](../../tests/), feature artifacts under [specs/005-code-review-polish/](.). All paths in tasks below are relative to repo root.

---

## Phase 1: Setup

**Purpose**: Confirm branch state and tooling baseline before any review or fix work begins.

- [X] T001 Verify current branch is `005-code-review-polish` and working tree is clean apart from spec-kit artifacts via `git rev-parse --abbrev-ref HEAD` and `git status` (quickstart Step 0)
- [X] T002 Verify [CLAUDE.md](../../CLAUDE.md) plan-link block points to [specs/005-code-review-polish/](.) (FR-018) — if not, update it as a one-line edit and commit `chore: point CLAUDE.md plan link at 005`
- [X] T003 [P] Verify `uv run ruff check .` exits 0 with no errors or warnings (baseline must hold for any subsequent regression to be detectable)
- [X] T004 [P] Verify `gitleaks` Docker image is pullable: `docker pull zricethezav/gitleaks:latest` (research Decision 2)
- [X] T005 [P] Verify `vulture` and `mypy` are installed in the project env: `uv run vulture --version` and `uv run mypy --version` (research Decisions 3 & 5; install via `uv add --dev` only if missing — log as setup commit)

**Checkpoint**: Tooling for the comprehensive review is ready and the lint baseline is green.

---

## Phase 2: Foundational

**Purpose**: Capture the pre-polish baseline so regressions are detectable, scaffold the findings deliverable, and clear the known format-only diff so it does not contaminate downstream finding counts.

**CRITICAL**: Every user-story task depends on the baseline being captured (US3 needs deltas; US1 needs the "before" state to write findings). Do not begin user-story work until this phase is complete.

- [X] T006 Capture pre-polish baseline into [specs/005-code-review-polish/eval-baseline.md](eval-baseline.md) with sections `lint`, `tests` (counts + skip list), `secret-scan`, `eval` (mark `n/a — harness stubbed at baseline; first eval run lands in eval-final.md` per quickstart Step 1), `repo-state` (output of `git rev-parse HEAD`). Commands per [quickstart.md](quickstart.md) Step 1. Commit as `chore: capture pre-polish baseline`
- [X] T007 Scaffold [specs/005-code-review-polish/findings.md](findings.md) per [contracts/findings-schema.md](contracts/findings-schema.md): header block, severity definitions verbatim from [data-model.md](data-model.md), empty summary table, empty Findings section, empty Eval delta summary, Known unfixed constitutional obligations section pre-populated with the Article VIII.5 deferral row (Clarifications Q6), empty Compliance snapshot section. Commit as `chore: scaffold findings.md per schema`
- [X] T008 Apply `uv run ruff format .` to the three baseline format diffs ([src/rag/providers/gemini.py](../../src/rag/providers/gemini.py), [src/rag/ui/routes.py](../../src/rag/ui/routes.py), [tests/unit/test_ui_brand_contract.py](../../tests/unit/test_ui_brand_contract.py)) and commit as `chore: apply ruff format autofix` (quickstart Step 4 / research baseline table)

**Checkpoint**: Baseline committed, findings doc skeleton in place, format gate clean. Comprehensive review can now begin.

---

## Phase 3: User Story 1 — Demo-blocking defects are eliminated (Priority: P1) MVP

**Goal**: Run the comprehensive review across the in-scope surface, log every issue as a Finding in [findings.md](findings.md), then fix every `critical` finding so a reviewer cannot encounter anything that undermines the hiring signal (leaked secrets, broken commands, failing tests, missing citations, broken refusal, stale README, swallowed errors). This phase also closes the known Article III gap (under-sized eval set + stubbed harness) because that gap is itself a critical finding.

**Independent Test**: After this phase, `make lint && make test` exits 0; `make up && make ingest` reaches a queryable state with no errors and no `print` output from library code; an in-scope question returns citations with all required provenance fields; an out-of-scope question returns "I don't know" with no fabricated citations; `findings.md` has no `severity=critical` row with `disposition != fixed`.

### Comprehensive review sweeps (discovery — log findings, do NOT triage during discovery)

- [X] T009 [P] [US1] Run `docker run --rm -v "$PWD":/repo zricethezav/gitleaks:latest detect --source /repo --no-git --redact`; record output (PASS or finding count + redacted entries) as evidence in [specs/005-code-review-polish/findings.md](findings.md) Process notes (research Decision 2; FR-016)
- [X] T010 [P] [US1] Run `uv run vulture src/rag tests --min-confidence 80`; for each candidate, record one draft finding in [specs/005-code-review-polish/findings.md](findings.md) flagged for manual confirmation against dynamic-use paths (CLI entrypoints, FastAPI deps, Jinja vars, eval reflection — Edge Case #3) (research Decision 3; FR-010)
- [X] T011 [P] [US1] Run `uv run mypy --strict src/rag`; for each error involving a public function add a finding to [specs/005-code-review-polish/findings.md](findings.md) with severity=critical if the missing hint is on a public surface (FR-007), else major/minor by caller breadth (research Decision 5)
- [X] T012 [P] [US1] Repetition/duplication sweep — walk [src/rag/](../../src/rag/) module by module looking for logic recurring across two or more modules that could be a shared helper; record each candidate finding in [specs/005-code-review-polish/findings.md](findings.md) with provisional disposition (refactor vs. keep — decided in T020) (FR-010a; Clarifications Q3)
- [X] T013 [P] [US1] Lengthy comments/docstrings sweep — for each file under [src/rag/](../../src/rag/), flag comments/docstrings that describe *what* the code does rather than *why*, restate obvious behavior, or reference rotting task/commit context; record each as a finding in [specs/005-code-review-polish/findings.md](findings.md) (FR-010b; Clarifications Q3)
- [X] T014 [P] [US1] Error-handling sweep — eyeball every `except` clause in [src/rag/](../../src/rag/); flag any that lacks a typed exception, omits structured logging (with `trace_id` when available), or silently swallows failures; record each as a finding in [specs/005-code-review-polish/findings.md](findings.md) (FR-009)
- [X] T015 [P] [US1] README accuracy sweep — for each `make` target listed in [README.md](../../README.md) confirm it exists in [Makefile](../../Makefile); for each env var listed confirm it appears in [.env.example](../../.env.example); for each path in the project-layout tree confirm it exists; if the README states a setup-time claim (e.g., "queryable in N minutes"), confirm it is consistent with the SC-004 ≤10 min bound — pin a concrete time bound if absent so US3 Acceptance Scenario 2 is mechanically verifiable; record every drift as a finding in [specs/005-code-review-polish/findings.md](findings.md) (FR-017; SC-004; SC-008)
- [X] T016 [P] [US1] `.env.example` completeness sweep — grep [src/rag/](../../src/rag/) for `os.environ.get`, `os.getenv`, and Pydantic `Settings` field names; cross-check every variable appears in [.env.example](../../.env.example) with a descriptive comment; record gaps as findings in [specs/005-code-review-polish/findings.md](findings.md) (FR-015)
- [X] T017 [P] [US1] Doc-drift sweep — read [CLAUDE.md](../../CLAUDE.md), [nymbl-brand.md](../../nymbl-brand.md), [ui_ux_review.md](../../ui_ux_review.md); flag references to files/paths/features that no longer exist or are misdescribed; record each as a finding in [specs/005-code-review-polish/findings.md](findings.md) (FR-017, FR-018)
- [X] T018 [P] [US1] Build/deploy hygiene sweep — read [Dockerfile](../../Dockerfile), [docker-compose.yml](../../docker-compose.yml), [Makefile](../../Makefile), [pyproject.toml](../../pyproject.toml) end to end; flag stale base images, mis-pinned versions, unused services, dangling Makefile targets as findings in [specs/005-code-review-polish/findings.md](findings.md)
- [X] T019 [P] [US1] Migrations sweep — read [migrations/0001_init_vector_store.sql](../../migrations/0001_init_vector_store.sql) and [migrations/0002_query_path.sql](../../migrations/0002_query_path.sql); verify each executes cleanly on a fresh DB (`make up` reproduces this); flag any non-idempotent statements or missing indexes as findings in [specs/005-code-review-polish/findings.md](findings.md)

### Triage

- [X] T020 [US1] For every finding logged in T009–T019, assign `severity` (critical / major / minor) and `disposition` (fixed / deferred / won't fix) per [data-model.md](data-model.md) rules in [specs/005-code-review-polish/findings.md](findings.md); enforce FR-001b (no critical may be deferred or "won't fix"); for every `deferred`/`won't fix` write a `rationale` per FR-003; sort the summary table by severity (criticals first)

### Critical fixes — Article III eval-harness closer

- [X] T021 [US1] Author 8+ new Q&A entries in [evals/questions.jsonl](../../evals/questions.jsonl) covering single-chunk factoids, multi-chunk synthesis, and out-of-scope refusals (Article III.1); use the existing two entries as the format reference; commit as `feat: expand eval set to satisfy Article III.1 (FND-NNN)`
- [X] T022 [US1] Implement the `rag eval` CLI in [src/rag/cli/eval.py](../../src/rag/cli/eval.py): load [evals/questions.jsonl](../../evals/questions.jsonl), run each question through the existing query pipeline, compute Recall@5 and MRR over questions with non-empty `expected_pages`, compute refusal precision for `category=out_of_scope`, invoke the existing grounding judge for answer-quality on non-refusal questions, write per-question rows to [evals/results.jsonl](../../evals/results.jsonl) and a human summary to [evals/results.md](../../evals/results.md); commit as `feat: implement minimal eval harness (FND-NNN)` (research Decision 6; FR-013)
- [X] T023 [US1] Update [Makefile](../../Makefile) `eval` target to invoke the harness from T022 directly (remove the `(stub)` annotation); commit as `chore: wire make eval to real harness (FND-NNN)`
- [X] T024 [US1] Add unit test for eval-harness metric computation at [tests/unit/test_eval_harness.py](../../tests/unit/test_eval_harness.py) covering deterministic Recall@5, MRR, and refusal-precision given fixed inputs (judge call is mocked or skipped); commit as `test: add deterministic metric tests for eval harness (FND-NNN)`

### Critical fixes — load-bearing invariants (Articles I, II)

- [X] T025 [P] [US1] Verify refusal-path invariant test at [tests/unit/test_refusal.py](../../tests/unit/test_refusal.py) asserts the system returns "I don't know" both (a) when retrieval similarity falls below the configured floor and (b) when the grounding judge returns a non-entailed verdict; if either branch is missing, add the assertion and commit as `test: harden refusal-path coverage (FND-NNN)` (FR-011)
- [X] T026 [P] [US1] Verify citation-construction invariant test at [tests/unit/test_citation_construction.py](../../tests/unit/test_citation_construction.py) asserts every returned citation includes document id, page number, character offsets (start, end), and the quoted span; if any field is missing from assertions, extend the test and commit as `test: assert full citation provenance (FND-NNN)` (FR-012)

### Critical fixes — all remaining critical findings from T020

- [X] T027 [US1] For each finding in [specs/005-code-review-polish/findings.md](findings.md) with `severity=critical` AND `disposition=fixed` AND not yet implemented by T021–T026, make the change in the relevant file(s) and commit using the format `<type>: <summary> (FND-NNN)` per research Decision 8 (FR-002 / FR-020); after each commit, fill the `Commit ref` field of the matching finding in [specs/005-code-review-polish/findings.md](findings.md)
- [X] T028 [US1] Verify `findings.md` invariant: no row in [specs/005-code-review-polish/findings.md](findings.md) has `severity=critical` AND `disposition != fixed` (FR-001b); confirm by grep before proceeding to US3

**Checkpoint**: Every critical finding has a `Commit ref`. `make lint && make test` exits 0. The eval harness produces real numbers. US1 independent test passes.

---

## Phase 4: User Story 3 — End-to-end behavior is verified after polish (Priority: P1)

**Goal**: After critical fixes land, prove nothing regressed by capturing the post-polish state (eval, lint, tests, integration tests, secret scan), recording deltas, and demoing the system within the 30-minute budget. Eval regressions are reported and human-judged (Clarifications Q1) — they do NOT auto-fail the branch.

**Independent Test**: [specs/005-code-review-polish/eval-final.md](eval-final.md) exists with all six measurements + `delta_vs_baseline` per metric + `ship_disposition` for any regression; `make lint`, `make test`, `make test-integration` all exit 0 on final branch state (the last one against a cold-booted stack per T033); demo dry-run logged at ≤30:00; fresh-setup walkthrough logged at ≤10:00 (SC-004); gitleaks scan reports 0 hits.

**Dependencies**: US1 phase (critical fixes must be in place — most importantly the eval harness from T022 — before final measurements can be taken).

### Verification measurements

- [X] T029 [US3] Run the eval harness (`make eval` or `uv run rag eval`) against the expanded [evals/questions.jsonl](../../evals/questions.jsonl); commit the produced [evals/results.jsonl](../../evals/results.jsonl) and [evals/results.md](../../evals/results.md) as `chore: capture post-polish eval results`
- [X] T030 [US3] Capture post-polish state into [specs/005-code-review-polish/eval-final.md](eval-final.md) with the same six measurement sections as [eval-baseline.md](eval-baseline.md), compute `delta_vs_baseline` for each metric, and assign `ship_disposition` for any regression per [data-model.md](data-model.md) EvalResult validation rules (Clarifications Q1); commit as `chore: capture post-polish final state`
- [X] T031 [P] [US3] Run `uv run ruff check .` and `uv run ruff format --check .` on final tree; both MUST exit 0 (FR-004 / SC-001); record outcome in [specs/005-code-review-polish/eval-final.md](eval-final.md)
- [X] T032 [P] [US3] Run `uv run pytest -q` on final tree; MUST exit 0 with no unexpected skips (FR-005); record pass count in [specs/005-code-review-polish/eval-final.md](eval-final.md)
- [X] T033 [US3] First reset the stack to a cold state: `docker compose down -v && make up` and confirm `/health` returns OK (FR-019 / Article V.1 — this verifies fresh-checkout boot, not just the named pytest invocation); then run `make test-integration` against that fresh stack; MUST exit 0 unconditionally per Clarifications Q5 (FR-006); record cold-boot elapsed time AND integration outcome in [specs/005-code-review-polish/eval-final.md](eval-final.md)
- [X] T034 [P] [US3] Re-run gitleaks on the final tree via `docker run --rm -v "$PWD":/repo zricethezav/gitleaks:latest detect --source /repo --no-git --redact`; MUST report 0 hits (FR-016 / SC-005); record outcome in [specs/005-code-review-polish/eval-final.md](eval-final.md)

### Demo-readiness updates

- [X] T035 [P] [US3] Add `## Limitations` section to [README.md](../../README.md) satisfying FR-017a (Article VIII.4) with specific, honest items grounded in the actual code — candidates: single-PDF corpus, no hybrid retrieval (BM25 not implemented per Article VII), judge LLM cost/latency, refusal-threshold sensitivity, eval set size, 768-dim reshape vs. native 3072-dim Gemini output; commit as `docs: add README Limitations section (FND-NNN)`
- [X] T036 [P] [US3] Add an "Eval results" table to [README.md](../../README.md) populated from [evals/results.md](../../evals/results.md) (FR-014, Article III.4); commit as `docs: publish current eval numbers in README (FND-NNN)`
- [X] T037 [US3] Time a demo dry-run with stopwatch covering architecture walk-through → live in-scope query producing citations → live out-of-scope question producing refusal → eval results → limitations → next steps; record elapsed time in the Process notes section of [specs/005-code-review-polish/findings.md](findings.md); MUST be ≤30:00 per Article VIII.6 / SC-007
- [X] T037a [US3] Stopwatch a fresh-setup walkthrough in a clean working directory: clone the repo to a new path, copy a configured `.env`, run `make up`, ingest the sample PDF, and issue the first successful query through the documented flow; record elapsed wall-clock time in [specs/005-code-review-polish/eval-final.md](eval-final.md); MUST be ≤10:00 per SC-004 (this is the clone→queryable bar, distinct from T037's architecture-demo bar)

**Checkpoint**: Post-polish snapshot committed, all hard gates green, demo timed within budget. US3 independent test passes.

---

## Phase 5: User Story 2 — The code reads as senior-quality (Priority: P2)

**Goal**: Make the major/minor findings from T020 a deliberate decision: fix the ones worth the churn, defer the rest with rationale. After this phase, randomly opening five files in [src/rag/](../../src/rag/) shows type-hinted public surfaces, no `print()`, no bare `except:`, no commented-out blocks, no dead imports — and the docs (README, CLAUDE.md, etc.) accurately describe what the code does today.

**Independent Test**: For five randomly opened files under [src/rag/](../../src/rag/), every public function has a complete type-hinted signature; no `print()` appears; every exception handler specifies a type and logs structured context; the README's command table, project layout, and tech stack match what `make help`, the actual `src/` tree, and [pyproject.toml](../../pyproject.toml) contain.

**Dependencies**: US1 triage (T020) — major/minor findings must be classified and dispositioned before this phase begins. US2 can run after US3 (final hardening) or in parallel with US3 as long as US3's final measurements (T029–T034) re-run if any US2 commit touches measured surfaces.

- [X] T038 [US2] For each finding in [specs/005-code-review-polish/findings.md](findings.md) with `severity=major` AND `disposition=fixed`, make the change in the relevant file(s) and commit per the `<type>: <summary> (FND-NNN)` format; fill the `Commit ref` field of the corresponding finding (FR-002 / FR-020)
- [X] T039 [US2] For each finding with `severity=minor` AND `disposition=fixed`, make the change in the relevant file(s) and commit per the same format; fill `Commit ref` of the corresponding finding
- [X] T040 [P] [US2] Verify no `print()` calls remain in [src/rag/](../../src/rag/) via `grep -rn "print(" src/rag/`; if any are found that did not surface as a finding, add a finding row and fix it (FR-008)
- [X] T041 [P] [US2] Verify no bare `except:` remains in [src/rag/](../../src/rag/) via `grep -rn "except:" src/rag/`; if any are found, add a finding row and fix it (FR-009)
- [X] T042 [P] [US2] Verify no `TODO`/`FIXME`/`XXX` without an associated issue or rationale remains in [src/rag/](../../src/rag/); also confirm no commented-out code blocks remain via `grep -rnE '^\s*#\s*(def |class |if |for |while |return |import |from )' src/rag/` (heuristic for code-shaped comment lines) — for any hit that isn't a finding row already, add one and fix it (per US2 Acceptance Scenario 5; FR-010)
- [X] T043 [US2] If any commit in this phase touched code measured by the eval harness (anything under [src/rag/query/](../../src/rag/query/), [src/rag/ingest/](../../src/rag/ingest/), [src/rag/providers/](../../src/rag/providers/), or [src/rag/repositories/](../../src/rag/repositories/)), re-run the eval harness and update [evals/results.md](../../evals/results.md), [evals/results.jsonl](../../evals/results.jsonl), and the README eval table; record the second measurement in [specs/005-code-review-polish/eval-final.md](eval-final.md) as a follow-up entry

**Checkpoint**: All non-`won't fix` major and minor findings have a `Commit ref`. US2 independent test passes.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Close the compliance matrices, complete the narratable artifacts, and verify every merge-readiness gate from quickstart Step 10 before declaring the branch shippable.

- [X] T044 [P] Update [specs/005-code-review-polish/contracts/nymbl-assessment-compliance.md](contracts/nymbl-assessment-compliance.md): flip every previously partial row to satisfied where the polish pass closed the gap; gap rows remain only for the explicit Article VIII.5 slide-deck deferral; every remaining `status=gap` row MUST link to an open finding in [findings.md](findings.md) per [data-model.md](data-model.md) ComplianceItem validation rules
- [X] T045 [P] Update [specs/005-code-review-polish/contracts/constitution-compliance.md](contracts/constitution-compliance.md) similarly; Article III row MUST flip to satisfied once T022–T024 land; every remaining gap row MUST link to an open finding
- [X] T046 Fill the "Eval delta summary" table in [specs/005-code-review-polish/findings.md](findings.md) with measured values from [eval-baseline.md](eval-baseline.md) and [eval-final.md](eval-final.md) (per [contracts/findings-schema.md](contracts/findings-schema.md) invariant #5 — empty cells not acceptable)
- [X] T047 Fill the "Known unfixed constitutional obligations" section in [specs/005-code-review-polish/findings.md](findings.md) — confirm Article VIII.5 (slide deck) row is present with rationale "developer responsibility outside spec-kit scope per Clarifications Q6" (FR-021a; findings-schema invariant #6); add any other deferred constitutional obligations surfaced during T020
- [X] T048 Fill the "Compliance snapshot at merge" section in [specs/005-code-review-polish/findings.md](findings.md) with counts copied from the two compliance matrices (`Nymbl PDF must-haves: X / Y satisfied`; `Constitution articles: X / Y satisfied`)
- [X] T049 Reconcile header counts in [specs/005-code-review-polish/findings.md](findings.md) with the summary table (findings-schema invariant #1): `Total findings`, `critical:`, `major:`, `minor:` totals MUST match the summary table row counts exactly
- [X] T050 Review `git log --oneline 005-code-review-polish` for narratability per FR-020 / Article VIII.2: no `wip` subjects, no merge-resolution commits, no commits mixing unrelated changes; if any commit needs amending it is done as a fresh commit (never `--amend` on already-pushed history)
- [X] T051 Final merge-readiness gate check per [quickstart.md](quickstart.md) Step 10 — verify all of: `make lint` exit 0, `make test` exit 0, `make test-integration` exit 0 (against cold-booted stack per T033), gitleaks 0 hits, every critical finding has `disposition=fixed` + `Commit ref`, README accuracy spot-check passes, [eval-baseline.md](eval-baseline.md) + [eval-final.md](eval-final.md) committed, both compliance matrices updated, demo dry-run ≤30 min recorded (T037), fresh-setup walkthrough ≤10 min recorded (T037a / SC-004); if any gate is false, do not merge

**Checkpoint**: Every quickstart Step 10 gate is green. Branch is mergeable.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — runs first.
- **Foundational (Phase 2)**: Depends on Setup. BLOCKS all user-story work because (a) US1 sweeps need the format-autofix commit out of the way to avoid noise, and (b) US3 needs the baseline captured to compute deltas.
- **US1 (Phase 3)**: Depends on Foundational. MVP and the largest body of work — comprehensive review + critical fixes + eval-harness build.
- **US3 (Phase 4)**: Depends on US1 (specifically T022 for the harness, T028 for critical-fix invariant). Produces the post-polish snapshot and runs the hard gates.
- **US2 (Phase 5)**: Depends on US1 triage (T020). May run in parallel with US3 if the developer is careful — but any US2 commit that touches eval-measured surfaces invalidates US3's final numbers and T043 must re-run them.
- **Polish (Phase 6)**: Depends on US1, US2, and US3 being complete (every finding needs its disposition and any commit refs filled before the compliance snapshot is taken).

### User Story Dependencies

- **US1 (P1, MVP)**: No story dependencies; this is the foundational review-and-fix work.
- **US3 (P1)**: Depends on US1's eval-harness build and critical-fix completion. US3 is the verification half of the polish bargain — it can only verify *after* fixes land.
- **US2 (P2)**: Depends on US1's triage. Major/minor selectivity is what differentiates US2 from US1's mandatory critical fixes.

### Within Each User Story

- All sweep tasks (T009–T019) are parallel-safe — they read disjoint surfaces and write to the same findings doc append-only.
- Triage (T020) MUST follow all sweeps before any fix is applied.
- Eval-harness build tasks (T021 → T022 → T023 → T024) are sequential by data dependency (questions before harness; harness before Makefile wiring; tests after harness).
- Invariant verification tests (T025, T026) are parallel with each other and with the eval-harness build.

### Parallel Opportunities

- **Setup**: T003, T004, T005 in parallel.
- **Foundational**: T006, T007, T008 are sequential by dependency (baseline → scaffold → autofix) — no parallelism.
- **US1 sweeps**: T009–T019 all parallel (different commands, append-only writes to findings.md — coordinate writes if running concurrently).
- **US1 invariant tests**: T025 and T026 parallel.
- **US3**: T031, T032, T034, T035, T036 parallel after T030 commits. T037a (fresh-clone stopwatch) is maximally parallel because it runs in a separate working directory.
- **US2**: T040, T041, T042 parallel with each other; T038/T039 sequential per commit but each commit is small.
- **Polish**: T044, T045 parallel; T046–T049 sequential (each fills a different section of findings.md but the sections cross-reference each other).

---

## Parallel Example: US1 comprehensive review sweeps

```text
# Launch the read-only sweeps in parallel (each appends draft findings to findings.md):
Task: "T009 — gitleaks scan over working tree"
Task: "T010 — vulture run on src/rag and tests"
Task: "T011 — mypy --strict run on src/rag"
Task: "T012 — repetition/duplication manual review of src/rag/"
Task: "T013 — comment/docstring length review of src/rag/"
Task: "T014 — except-clause review of src/rag/"
Task: "T015 — README accuracy sweep"
Task: "T016 — .env.example completeness sweep"
Task: "T017 — doc-drift sweep on CLAUDE.md / nymbl-brand.md / ui_ux_review.md"
Task: "T018 — build/deploy hygiene sweep"
Task: "T019 — migrations sweep"
```

These are read-only against the codebase and append-only against `findings.md`; running them in parallel is the fastest way through US1 discovery.

---

## Implementation Strategy

### MVP First (Setup → Foundational → US1)

1. Complete Setup (T001–T005) — confirms tooling and branch state.
2. Complete Foundational (T006–T008) — baseline captured, findings scaffold in place, format gate cleared.
3. Complete US1 (T009–T028) — comprehensive review, triage, every critical fix landed, eval harness built.
4. **STOP & VALIDATE**: At this point the demo-blocking-defects story is fully satisfied. The branch could in theory be demoed showing "criticals all fixed, eval harness now works, refusal/citation invariants verified."

### Incremental Delivery (recommended sequence)

1. Setup → Foundational → US1 (MVP) → demoable.
2. US3 (verification) → eval-final.md + integration tests + dry-run → demoable with full hard-gate evidence.
3. US2 (senior-quality selective fixes) → reading impression improved.
4. Polish (compliance matrices + findings.md final sections + merge gate) → mergeable.

### Solo Developer Note

This branch is a one-developer-one-LLM bundle, not a parallel-team feature. The "parallel opportunities" listed above are for when Claude executes multiple read-only sweeps in a single tool-batch invocation — not for splitting work across engineers. Tasks that write to the same file (every sweep writes to `findings.md`) require sequential commits even if the work itself was discovered in parallel.

---

## Notes

- Every "fixed" finding ends up as a commit on `005-code-review-polish` with subject `<type>: <summary> (FND-NNN)`; that trailing token is what makes FR-002 traceability mechanical.
- The eval-harness work (T021–T024) is simultaneously a critical-finding fix (Article III gap closer) AND the prerequisite for US3 verification — that double duty is why it lives in US1, not in Foundational or US3.
- `findings.md` is a first-class committed deliverable per Article VIII.1 / Clarifications Q4 — write it like a document a reviewer reads in isolation, not a scratch log.
- The slide deck (Article VIII.5) is OUT of scope per Clarifications Q6 — do not author one. It is logged as a deferred row in `findings.md` and stays as the only ❌ in the constitution-compliance matrix.
- Constitution Articles I, II, III, IV are load-bearing and SHOULD NOT be touched as part of this pass. If a finding suggests touching them, it becomes a `deferred` item with rationale per FR-022, not a fix.
