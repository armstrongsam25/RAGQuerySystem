# Feature Specification: Production-Polish Code Review Pass

**Feature Branch**: `005-code-review-polish`
**Created**: 2026-05-14
**Status**: Draft
**Input**: User description: "I want to perform a code review and polish this codebase in lieu of a deployment to a production environment. please be critical of the code, make a plan to remedy aspects, and verify all aspects still work after updating"

## Clarifications

### Session 2026-05-14

- Q: Should eval-score regressions against the pre-polish baseline block the branch merge? → A: No — eval results are reported and any regressions are flagged for review, but do not auto-fail the polish pass.
- Q: What severity bar must be cleared for the polish branch to be considered ready to merge? → A: All **critical** findings MUST be fixed; **major** and **minor** findings are at the developer's discretion (each must still carry a disposition in the findings document).
- Q: What is the scope of the code review surface? → A: Everything in the repo EXCEPT frozen artifacts (prior specs 001–004, the constitution, `data/`, `.specify/templates`, `.venv/`). Pay particular attention to **repetitive code** (duplicated logic across modules) and **lengthy comments/docstrings** that should be trimmed or removed entirely if they describe *what* the code does rather than non-obvious *why*.
- Q: Is the findings document a first-class committed deliverable or a working scratch artifact? → A: First-class committed deliverable, demo-visible — `findings.md` is treated like `spec.md`/`plan.md`/`tasks.md` under Article VIII.1: polished, narratable, walked through in the 30-minute demo to demonstrate triage discipline that a clean diff alone cannot show.
- Q: Are integration tests required to pass before the polish branch can merge? → A: Yes, unconditionally — `make test-integration` MUST be run against the full running stack on the final branch state (regardless of which areas the polish touched) and MUST exit zero before merge. No "only if pipeline code changed" carve-out.
- Q: Is the Article VIII.5 slide deck included in this polish pass? → A: No — the deck is out of scope for branch `005-code-review-polish`. It remains the developer's responsibility outside spec-kit and will be produced separately. The polish pass MUST log the missing-deck status in `findings.md` as a known constitutional gap (Article VIII.5) with disposition "won't fix in this branch" and rationale "developer responsibility outside spec-kit scope per Clarifications 2026-05-14."
- Q: Is the Article VIII.4 README limitations section an explicit polish-pass deliverable? → A: Yes — the polish pass MUST add a `## Limitations` section to `README.md` containing specific, honest items (no generic "could be improved with more time" disclaimers). This is added as a dedicated functional requirement, not left implicit under the general README-accuracy requirement.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Demo-blocking defects are eliminated (Priority: P1)

A reviewer (the Nymbl hiring panel, or any future reader) clones the repo, runs `make up`, ingests a PDF, asks both in-scope and out-of-scope questions, and inspects the code. They MUST NOT encounter anything that would undermine the hiring signal: leaked secrets, broken commands, lint failures, failing tests, missing citations, a refusal path that doesn't refuse, error paths that swallow real failures, or stale README claims that don't match the running code.

**Why this priority**: This is the assessment surface. Anything that fails here directly damages the hiring signal that the constitution exists to protect. Articles I (Grounding), II (Citations), III (Evaluation), and VI (Code Quality Floor) are all in scope here.

**Independent Test**: Run `make lint && make test`, perform a fresh `make up && make ingest && make query`, exercise both an in-scope and an out-of-scope question, and verify the documented refusal behavior and citation structure. No errors, no leaked secrets in logs, no command in the README that fails.

**Acceptance Scenarios**:

1. **Given** a fresh checkout with only `.env` configured, **When** the reviewer runs `make up` followed by `make ingest`, **Then** the system reaches a queryable state with no errors and no `print` output from library code.
2. **Given** the system is running, **When** the reviewer asks a question covered by the ingested PDF, **Then** the response includes one or more citations with document id, page number, character offsets, and a quoted span (Article II).
3. **Given** the system is running, **When** the reviewer asks a question that is clearly out of scope, **Then** the system returns an explicit "I don't know" response with no fabricated citations (Article I).
4. **Given** the repository at HEAD, **When** `make lint` is run, **Then** it exits 0 with no warnings or errors.
5. **Given** the repository at HEAD, **When** `make test` is run, **Then** all unit tests pass; integration tests pass when the stack is up.
6. **Given** the repository, **When** any committed file is inspected, **Then** no secret values (API keys, tokens, passwords) appear in code, logs, comments, or fixtures.

---

### User Story 2 - The code reads as senior-quality (Priority: P2)

A reviewer skimming the codebase forms the impression of a senior engineer's work: consistent style, clear naming, no dead code, no copy-paste duplication, no commented-out blocks, type-hinted public surfaces, structured logging with trace ids, and exception handlers that explain what went wrong rather than masking it. The README, CLAUDE.md, and the constitution accurately describe the codebase as it stands today.

**Why this priority**: The hiring signal is judgment, not just behavior. A working system with sloppy code communicates the opposite of what the constitution is trying to demonstrate. This is the difference between "passes the bar" and "raises the bar."

**Independent Test**: A reviewer randomly opens five files in `src/rag/` and finds: type hints on every public function, no `print()`, no bare `except:`, no commented-out code, no dead imports, no unused variables. The README's command table, project layout, and tech stack all match what `make help`, `find src`, and `pyproject.toml` actually contain.

**Acceptance Scenarios**:

1. **Given** any file under `src/rag/`, **When** inspected, **Then** every public function has a complete type-hinted signature.
2. **Given** any file under `src/rag/`, **When** inspected, **Then** no `print()` calls exist; all diagnostic output goes through the structured logger.
3. **Given** any exception handler in `src/rag/`, **When** inspected, **Then** it specifies an exception type (no bare `except:`), logs structured context, and either re-raises or returns a typed error — it does not silently swallow failures.
4. **Given** the README, **When** cross-checked against the code, **Then** every listed `make` target exists in the Makefile, every claimed environment variable exists in `.env.example`, and the project layout tree matches `src/`'s actual structure.
5. **Given** any source file, **When** inspected, **Then** there are no commented-out code blocks, no `TODO`/`FIXME` markers without an associated issue or rationale, and no dead imports.

---

### User Story 3 - End-to-end behavior is verified after polish (Priority: P1)

After polish changes land, the developer (and any future reviewer) can confirm that nothing regressed: the eval suite produces results that meet the pre-polish baseline, the demo dry-run still fits the 30-minute budget from Article VIII.6, and the documented quickstart still works on a fresh machine.

**Why this priority**: The user explicitly asked for verification. Polish that quietly regresses retrieval recall or refusal precision is worse than no polish — it damages exactly the load-bearing articles (I, II, III) the constitution protects. This is P1 because verification is the *point* of the request, not a nice-to-have.

**Independent Test**: Capture eval metrics (Recall@k, MRR, refusal precision, judge-graded answer quality) before any code changes; capture again after; surface any deltas for review. Eval deltas are reported and human-judged, not merge-blocking (see Clarifications). Time a full demo walkthrough against a stopwatch.

**Acceptance Scenarios**:

1. **Given** baseline eval results captured before the polish pass, **When** the eval suite is re-run after all changes land, **Then** the post-polish numbers are recorded alongside the baseline, any deltas (positive or negative) are surfaced in the findings document, and the developer makes an explicit "ship / don't ship" call on each regression rather than the pipeline failing automatically.
2. **Given** the final polished branch, **When** a fresh `docker compose up` is performed on a clean machine with only `.env` configured, **Then** the system reaches a queryable state within the time the README claims.
3. **Given** the final polished branch, **When** a demo dry-run covering architecture walk-through, live query flow, and limitations is conducted, **Then** it completes within the 30-minute budget defined in Article VIII.6.
4. **Given** the polish changes, **When** the eval suite is run, **Then** the README's "current eval numbers" table is updated to reflect the latest run (Article III.4).

---

### Edge Cases

- A "polish" change accidentally weakens the refusal path (e.g., raises the similarity floor too high, or judge prompt changes silently fabricate "supported" verdicts). Eval must catch this.
- A refactor renames or moves a file referenced in `README.md`, `CLAUDE.md`, the project-layout tree, or a `specs/00X-*/plan.md`. Doc drift must be detected before the branch merges.
- An import or symbol flagged as "dead" is actually used through a dynamic path (CLI entrypoint, FastAPI dependency, Jinja template variable, eval harness reflection). Removal must be paired with execution of every entrypoint.
- A "clean up logging" change strips a field a future operator would need to correlate ingest failures (e.g., `trace_id`, `doc_id`, `page`).
- A polish change re-runs ingest with a different chunker setting and silently changes the embedding row count; eval comparisons become apples-to-oranges.
- An out-of-scope refactor creeps into the change set (e.g., adding auth, observability, or a polished frontend), violating Article VII.
- The `.env.example` and `.env` files drift: a new variable used by the code is missing from `.env.example`, so a fresh checkout can't boot.
- A secret is committed in a fixture or test snapshot (real API key in a recorded HTTP transcript). Secret scan must catch this.
- The constitution's load-bearing articles (I, II, III) are touched without an accompanying version bump and Sync Impact Report, per its own governance rules.

## Requirements *(mandatory)*

### Functional Requirements

**Defect identification and tracking**

- **FR-001**: The polish pass MUST produce a code review findings document under the feature directory enumerating every identified issue with: file/area, severity (critical / major / minor), category (correctness, security, style, doc, scope), and disposition (fixed, deferred with rationale, won't fix).
- **FR-001a**: Severity tiers MUST be defined in the findings document itself with concrete examples (e.g., critical = leaked secret, broken refusal path, lint failure, security regression; major = type-hint gap, weak error message, doc drift; minor = naming inconsistency, comment clarity). This makes the bar auditable.
- **FR-001b**: Every finding classified as **critical** MUST have a disposition of "fixed" — critical findings cannot be deferred or marked "won't fix" (per Clarifications 2026-05-14). Major and minor findings may carry any disposition the developer judges appropriate, with rationale.
- **FR-002**: Every "fixed" finding MUST be traceable to a commit in the `005-code-review-polish` branch.
- **FR-003**: Every "deferred" or "won't fix" finding MUST have a written rationale referencing either Article VII (out of scope), an explicit constraint, or an explicit judgment call ("not worth the churn for a demo" is acceptable; an empty rationale is not).

**Quality floor (Article VI)**

- **FR-004**: `make lint` MUST exit zero with no warnings or errors after the polish pass.
- **FR-005**: `make test` (unit tier) MUST exit zero with no skipped tests other than those guarded by documented external-dependency markers.
- **FR-006**: `make test-integration` MUST exit zero against the full running stack on the final branch state before merge, regardless of which files the polish pass touched (per Clarifications 2026-05-14). The integration run is a hard gate, not advisory; "we only changed comments" is not a basis to skip it.
- **FR-007**: Every public function in `src/rag/` MUST carry a complete type-hinted signature.
- **FR-008**: No `print()` calls MUST remain in `src/rag/` (the library) — only `scripts/` and CLI user-facing output are permitted to write to stdout.
- **FR-009**: No bare `except:` MUST remain. Every exception handler MUST specify an exception type, log structured context (including `trace_id` when available), and either re-raise, raise a typed error, or return a typed error — never silently swallow.
- **FR-010**: Dead code MUST be removed: unused imports, unreachable branches, unused private helpers, commented-out blocks, files referenced by nothing.
- **FR-010a**: Repetitive code (logic duplicated across two or more modules that could be expressed as a shared helper without forcing an awkward abstraction) MUST be flagged as a finding. The disposition column decides whether to refactor or keep — premature abstraction is itself a defect, so "kept duplicated; abstraction would be worse" is a valid disposition with rationale.
- **FR-010b**: Comments and docstrings MUST be reviewed for length and information density. A comment or docstring SHOULD be removed or trimmed when it (a) describes what well-named code already says, (b) references the current task or commit context that will rot, or (c) restates obvious behavior. Comments are kept when they explain *why* — hidden constraints, subtle invariants, workarounds, surprising behavior.

**Review surface (Article scope)**

- **FR-010c**: The code review MUST cover the entire repository tree EXCEPT the frozen artifacts: prior spec directories (`specs/001-*`, `specs/002-*`, `specs/003-*`, `specs/004-*`), the constitution at `.specify/memory/constitution.md` (touched only via its own governance), the speckit templates under `.specify/templates/`, the local virtualenv `.venv/`, and ingested data under `data/sample-pdfs/` (except `data/sample-pdfs/curated/` whose metadata may be touched if needed). All other files — `src/`, `tests/`, `scripts/`, `evals/`, `migrations/`, `Makefile`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `README.md`, `CLAUDE.md`, `nymbl-brand.md`, `ui_ux_review.md`, and any committed slide deck — are in scope per Clarifications 2026-05-14.

**Load-bearing articles (I, II, III) — invariants, not deltas**

- **FR-011**: The refusal path MUST remain covered by at least one unit test that asserts the system returns "I don't know" both (a) when retrieval similarity falls below the configured floor and (b) when the grounding judge returns a non-entailed verdict.
- **FR-012**: Citation construction MUST remain covered by at least one unit test asserting that every returned citation includes document id, page number, character offsets (start, end), and the quoted span.
- **FR-013**: The eval harness MUST be runnable via `make eval` (or the equivalent `uv run rag eval`) and MUST produce Recall@k, MRR, and answer-quality numbers that are written to a results file checked into the repo.
- **FR-014**: The README MUST display the post-polish eval numbers in its results table (Article III.4).

**Hygiene and demo-readiness (Articles V, VIII)**

- **FR-015**: `.env.example` MUST contain every environment variable read by `src/rag/`, each with a descriptive comment; `.env` MUST remain gitignored.
- **FR-016**: No secret values MUST appear in any committed file, log statement, error message, or test fixture. An automated secret scan MUST be run and its output checked.
- **FR-017**: The README's command table, project layout tree, tech stack, and quickstart steps MUST match the codebase at HEAD after polish.
- **FR-017a**: The README MUST contain a `## Limitations` section satisfying Article VIII.4 (per Clarifications 2026-05-14): specific, honest items grounded in the actual codebase (e.g., single-PDF corpus, no hybrid retrieval, judge LLM cost/latency, refusal-threshold tradeoffs, eval set size). Generic disclaimers like "could be improved with more time" are not acceptable — each item MUST name a concrete constraint or tradeoff visible in the code.
- **FR-018**: `CLAUDE.md` MUST be updated if any file path it links to has moved or been removed.
- **FR-019**: `make up` on a fresh checkout (with only Docker, a Gemini API key in `.env`, and any locally-configured judge LLM) MUST bring the system to a queryable state, matching Article V.1.
- **FR-020**: The git history on the `005-code-review-polish` branch MUST be clean enough to narrate during the demo (per Article VIII.2): no merge-resolution noise, no "wip" commits, no commits that mix unrelated changes.

**Scope discipline (Article VII)**

- **FR-021**: The polish pass MUST NOT introduce authentication, authorization, multi-tenancy, production observability stacks (Prometheus, OpenTelemetry, Sentry, etc.), token streaming, or a redesigned frontend.
- **FR-021a**: The Article VIII.5 slide deck is out of scope for this branch (per Clarifications 2026-05-14). The polish pass MUST NOT author, generate, or commit deck files. It MUST, however, record the missing-deck status as a finding in `findings.md` so the constitutional obligation is not silently forgotten.
- **FR-022**: Any change to the constitution itself MUST be a separate commit with version bump and Sync Impact Report per the constitution's own governance rules.
- **FR-023**: The polish pass MUST NOT delete or rewrite prior spec artifacts (`specs/001-*`, `002-*`, `003-*`, `004-*`); those are frozen historical context.

### Key Entities *(include if feature involves data)*

- **Code Review Findings Document**: A markdown file at `specs/005-code-review-polish/findings.md`, treated as a first-class committed deliverable per Article VIII.1 (per Clarifications 2026-05-14). Each finding has: id, file or area, severity, category, description, suggested remediation, disposition, and (for fixed items) commit reference. The document itself MUST be readable in isolation — narratable in the 30-minute demo without requiring a reviewer to also have the diff open — and MUST include a severity-definitions section per FR-001a so the bar is auditable.
- **Eval Baseline & Final Results**: Two snapshots of `evals/` output (Recall@k, MRR, refusal precision, answer-quality scores) — one captured before any polish changes, one after — committed to the repo so regressions are auditable.
- **Polish Changelog**: The commit history on the `005-code-review-polish` branch, narratable in the demo per Article VIII.2.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Lint reports zero warnings and zero errors across the entire `src/` and `tests/` tree.
- **SC-002**: 100% of pre-existing unit tests pass after polish; integration tests pass when the stack is running.
- **SC-003**: Post-polish eval scores (Recall@k, MRR, refusal precision, answer quality) are captured and committed alongside the pre-polish baseline; any metric that falls below baseline is enumerated in the findings document with an explicit ship/don't-ship disposition from the developer. Eval deltas do NOT auto-fail the polish pass (per Clarifications 2026-05-14).
- **SC-004**: A reviewer can complete fresh setup (clone → `make up` → first successful query) in under 10 minutes following only the README, on a machine with Docker and a Gemini API key already configured.
- **SC-005**: An automated secret scan reports zero hits across committed files.
- **SC-006**: 100% of issues enumerated in the findings document have a disposition (fixed, deferred with rationale, or won't fix with rationale).
- **SC-007**: A timed demo dry-run covering architecture, live query flow, eval results, and limitations completes within the 30-minute budget from Article VIII.6.
- **SC-008**: README claims (command list, project tree, tech stack, eval numbers) are validated against the actual codebase with zero drift.

## Assumptions

- **"In lieu of a deployment to a production environment" is rhetorical**, not literal. This codebase is a hiring assessment demo, not a system being shipped to paying users. The polish pass applies production-grade *quality* standards (lint, types, structured logging, no secrets, no dead code, accurate docs) but DOES NOT introduce production *features* the constitution explicitly puts out of scope (auth, multi-tenancy, observability stacks, streaming, polished frontend per Article VII).
- The pre-polish state — current lint output, current test pass count, current eval numbers — is captured as a baseline before any code changes begin, so regressions are detectable.
- "Critical" review means principled critique informed by the constitution's quality floor (Article VI) and demo-product framing (Article VIII), not maximalist nitpicking. Findings are triaged; not every nit becomes a commit.
- The reviewer can run Docker, has a Gemini API key, and (for the grounding judge) has either a local OpenAI-compatible LLM available or Gemini configured for that role.
- Articles I, II, III, and VII of the constitution are load-bearing for this feature and SHOULD NOT be touched. If a polish finding suggests touching them, it becomes a deferred item with rationale, not a fix.
- The previous feature branch (`004-nymbl-ui-polish`) is already merged or its state on `main` is the polish-pass starting point. The polish pass operates on the codebase as it stands at branch creation, not on any in-flight feature work.
- All polish work happens on the `005-code-review-polish` branch and is reviewed as one bundle before merge to `main`; rollback is a simple branch discard if regressions are found.
