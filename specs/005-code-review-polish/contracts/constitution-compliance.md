# Constitution Compliance Matrix

**Branch**: `005-code-review-polish` | **Constitution version**: 1.0.3 (ratified 2026-05-11, last amended 2026-05-12)
**Last updated**: 2026-05-14 (plan time)

This matrix maps each constitutional article (and load-bearing clause) to evidence in the codebase. Status legend: ✅ satisfied · ⚠ partial · ❌ gap. Gaps MUST link to a finding in `findings.md`.

Companion: [nymbl-assessment-compliance.md](nymbl-assessment-compliance.md) maps the same shape against the Nymbl PDF rubric (the stricter superset is the constitution).

## Article I — Grounding Is Non-Negotiable (LOAD-BEARING)

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| I.1 | Every claim traceable to retrieved chunks | `src/rag/query/pipeline.py` constructs answers only from retrieved chunks; prompt enforces grounding in `src/rag/query/prompts.py`. | ✅ |
| I.2 | "I don't know" when retrieval similarity falls below floor OR judge returns non-entailed | Two-tier refusal in pipeline.py: cosine floor check + grounding judge call. Tests in `tests/unit/test_refusal.py`. | ✅ |
| I.3 | Explicit, testable refusal mechanism | Refusal path is unit-tested for both refusal triggers (FR-011 keeps this invariant). | ✅ |

## Article II — Citations Carry Real Provenance (LOAD-BEARING)

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| II.1 | Each chunk persists source doc id, page, char offsets, raw span | `migrations/0001_init_vector_store.sql` schema; `src/rag/ingest/chunker.py` produces these fields. | ✅ |
| II.2 | API responses include quoted span, page, stable chunk id per citation | `src/rag/query/citations.py` + `src/rag/query/responses.py`. Tests: `tests/unit/test_citation_construction.py`. | ✅ |
| II.3 | A reviewer can open the PDF to the cited page and locate the evidence | Page and offsets are preserved; reviewer can do this manually given the API response. | ✅ |

## Article III — Evaluation Before Demo (LOAD-BEARING) ❗

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| III.1 | ≥10 Q&A pairs covering single-chunk, multi-chunk, out-of-scope | `evals/questions.jsonl` has **2** entries at baseline | ❌ — see finding (Phase 2 task: author 8+ additional pairs across categories) |
| III.2 | Recall@k and MRR measured | No harness yet — `make eval` is a stub | ❌ — see finding (Phase 2 task: build minimal eval harness per research Decision 6) |
| III.3 | Answer quality graded via LLM-as-judge or manual rubric, results in repo | Judge implementation exists in `src/rag/providers/gemini.py`; no end-to-end harness call | ❌ — closes when minimal harness lands |
| III.4 | README displays current eval numbers; regressions block "done" | No eval table in README | ❌ — closes when README sweep + harness output land |

This is the largest gap and the most consequential. Phase 2 (`/speckit-tasks`) will produce explicit tasks for each row.

## Article IV — Stack Decisions Are Fixed

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| IV.1 | Python 3.12, deps via uv | `pyproject.toml` `requires-python = ">=3.12,<3.13"`, `uv.lock` present | ✅ |
| IV.2 | FastAPI + Pydantic v2 | `pyproject.toml` `fastapi>=0.115`, `pydantic>=2.7` | ✅ |
| IV.3 | Postgres 16 + pgvector, schema pins `vector(768)` | `docker-compose.yml` uses `pgvector/pgvector:pg16`; migration 0001 creates `vector(768)` column | ✅ |
| IV.4 | PDF extraction via Gemini File API | `src/rag/ingest/pdf.py` | ✅ |
| IV.5 | `gemini-embedding-001` with `output_dimensionality=768`, same for ingest & query | `src/rag/providers/gemini.py` (`EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)`) + config pins | ✅ |
| IV.6 | `gemini-2.5-flash` for generation | `src/rag/config.py` default `GENERATION_MODEL=gemini-2.5-flash` | ✅ |
| IV.7 | Docker Compose with `app` + `db`, pgvector image | `docker-compose.yml` | ✅ |
| IV.8 | Any deviation MUST be justified inline in spec.md | No deviations in this branch | ✅ |

## Article V — Developer Experience

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| V.1 | `make up` works on a fresh machine with Docker + Gemini key | `Makefile` + `docker-compose.yml`; verified by SC-004 once polish completes | ⚠ — verify during polish pass |
| V.2 | Scripted commands for ingest/query/eval/test/lint | `Makefile` lines 11–51 cover all but `eval` (stub) | ⚠ — closes when eval harness lands |
| V.3 | All secrets via env; `.env.example` checked in; no secrets in code | `.env.example` exists; `.gitignore` excludes `.env`. Code-side: `Settings` class. Gitleaks scan pending (SC-005). | ⚠ — closes after scan |
| V.4 | README: problem statement, architecture diagram, setup, example queries, eval results, known limitations | Most present; missing `## Limitations` (FR-017a), missing eval results table (Article III.4 — closes together) | ⚠ — closes during polish |

## Article VI — Code Quality Floor

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| VI.1 | ruff lint + format; `make lint` | `Makefile` `lint`, `fmt` targets; `pyproject.toml` `[tool.ruff]` config | ✅ — baseline: lint passes; 3 format-only diffs pending autofix |
| VI.2 | pytest covering chunking, retrieval, citations, refusal | Tests exist for all four (chunker, retrieval ranking, citation construction, refusal) | ✅ |
| VI.3 | Type hints on all public functions | Pending Phase 2 mypy strict pass | ⚠ — verify during polish |
| VI.4 | Structured logging (JSON or structlog); no `print` in library | `src/rag/log.py` provides structured logger; baseline: 0 `print` in `src/rag/` | ✅ |
| VI.5 | Errors with actionable messages; no bare `except:`; no silent fallbacks | Baseline: 0 bare `except:` in `src/rag/`; ruff `BLE` rule enabled | ✅ — verify exception messages during review (likely some major-tier findings) |

## Article VII — Scope Discipline

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| VII.out | No auth, no multi-doc corpora, no production observability, no streaming, no polished frontend | None present; HTMX UI is minimal per Article VII | ✅ |
| VII.stretch | Stretch items only after I–III green | Not attempted; Article III is currently ❌ so stretch is correctly deferred | ✅ |

## Article VIII — The Demo Is the Product

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| VIII.1 | Spec-kit artifacts + eval results are first-class deliverables, committed | spec/plan/tasks pattern in use; eval results pending | ⚠ — closes after eval harness lands |
| VIII.2 | Commit history clean enough to narrate; squash exploratory work | Branch is fresh; FR-020 + research Decision 8 govern execution-time discipline | ⚠ — verify at merge time |
| VIII.3 | README stands alone | Missing limitations section (FR-017a), missing eval numbers (Article III.4) | ⚠ — closes during polish |
| VIII.4 | Limitations section MUST be specific and honest | Section absent | ❌ — FR-017a closes this |
| VIII.5 | Slide deck committed or linked from README | No deck found | ❌ — DEFERRED per Clarifications Q6; logged as a finding, not authored on this branch |
| VIII.6 | 30-minute demo budget; dry-run timed before submission | Dry-run pending | ⚠ — SC-007 closes |

## Summary at plan time

- **Fully ✅**: Articles I, II, IV, VII; most of VI. The load-bearing grounding/citation/stack articles are intact.
- **⚠ closeable by polish**: Article V (DX), most of VI (quality verification), VIII.1–4, VIII.6. All addressable inside this branch.
- **❌ open gaps**: Article III (entire) and VIII.5 (deck). III closes via the minimal eval harness + extra Q&A pairs. VIII.5 is deferred per Clarifications Q6 with explicit "won't fix in this branch" disposition.

The polish pass execution is bounded by: close all ⚠ rows, close all III ❌ rows, log VIII.5 as a known unfixed gap.
