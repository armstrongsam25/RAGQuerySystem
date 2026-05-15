# Phase 0 Research: Production-Polish Code Review Pass

**Branch**: `005-code-review-polish` | **Date**: 2026-05-14
**Companion plan**: [plan.md](plan.md)

This document records the decisions for every technique the polish pass relies on, plus the pre-polish baseline measurements that make regression detectable. Each entry follows `Decision / Rationale / Alternatives considered`.

---

## Pre-polish baseline (captured 2026-05-14)

These are the measured facts the polish pass starts from. The post-polish state must match or improve them (subject to the eval-non-blocking exception from Clarifications Q1).

| Signal | Pre-polish value | Source / how to reproduce |
|---|---|---|
| `ruff check .` | All checks passed (0 errors, 0 warnings) | `uv run ruff check .` |
| `ruff format --check .` | 3 files would be reformatted: `src/rag/providers/gemini.py`, `src/rag/ui/routes.py`, `tests/unit/test_ui_brand_contract.py` | `uv run ruff format --check .` |
| `print()` calls in `src/rag/` | 0 | quick grep |
| Bare `except:` in `src/rag/` | 0 | quick grep |
| `TODO` / `FIXME` / `XXX` in `src/rag/` | 0 | quick grep |
| Eval set size | 2 entries (`q-000-example-factoid`, `q-000-example-out-of-scope`) | `wc -l evals/questions.jsonl` |
| Eval harness | Stub — `make eval` calls `rag eval` but the CLI command is a placeholder per its own help text | `Makefile` line 46 |
| README "current eval numbers" table | Not present | `grep -i eval README.md` |
| README `## Limitations` section | Not present | `grep -i limitation README.md` |
| Slide deck | Not present anywhere in the repo | `find . -name '*.pptx' -o -name '*.key' -o -iname '*slide*'` |
| Unit test count | 77 (per README badge) | `uv run pytest --collect-only -q | tail` |
| Integration tests | Present, gated by `RUN_INTEGRATION=1` and `pytest -m integration` | `pyproject.toml` `[tool.pytest.ini_options]` markers |
| CLAUDE.md plan link | Points to `specs/004-nymbl-ui-polish/` (stale — must update during this pass) | `CLAUDE.md` line 5 |

---

## Decision 1 — Baseline capture procedure

**Decision**: Capture the baseline as a single committed markdown file `eval-baseline.md` in the feature directory. Sections: `lint`, `tests` (counts + skip list), `secret-scan`, `eval` (Recall@k, MRR, judge-graded answer quality on the existing 2-question set plus the 8+ to be added), `repo-state` (git rev at capture). Capture is performed by the developer running each measurement command and pasting outputs — no automation script is built for this; the measurement set is too small to justify scaffolding.

**Rationale**: A markdown snapshot is auditable, diffable, narratable in the demo, and survives without a runtime. Scripting would be over-engineering for a one-shot capture.

**Alternatives considered**:
- Bash script that re-runs every check and produces JSON → rejected; small payoff, more code to maintain.
- Commit raw command outputs to a `baseline/` folder → rejected; harder to read in the demo than a single markdown file.

---

## Decision 2 — Secret-scan technique

**Decision**: Use `gitleaks` invoked via its official Docker image to scan the committed tree on the final branch state. Command pattern: `docker run --rm -v "$PWD":/repo zricethezav/gitleaks:latest detect --source /repo --no-git --redact`. Run output (PASS or count of findings) is pasted into `findings.md` as evidence for FR-016/SC-005.

**Rationale**: gitleaks is mature, has a well-maintained patterns library, is single-binary via Docker (no install friction on Windows), and produces low false-positive output on a small codebase. Running over the working tree (`--no-git`) rather than the history is sufficient for the polish pass because the branch is fresh; we don't need to scrub history.

**Alternatives considered**:
- `trufflehog` → rejected; broader patterns, but slower and noisier on a small repo; gitleaks is the de-facto standard.
- Custom grep + entropy heuristic → rejected; rewrites a solved problem and misses common patterns (Gemini keys, OpenAI keys).
- GitHub's secret scanning (push-time) → rejected; the polish pass is local; we need to verify locally before push, not after.

---

## Decision 3 — Dead-code detection

**Decision**: Run `vulture` once against `src/rag/` and `tests/` with `--min-confidence 80` and treat each candidate as a *finding to inspect*, not an automatic removal. Manual confirmation required for every removal because of dynamic-use risk (Edge Case #3 in spec: CLI entrypoints, FastAPI dependencies, Jinja template variables, eval-harness reflection).

**Rationale**: Ruff's `F401` already catches unused imports (lint passes — that surface is clean). Vulture catches the broader class (unused private helpers, unreachable branches, dead methods). Confidence threshold 80 produces a manageable candidate list; lower thresholds drown signal in noise.

**Alternatives considered**:
- Ruff's `RUF013` and friends → already enabled; covers the lint-detectable subset.
- Manual grep audit only → rejected; small codebase but still ~3000 LoC, easy to miss helpers used only in one ingest path.
- `pylint --dead-code` → rejected; pylint is heavier than the value delivered for a one-shot scan.

---

## Decision 4 — Duplication detection

**Decision**: Manual review across `src/rag/` driven by reading the module list end-to-end. No tool. Findings are recorded under FR-010a with one of two dispositions: "refactored to shared helper" (with commit ref) or "kept duplicated; abstraction would be worse" (with rationale).

**Rationale**: The codebase is ~3000 LoC across ~35 files. A senior reviewer can read it all and make the "is this premature abstraction?" judgment better than a Levenshtein-based duplication detector. The user explicitly called out "repetitiveness" (Clarifications Q3) as an attention focus — this is judgment work, not pattern matching.

**Alternatives considered**:
- `pylint --duplicate-code` → rejected; produces noisy reports on small codebases and can't judge "should this be abstracted?"
- `jscpd` → rejected; same issue, cross-language tool not optimized for Python idioms.
- Skip detection entirely → rejected; user explicitly asked for this attention.

---

## Decision 5 — Type-hint coverage

**Decision**: Run `mypy --strict` once against `src/rag/` (not `tests/`). Each remaining error is a finding; severity is "critical" only when the missing hint is on a public function in the library (FR-007), otherwise "major" or "minor" depending on caller breadth.

**Rationale**: Mypy strict catches missing hints, `Any` leaks, and untyped third-party imports — the exact surface FR-007 cares about. Ruff has ANN rules but they overlap and produce duplicate signal; mypy's output is more actionable. Tests are excluded because strict typing in test setup is rarely worth the noise.

**Alternatives considered**:
- `pyright` → roughly equivalent; mypy chosen for being already-installable via uv and broader Python community familiarity.
- Ruff `ANN` rules → rejected; configuring them to match mypy strict's behavior is more work than just running mypy once.
- Skip; rely on review only → rejected; a quick `mypy --strict` is cheap and produces a concrete checklist.

---

## Decision 6 — Eval-harness minimum-viable design

**Decision**: Build the smallest harness that satisfies Article III. Concretely:

- **Inputs**: `evals/questions.jsonl` (must contain ≥10 entries by completion, currently 2 — author the additional 8+ during the polish pass).
- **Retrieval metrics**: Recall@k for k=5 (the system's default top-k), and MRR. Computed over the questions where `expected_pages` is non-empty.
- **Refusal metric**: For `category=out_of_scope` questions, success = the system returned the configured refusal string. "Refusal precision" = correct refusals / total out-of-scope questions.
- **Answer-quality metric**: For non-refusal questions, the existing grounding judge (already in `src/rag/providers/gemini.py`) scores each response on a 0–1 scale (entailed-by-context = 1; not-entailed = 0). Aggregate via mean.
- **Outputs**: `evals/results.jsonl` (per-question machine-readable) and `evals/results.md` (human summary with the four headline numbers).
- **README**: An "Eval results" table reproduced from `evals/results.md` (FR-014).
- **Determinism**: Retrieval metrics are fully deterministic given the same embeddings + DB state. Judge-graded quality is non-deterministic; the harness reports a single run, and Clarifications Q1 allows judgement on regression.

**Rationale**: This is the minimum viable shape that satisfies Article III.1–4 without expanding into a full eval platform (Stretch territory per Article VII). The judge already exists; the chunker, retriever, and citation builder already exist. The harness is mostly glue.

**Alternatives considered**:
- Build a more elaborate harness with multiple k values, per-category breakdowns, sweep across thresholds → rejected; scope creep. Save for a later feature if needed.
- Skip the harness and rely on manual smoke testing → rejected; violates Article III directly and would be a "won't fix" on a load-bearing article, which spec FR-022 effectively prohibits.
- Reuse an external eval framework (RAGAS, etc.) → rejected; new dependency surface (Article IV violation by introducing un-pinned tooling), and the existing primitives already produce the needed numbers.

---

## Decision 7 — Comparison framework against the Nymbl PDF

**Decision**: Build `contracts/nymbl-assessment-compliance.md` as a flat compliance matrix. One row per assessment must-have, with: `id` (NYM-1..NYM-5 plus sub-bullets), `requirement` (verbatim from the PDF), `evidence` (file paths and brief description), `status` (✅ satisfied / ⚠ partial / ❌ gap), `notes`.

**Rationale**: The user explicitly asked for this comparison. A flat matrix is the same shape as standard compliance-mapping artifacts (e.g., SOC2 control mappings) — familiar to engineers and reviewers alike. Status-coded so a reader can scan the column and see green/yellow/red at a glance.

**Alternatives considered**:
- Long-form prose section in README → rejected; harder to scan, harder to update, mixes with public-facing docs.
- Inline as a section of `findings.md` → rejected; conflates two artifacts (one is a *check against an external rubric*, the other is *the developer's own critique*).
- Inline as a section of plan.md → rejected; plan is for the implementation strategy, not the compliance evidence.

---

## Decision 8 — Commit granularity (FR-020 implementation guidance)

**Decision**: One logical change per commit. Each "fix a finding" gets its own commit with a message of the form `fix: <one-line summary> (FND-NNN)`. The trailing `(FND-NNN)` makes traceability for FR-002 mechanical. Multi-file changes are fine within a commit if they implement one logical fix (e.g., renaming a function across its definition + callers).

**Rationale**: This is what Article VIII.2 ("Commit history MUST be clean enough to narrate") demands operationally. Tying each commit to a finding id closes the audit loop in `findings.md`.

**Alternatives considered**:
- Squash everything at the end → rejected; loses the narrative the constitution mandates.
- Allow ad-hoc commits and clean up at the end with interactive rebase → rejected; the prompt's git safety protocol disallows `-i` flags, and squash-late is error-prone.

---

## Outstanding (low-impact) items deliberately not researched

- README's "queryable state within time" claim (Clarifications coverage note) — resolved at execution time by either measuring once or softening the claim. Not worth a research entry.
- Demo dry-run procedure (who runs the stopwatch, whether to record) — execution detail; the developer decides at the time.
- Integration-test fidelity (does the judge LLM need to be configured for integration runs?) — answered in practice by FR-006 wording: the *full running stack* on the final branch state. If the judge is part of the stack, it's in. If a test is marked `integration` and skips when the judge is absent, that's the test's own skip semantics, not a polish-pass decision.

---

## Summary

Every NEEDS-CLARIFICATION-style placeholder in plan.md's Technical Context is resolved by one of decisions 1–8 above. Phase 1 (data model, contracts, quickstart) is unblocked.
