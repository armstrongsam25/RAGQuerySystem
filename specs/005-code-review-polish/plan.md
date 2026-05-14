# Implementation Plan: Production-Polish Code Review Pass

**Branch**: `005-code-review-polish` | **Date**: 2026-05-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification at [specs/005-code-review-polish/spec.md](spec.md) + Nymbl AI Engineer Tech Assessment PDF (attached to the `/speckit-plan` invocation)

## Summary

This is a code-review-and-polish pass, not a feature build. The work product is twofold:

1. **A first-class deliverable** — `findings.md` — that enumerates every issue surfaced during a comprehensive review of the repo (everything except frozen artifacts), categorizes by severity and category, and records disposition. All critical findings are fixed in this branch; majors and minors are at developer discretion with rationale (Clarifications Q2).

2. **A verification bundle** — pre-polish baseline + post-polish results — that proves the system meets two independent bars:
   - The **Nymbl AI Engineer Tech Assessment PDF** (the actual hiring rubric — 5 must-haves: Ingest, Chunk & Embed, Store, Retrieve & Answer with citations and "I don't know" refusal, Hygiene & DX).
   - The **project constitution** (a stricter superset: adds grounding rigor with similarity floor + judge, citation provenance with character offsets, eval discipline with Recall@k + MRR + LLM-judge, code quality floor, demo-as-product framing).

Hard gates: lint clean, unit tests green, integration tests green on final stack. Soft gate: eval reported but non-blocking (Q1). Slide deck out of scope (Q6). README `## Limitations` section in scope (Q7).

**Technical approach is not "write code first" — it is "measure → catalogue → triage → fix → re-measure → document."** The plan below decomposes this into research (Phase 0), schemas/contracts (Phase 1), and a developer quickstart for executing the pass.

## Technical Context

**Language/Version**: Python 3.12 (constitution Article IV.1, `pyproject.toml` `requires-python = ">=3.12,<3.13"`). No language changes.
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, psycopg[binary,pool] 3.2+, pgvector 0.3+, typer, uvicorn, google-genai, openai (judge), jinja2, pypdf, tiktoken, numpy. **No new runtime deps planned** — polish pass should not expand dependency surface.
**Storage**: Postgres 16 + pgvector with HNSW indexes and 768-dim vector columns (Article IV.3, migrations `0001_init_vector_store.sql` and `0002_query_path.sql`). No schema changes planned.
**Testing**: pytest 8.3+ with `pytest-asyncio` (auto mode), ruff 0.6+ for lint and format. Two tiers separated by the `integration` marker — `make test` runs unit-only by default; `make test-integration` runs marked tests with `RUN_INTEGRATION=1`.
**Target Platform**: Docker Compose stack with `app` and `db` services (Article IV.7). Developer machine is Windows 10 with `uv`, Docker Desktop, and a Gemini API key.
**Project Type**: Single repository — web service + CLI + HTMX UI for single-PDF RAG. ~35 Python source files under `src/rag/`, ~25 test files under `tests/`, 2 SQL migrations, 1 sample-PDF generator script.
**Performance Goals**: N/A as a polish *target*. Performance is verified as not-regressed via the eval harness; no new latency or throughput targets are introduced.
**Constraints**:
  - Article VII out-of-scope list: no auth, no observability stacks, no streaming, no frontend redesign.
  - Slide deck (Article VIII.5) is the developer's responsibility outside this branch (Clarifications Q6).
  - Critical findings MUST be fixed; majors/minors at developer discretion with rationale (Clarifications Q2).
  - Constitution Articles I, II, III are load-bearing — polish MUST NOT relax their behavior; changes to them require their own governance commit (FR-022).
**Scale/Scope**:
  - Review surface: entire repo minus frozen artifacts (specs/001–004, `.specify/templates`, `.specify/memory/constitution.md`, `.venv`, ingested data files).
  - Realistic finding volume estimate: 15–40 findings, of which ~3–8 critical, ~10–20 major, ~5–15 minor (calibrated against baseline scan results in Phase 0).
**Pre-polish baseline (captured 2026-05-14)**:
  - `make lint` (ruff check): **passes** with zero errors.
  - `ruff format --check`: **3 files need formatting** (gemini.py, ui/routes.py, test_ui_brand_contract.py) — autofix.
  - `print()` in `src/rag/`: **0** found via quick grep.
  - Bare `except:` in `src/rag/`: **0** found.
  - `TODO`/`FIXME`/`XXX` in `src/rag/`: **0** found.
  - Eval set size in `evals/questions.jsonl`: **2 entries** (constitution Article III.1 requires ≥10).
  - `make eval` target: marked as `(stub) — delivered by feature 00X-eval-harness`.
  - 77 unit tests currently passing per README badge.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Per-article evaluation against the polish-pass scope:

| Article | Title | Status at plan time | Notes |
|---|---|---|---|
| I | Grounding Is Non-Negotiable | **Hold** — invariant | Refusal path exists (similarity floor + judge); FR-011 keeps test coverage. Polish MUST NOT change the floor or judge prompt without a deliberate, traceable change. |
| II | Citations Carry Real Provenance | **Hold** — invariant | Citation construction exists per `src/rag/query/citations.py`; FR-012 keeps test coverage. |
| III | Evaluation Before Demo | **GAP — must fix** | `evals/questions.jsonl` has 2 entries (need ≥10). `make eval` is a stub. README does not display current eval numbers. This is a Phase 0 priority gap that informs Phase 2 task generation. |
| IV | Stack Decisions Are Fixed | **Hold** — invariant | `pyproject.toml` pins Python 3.12, FastAPI, Pydantic v2, pgvector. Embedding model `gemini-embedding-001` with `output_dimensionality=768` per IV.5. No deviations planned. |
| V | Developer Experience | **Hold + minor polish** | `make up`, scripted commands exist, `.env.example` is checked in, secrets via env. Polish verifies the README accurately documents the actual targets and env vars (FR-015, FR-017). |
| VI | Code Quality Floor | **Hold + minor polish** | Ruff config is robust; no bare excepts found; no prints in `src/`. Polish autofixes 3 format-only diffs and verifies every public function has type hints (FR-007). |
| VII | Scope Discipline | **Hold — guardrail** | FR-021/021a/022/023 enforce scope. Findings doc captures missing slide deck (Article VIII.5) without authoring it. |
| VIII | The Demo Is the Product | **Partial — must close** | Articles VIII.1 (spec-kit artifacts as deliverables) satisfied; VIII.2 (clean commit history) is the developer's discipline on this branch; VIII.3 (README stands alone) needs the `## Limitations` section; VIII.4 (limitations specific and honest) is FR-017a; VIII.5 (slide deck) deferred per Clarifications Q6; VIII.6 (30-min demo budget) is SC-007. |

**Verdict**: PASS for Phase 0 entry. Two notable items:
- **Article III is a known gap** (eval set undersized, harness stubbed, README missing numbers). It will be addressed via critical findings in `findings.md` and a Phase 2 task to build out the minimal eval harness.
- **Articles VIII.3/VIII.4** are addressed by FR-017a in spec.

No unjustified violations. The plan does not require entries in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/005-code-review-polish/
├── plan.md                      # This file
├── research.md                  # Phase 0 — baseline measurements + technique choices
├── data-model.md                # Phase 1 — schemas for findings, eval results, compliance matrix
├── contracts/                   # Phase 1 — assessment and constitution compliance matrices
│   ├── nymbl-assessment-compliance.md
│   ├── constitution-compliance.md
│   └── findings-schema.md
├── quickstart.md                # Phase 1 — developer/AI checklist to execute the polish pass
├── checklists/
│   └── requirements.md          # (from /speckit-specify)
├── findings.md                  # Phase 2+ — created during execution, the actual review log
├── eval-baseline.md             # Phase 2+ — pre-polish eval snapshot
├── eval-final.md                # Phase 2+ — post-polish eval snapshot
└── tasks.md                     # /speckit-tasks output (not created here)
```

### Source Code (repository root — unchanged shape)

```text
.
├── src/rag/                     # Library — IN SCOPE for review
│   ├── api.py                   # FastAPI app entrypoint
│   ├── cli/                     # Typer CLI (ingest, query, eval, serve)
│   ├── config.py                # Pydantic Settings, env-var loading
│   ├── db.py                    # psycopg pool, schema bootstrap
│   ├── ingest/                  # PDF → text → chunks → embeddings → store
│   │   ├── chunker.py
│   │   ├── pdf.py
│   │   └── pipeline.py
│   ├── lifespan.py              # FastAPI lifespan
│   ├── log.py                   # Structured logging
│   ├── migrations.py            # Versioned SQL runner
│   ├── providers/               # Gemini, judge abstraction
│   │   ├── base.py
│   │   └── gemini.py
│   ├── query/                   # Retrieval, citation construction, prompts
│   │   ├── citations.py
│   │   ├── pipeline.py
│   │   ├── prompts.py
│   │   └── responses.py
│   ├── repositories/            # In-memory + pgvector implementations
│   │   ├── base.py
│   │   ├── memory.py
│   │   └── pgvector.py
│   ├── trace.py                 # trace_id helpers
│   └── ui/                      # Jinja + HTMX routes, upload jobs/validation
├── tests/                       # Unit + integration tiers — IN SCOPE
├── scripts/                     # IN SCOPE (e.g., make_sample_pdf.py)
├── evals/                       # IN SCOPE (questions.jsonl — under-sized per Art III.1)
├── migrations/                  # IN SCOPE (versioned SQL)
├── Makefile                     # IN SCOPE
├── Dockerfile                   # IN SCOPE
├── docker-compose.yml           # IN SCOPE
├── pyproject.toml               # IN SCOPE
├── README.md                    # IN SCOPE (needs ## Limitations section)
├── CLAUDE.md                    # IN SCOPE (needs plan link update)
├── nymbl-brand.md               # IN SCOPE
├── ui_ux_review.md              # IN SCOPE
├── .env.example                 # IN SCOPE
├── .gitignore / .dockerignore   # IN SCOPE
├── LICENSE                      # IN SCOPE (verify)
├── specs/001-* … 004-*          # FROZEN — out of scope (FR-023)
├── .specify/memory/constitution.md  # FROZEN — only touched via its own governance (FR-022)
├── .specify/templates/          # FROZEN — speckit infrastructure
├── data/sample.pdf              # FROZEN — corpus content
├── data/sample-pdfs/curated/    # IN SCOPE for metadata only
└── .venv/                       # FROZEN — vendored deps
```

**Structure Decision**: No source-code structure change. The polish pass operates on the existing single-project layout above. New artifacts live exclusively under `specs/005-code-review-polish/`. Constitution Article IV pins the stack and project shape; deviations are not warranted by this feature.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No unjustified constitution violations. The Article III gap (under-sized eval set, stubbed harness, missing README numbers) is **known and addressed** as a critical finding in `findings.md`, not a violation of the polish pass itself. The single ambiguity worth flagging:

| Item | Why it's not a violation | How handled |
|---|---|---|
| `make eval` is currently a stub | Pre-existing state, not introduced by this branch | Critical finding; build minimal eval harness producing Recall@k + MRR + judge-graded answer quality. The harness is part of the polish pass deliverables, sized to Article III.1–3 minimums, not a full eval platform. |
| Eval set has 2/10 entries | Pre-existing state | Critical finding; author 8+ additional Q&A pairs covering single-chunk factoids, multi-chunk synthesis, and out-of-scope refusals per Article III.1. |
| Slide deck (Article VIII.5) missing | Deferred per Clarifications Q6 (developer responsibility outside spec-kit) | Logged in `findings.md` with disposition `won't fix in this branch`, rationale documented. |

## Phase 0 — Research

**Goal**: Replace every "we'll see what we find" with a measured baseline + chosen technique.

Research tasks (consolidated in `research.md`):

1. **Baseline capture procedure** — how to snapshot the pre-polish state so regressions are detectable. Choices: scripted vs manual; what goes in `eval-baseline.md`; how to handle non-deterministic judge variance during baseline.
2. **Secret-scan technique** — automated scan for FR-016/SC-005. Choices: `gitleaks` (mature, single binary), `trufflehog` (broader patterns), or grep + entropy heuristic. Decision: gitleaks (no install friction on Windows via Docker, well-known patterns library, low false positives).
3. **Dead-code detection** — for FR-010. Choices: `ruff` `F401` (unused imports — already enforced), `vulture` (broader unreachable-code detection), manual grep audit. Decision: `vulture` as a one-off Phase 2 task with `--min-confidence 80` to avoid false positives, then manual review of each candidate.
4. **Duplication detection** — for FR-010a. Choices: `pylint --duplicate-code`, `jscpd` (cross-language), eyeball review of the small codebase. Decision: eyeball review across `src/rag/` is feasible (~3000 LoC) and produces better calls on "premature abstraction vs duplication" than tools.
5. **Type-hint coverage check** — for FR-007. Choices: `mypy --strict`, `pyright`, `ruff` `ANN` rules. Decision: `mypy --strict` on `src/rag/` as a one-off run, surface gaps as findings.
6. **Eval harness minimum-viable design** — for FR-013 and the Article III gap. Decisions: Recall@k (k=5), MRR; judge-graded answer quality on a 0–1 scale (correct + grounded + cited); results emitted as `evals/results.jsonl` + a markdown summary; runs against `evals/questions.jsonl`.
7. **Comparison framework against Nymbl assessment PDF** — for the user's explicit request. Output: a compliance matrix in `contracts/nymbl-assessment-compliance.md` listing each PDF must-have (Ingest / Chunk & Embed / Store / Retrieve & Answer / Hygiene & DX) and pointing to evidence in the codebase.

**Output**: `research.md` consolidating each decision in `Decision / Rationale / Alternatives considered` format.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete.

### 1. Data Model → `data-model.md`

Entities involved in the polish-pass workflow:

- **Finding** (the row type of `findings.md`): `id` (FND-NNN), `area` (file or module), `severity` (critical / major / minor), `category` (correctness / security / style / doc / scope), `description`, `suggested_remediation`, `disposition` (fixed / deferred / won't fix), `commit_ref` (filled when fixed), `rationale` (filled when deferred / won't fix).
- **EvalResult** (the row type of `eval-baseline.md` and `eval-final.md`): `metric` (recall_at_5 / mrr / refusal_precision / answer_quality_judge), `value`, `n_questions`, `model_versions`, `timestamp`, `delta_vs_baseline` (only in final).
- **ComplianceItem** (the row type of compliance matrices): `requirement_id`, `requirement_text` (verbatim from source), `source` (Nymbl-PDF or Article-X), `evidence` (path:line ranges in code), `status` (satisfied / partial / gap), `notes`.

### 2. Contracts → `contracts/`

The polish pass exposes three "contracts" that the deliverables MUST satisfy:

- **`contracts/nymbl-assessment-compliance.md`** — Compliance matrix mapping every must-have in the Nymbl PDF to evidence in the codebase. Provides the comparison the user explicitly requested.
- **`contracts/constitution-compliance.md`** — Same shape, mapping each of Articles I–VIII to evidence + gap list.
- **`contracts/findings-schema.md`** — Authoritative schema for the row format of `findings.md`. This is the contract the in-progress findings document must honor as items are added during execution.

### 3. Quickstart → `quickstart.md`

A step-by-step checklist the developer (or Claude executing the polish work) follows to perform the pass end-to-end:

  1. Capture pre-polish baseline (lint, tests, secret scan, eval) into `eval-baseline.md` and the findings notebook.
  2. Run the comprehensive review across the in-scope surface, emitting one bullet per finding to `findings.md` (severity, category, suggested remediation).
  3. Triage: classify each finding; assign disposition.
  4. Fix every critical finding; selectively fix majors/minors; commit each fix on its own (FR-020 — clean history).
  5. Build the minimal eval harness; run it; commit results.
  6. Update README: `## Limitations` section (FR-017a), eval-numbers table (FR-014), accuracy sweep (FR-017).
  7. Re-run lint, unit tests, integration tests on final state — all must pass (FR-004/005/006).
  8. Run the secret scan one more time on the final tree (FR-016, SC-005).
  9. Time a demo dry-run; confirm it fits 30 min (SC-007).
  10. Update CLAUDE.md plan-link (FR-018).

### 4. Agent context update

Update the link block in `CLAUDE.md` (between `<!-- SPECKIT START -->` and `<!-- SPECKIT END -->`) to point to this plan (`specs/005-code-review-polish/plan.md`) instead of the prior feature `004-nymbl-ui-polish`. This is required by Phase 1, step 3 of the plan template.

## Re-evaluation: Constitution Check After Design

| Article | Title | Post-design status |
|---|---|---|
| I | Grounding | Hold — design adds no behavioral change. |
| II | Citations | Hold — design adds no behavioral change. |
| III | Evaluation | **Plan now closes the gap**: research.md decision 6 + Phase 2 tasks for the minimal harness + 8 new Q&A pairs + README numbers. |
| IV | Stack | Hold — no dependency or version changes. |
| V | DX | Hold + README sweep planned. |
| VI | Code Quality | Hold + format autofix + type-hint coverage check + dead-code + duplication review planned. |
| VII | Scope | Hold — design adds no new feature surface; out-of-scope items explicitly logged not built. |
| VIII | Demo | Closes VIII.3/VIII.4 (README limitations + accuracy sweep). VIII.5 (deck) explicitly deferred with documented rationale. VIII.6 (30-min budget) verified at the end of execution via dry-run. |

**PASS**: No unjustified violations introduced by the design. Ready for `/speckit-tasks`.

## Stop & Report

This command stops here. The next command is `/speckit-tasks`, which decomposes Phase 2 — the actual review-and-fix work — into ordered, dependency-respecting tasks.
