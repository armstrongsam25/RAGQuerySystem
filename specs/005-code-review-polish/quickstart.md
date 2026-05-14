# Quickstart: Executing the Polish Pass

**Branch**: `005-code-review-polish` | **For**: the developer (Sam) and/or Claude Code executing this branch
**Companion docs**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/)

This is the step-by-step checklist for actually performing the polish pass. Run from the repo root with the branch checked out. Each step has a definition of done.

---

## Step 0 — Confirm branch and clean working tree

- [ ] On branch `005-code-review-polish`: `git rev-parse --abbrev-ref HEAD`
- [ ] Working tree is clean apart from the spec-kit artifacts: `git status`
- [ ] CLAUDE.md plan link points to this feature (FR-018) — addressed by `/speckit-plan` Phase 1 step 3

---

## Step 1 — Capture pre-polish baseline

Create `specs/005-code-review-polish/eval-baseline.md` with each of the following measurements pasted in. Commit as a single commit titled `chore: capture pre-polish baseline`.

- [ ] `uv run ruff check .` (expect: All checks passed)
- [ ] `uv run ruff format --check .` (expect: 3 files would be reformatted)
- [ ] `uv run pytest -q` (expect: 77 passed, 0 failed) — counts MUST be recorded, not just "ok"
- [ ] `git rev-parse HEAD` at capture time
- [ ] Eval — see Step 5 for the harness build; if no harness yet, note `n/a — harness stubbed at baseline; first eval run lands in eval-final.md only`
- [ ] gitleaks scan over working tree: `docker run --rm -v "$PWD":/repo zricethezav/gitleaks:latest detect --source /repo --no-git --redact` (expect: no leaks)

**Definition of done**: `eval-baseline.md` exists, is committed, contains all six rows above.

---

## Step 2 — Run the comprehensive review

For each of these sweeps, record findings as they are discovered into `findings.md` per [contracts/findings-schema.md](contracts/findings-schema.md). Do NOT triage during discovery — capture first, classify later.

Sweep checklist:

- [ ] **Repetition / duplication** (Clarifications Q3) — walk `src/rag/` module by module, looking for logic that recurs across two or more modules in a form that could be a shared helper. Note each candidate. Don't decide refactor vs keep yet.
- [ ] **Lengthy comments / docstrings** (Clarifications Q3) — for each file, scan for comments and docstrings that describe *what* the code does rather than *why*. Note each candidate for trim or removal. Spec FR-010b is the rule.
- [ ] **Dead code** — run `uv run vulture src/rag tests --min-confidence 80`; treat each candidate as a finding to inspect manually. Capture true positives only after confirming the symbol isn't used dynamically (CLI entrypoint, FastAPI dep, Jinja var, eval reflection — see Edge Case #3 in spec).
- [ ] **Type-hint coverage** — run `uv run mypy --strict src/rag`; surface every error involving a public function (FR-007). Add as findings.
- [ ] **Error handling sanity** — eyeball every `except` clause in `src/rag/`: does it specify a type, log structured context with `trace_id` when available, and either re-raise or return a typed error? FR-009.
- [ ] **README accuracy sweep** (FR-017) — for each `make` target listed in README, confirm it exists in `Makefile`. For each environment variable listed, confirm it appears in `.env.example`. For each path in the project-layout tree, confirm it exists.
- [ ] **`.env.example` completeness** (FR-015) — grep `src/rag/` for `os.environ.get`, `os.getenv`, and `Settings`-field names; cross-check every variable appears in `.env.example` with a descriptive comment.
- [ ] **Doc drift** — read `CLAUDE.md`, `nymbl-brand.md`, `ui_ux_review.md`; flag references to files/paths/features that no longer exist or are misdescribed.
- [ ] **Build & deploy hygiene** — read `Dockerfile`, `docker-compose.yml`, `Makefile`, `pyproject.toml` end to end; flag anything stale, mis-pinned, or unused.
- [ ] **Migrations** — read `migrations/0001_init_vector_store.sql` and `0002_query_path.sql`; verify they execute cleanly on a fresh DB (this is exercised by `make up`).
- [ ] **Compliance matrices** — open [contracts/nymbl-assessment-compliance.md](contracts/nymbl-assessment-compliance.md) and [contracts/constitution-compliance.md](contracts/constitution-compliance.md); for every ⚠ or ❌ row, ensure there is a corresponding finding in `findings.md`.

**Definition of done**: `findings.md` exists with the structure mandated by [contracts/findings-schema.md](contracts/findings-schema.md). All sweeps above have produced at least one finding or have been positively closed (e.g., "no duplications found" → state explicitly in the Process notes section, do not silently omit).

---

## Step 3 — Triage and disposition

- [ ] For each finding, assign `severity` (critical / major / minor) using the definitions in [data-model.md](data-model.md).
- [ ] For each finding, assign `disposition` (fixed / deferred / won't fix). Critical MUST be `fixed` (FR-001b). Major / minor at developer discretion (Clarifications Q2).
- [ ] For each `deferred` or `won't fix`, write a `rationale` per FR-003. "Not worth churn for a demo" is an acceptable rationale; an empty rationale is not.
- [ ] Sort the summary table in `findings.md` by severity (critical first).

**Definition of done**: Every finding has both severity and disposition. No `critical + non-fixed` rows exist (FR-001b invariant).

---

## Step 4 — Apply fixes

- [ ] For each `disposition: fixed` finding, make the change. One logical fix per commit (research Decision 8). Commit message format: `<type>: <summary> (FND-NNN)` where `<type>` is one of `fix` / `chore` / `docs` / `refactor` / `test`.
- [ ] After each commit, fill in the `Commit ref` field of the corresponding finding in `findings.md` (FR-002).
- [ ] Run `uv run ruff format .` early to address the 3 baseline format diffs as their own commit (`chore: apply ruff format autofix`).
- [ ] Do NOT mix unrelated changes in a single commit (FR-020).

**Definition of done**: every `fixed` finding has a `Commit ref`. `git log --oneline` reads as a narratable sequence.

---

## Step 5 — Build the minimal eval harness (Article III closer)

Per research Decision 6:

- [ ] Add 8+ Q&A entries to `evals/questions.jsonl` covering single-chunk factoids, multi-chunk synthesis, and out-of-scope refusals (Article III.1). Use the existing two entries as the format reference.
- [ ] Implement the `rag eval` CLI in `src/rag/cli/eval.py` so it loads `evals/questions.jsonl`, runs each question through the query pipeline, captures retrieval metrics (Recall@5, MRR), refusal precision, and judge-graded answer quality, and writes to `evals/results.jsonl` plus `evals/results.md`.
- [ ] Update `Makefile` `eval` target so it is no longer marked `(stub)`.
- [ ] Add a unit test for the eval harness's metric computation (deterministic given fixed inputs).

**Definition of done**: `make eval` produces real numbers; `evals/results.md` exists; Article III.2 status flips from ❌ to ✅ in `contracts/constitution-compliance.md`.

---

## Step 6 — Update README

- [ ] Add `## Limitations` section per FR-017a. Specific items only — name actual constraints visible in the code. Candidates: single-PDF corpus, no hybrid retrieval (BM25 not implemented per Article VII stretch), judge LLM cost/latency tradeoffs, refusal-threshold sensitivity, eval set size, 768-dim reshape vs native 3072-dim Gemini output.
- [ ] Add an "Eval results" table populated from `evals/results.md` (FR-014). Match Article III.4.
- [ ] Sweep README claims against the codebase (FR-017): every `make` target, env var, path in the layout tree, tech stack item must match.
- [ ] Update the unit-test badge count if it has drifted.

**Definition of done**: README contains `## Limitations` and an Eval results table; SC-008 (zero drift) is verified by spot-check.

---

## Step 7 — Capture post-polish state

Create `specs/005-code-review-polish/eval-final.md` with the same six measurements as Step 1, taken now. Compute `delta_vs_baseline` for each eval metric.

- [ ] `uv run ruff check .` (expect: All checks passed)
- [ ] `uv run ruff format --check .` (expect: 0 diffs)
- [ ] `uv run pytest -q` — unit tier still green
- [ ] `RUN_INTEGRATION=1 uv run pytest -m integration` against the running stack (FR-006 — hard gate)
- [ ] Eval re-run; record `delta_vs_baseline` per metric; assign `ship_disposition` for any regression (Clarifications Q1)
- [ ] gitleaks scan over working tree (expect: 0 leaks; SC-005)

**Definition of done**: `eval-final.md` exists with all measurements + deltas + ship dispositions.

---

## Step 8 — Demo dry-run

- [ ] Time a walkthrough covering: architecture, live query flow (one in-scope question producing citations, one out-of-scope question producing refusal), eval results, limitations, next steps. Use a stopwatch.
- [ ] If the walkthrough exceeds 30 minutes, trim — the time budget is a hard constraint per Article VIII.6 and SC-007.

**Definition of done**: dry-run completed within budget; time recorded in `findings.md` Process notes.

---

## Step 9 — Final compliance pass

- [ ] Update [contracts/nymbl-assessment-compliance.md](contracts/nymbl-assessment-compliance.md): every ⚠ → ✅ where appropriate; ❌ stay only for explicitly-deferred items (slide deck per Clarifications Q6).
- [ ] Update [contracts/constitution-compliance.md](contracts/constitution-compliance.md) similarly.
- [ ] Fill in the "Eval delta summary", "Known unfixed constitutional obligations", and "Compliance snapshot at merge" sections of `findings.md`.

**Definition of done**: both compliance matrices have clean ✅ rows for everything except the explicit Article VIII.5 deferral.

---

## Step 10 — Merge readiness gate

All of these MUST be true to merge:

- [ ] `make lint` exit 0 (FR-004 / SC-001)
- [ ] `make test` exit 0 with no unexpected skips (FR-005)
- [ ] `make test-integration` exit 0 against the running stack on the final branch state (FR-006 — unconditional per Clarifications Q5)
- [ ] gitleaks scan: 0 hits (FR-016 / SC-005)
- [ ] `findings.md` complete, all critical findings `fixed`, all dispositions assigned (FR-001b, SC-006)
- [ ] README accuracy verified (SC-008)
- [ ] Eval baseline + final committed (FR-013, SC-003)
- [ ] Compliance matrices both updated
- [ ] Demo dry-run timed under 30 min (SC-007)
- [ ] Commit history narratable (FR-020)

If any of these is false, do not merge.

---

## Rollback

If any step reveals a regression that can't be quickly fixed, the polish branch can be discarded entirely:

```powershell
git checkout main
git branch -D 005-code-review-polish
```

This is safe because all changes were on this branch and `main` is untouched. The findings document is the only artifact worth preserving in that case — copy it to `main` under `docs/post-mortem-005.md` (or similar) before deleting the branch.
