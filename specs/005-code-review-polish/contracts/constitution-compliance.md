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

## Article III — Evaluation Before Demo (LOAD-BEARING)

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| III.1 | ≥10 Q&A pairs covering single-chunk, multi-chunk, out-of-scope | `evals/questions.jsonl` has **12** entries (7 factoid + 2 synthesis + 3 out-of-scope) per FND-002 | ✅ |
| III.2 | Recall@k and MRR measured | `src/rag/eval/metrics.py` computes both; `rag eval` writes `evals/results.{jsonl,md}` per FND-002 | ✅ |
| III.3 | Answer quality graded via LLM-as-judge or manual rubric, results in repo | Judge runs against each non-refused query; entailment proxy reported as `answer_quality_judge` in `evals/results.md` | ✅ |
| III.4 | README displays current eval numbers; regressions block "done" | README `## Eval results` table populated from `evals/results.md` per FND-006; regressions surface in `eval-final.md` with explicit ship/don't-ship per Clarifications Q1 | ✅ |

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
| V.1 | `make up` works on a fresh machine with Docker + Gemini key | `Makefile` + `docker-compose.yml`; exercised end-to-end during this branch's eval run (FND-002) | ✅ |
| V.2 | Scripted commands for ingest/query/eval/test/lint | `Makefile` covers every target including the now-real `eval` (FND-002) | ✅ |
| V.3 | All secrets via env; `.env.example` checked in; no secrets in code | `.env.example` complete; `.gitignore` excludes `.env`. `Settings` enforces required keys at startup. Gitleaks (with `.gitleaks.toml` allowlist per FND-007) reports 0 leaks. | ✅ |
| V.4 | README: problem statement, architecture diagram, setup, example queries, eval results, known limitations | All present per FND-006; eval results in `## Eval results`, limitations in `## Limitations` | ✅ |

## Article VI — Code Quality Floor

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| VI.1 | ruff lint + format; `make lint` | `make lint` exits 0 on the final tree (0 errors, 0 warnings); format-check exits 0 across all 66 files | ✅ |
| VI.2 | pytest covering chunking, retrieval, citations, refusal | 147 unit tests passing; tests exist for chunker, retrieval ranking, citation construction, refusal, and the new eval-harness metrics | ✅ |
| VI.3 | Type hints on all public functions | `mypy --strict src/rag` exits 0 on the final tree per FND-003 | ✅ |
| VI.4 | Structured logging (JSON or structlog); no `print` in library | `src/rag/log.py`; 0 `print` calls in `src/rag/` | ✅ |
| VI.5 | Errors with actionable messages; no bare `except:`; no silent fallbacks | 0 bare `except:` in `src/rag/`; ruff `BLE001` enforced; FND-008 fixed a `None`-iteration silent fallback in the embed-response path | ✅ |

## Article VII — Scope Discipline

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| VII.out | No auth, no multi-doc corpora, no production observability, no streaming, no polished frontend | None present; HTMX UI is minimal per Article VII | ✅ |
| VII.stretch | Stretch items only after I–III green | Not attempted; Article III is currently ❌ so stretch is correctly deferred | ✅ |

## Article VIII — The Demo Is the Product

| Clause | Requirement (paraphrased) | Evidence | Status |
|---|---|---|---|
| VIII.1 | Spec-kit artifacts + eval results are first-class deliverables, committed | `specs/005-code-review-polish/findings.md`, `eval-baseline.md`, `eval-final.md`, and the compliance matrices are all committed | ✅ |
| VIII.2 | Commit history clean enough to narrate; squash exploratory work | Branch commits follow the `<type>: <summary> (FND-NNN)` pattern; no `wip`, no merge-resolution noise | ✅ |
| VIII.3 | README stands alone | `## Limitations` + `## Eval results` sections added per FND-006; tech-stack and project-layout drift corrected | ✅ |
| VIII.4 | Limitations section MUST be specific and honest | 8 specific items, each grounded in actual code (single-PDF, no hybrid retrieval, judge cost, threshold sensitivity, eval set size, 768-dim reshape, no streaming, no auth) | ✅ |
| VIII.5 | Slide deck committed or linked from README | No deck — DEFERRED per Clarifications Q6, tracked as `FND-011 — won't fix` in `findings.md` | ❌ |
| VIII.6 | 30-minute demo budget; dry-run timed before submission | Dry-run is a merge-time check, not branched into this commit | ⚠ |

## Summary at merge

- **Fully ✅**: Articles I, II, III, IV, V, VI, VII. All previously-partial rows in V, VI, and VIII.1–4 closed during the polish pass.
- **⚠ remaining**: VIII.6 (30-min demo dry-run). This is a stopwatch check the developer runs at merge time, not a code change.
- **❌ remaining**: VIII.5 (slide deck). Explicitly DEFERRED per Clarifications Q6; tracked as `FND-011 — won't fix` in `findings.md`. Developer responsibility outside spec-kit scope.

The polish pass closed every gap it had the authority to close. The single remaining ❌ is the documented deck deferral; the single remaining ⚠ is a developer rehearsal, not a code obligation.
