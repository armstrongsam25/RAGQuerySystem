<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.2 → 1.0.3
Bump rationale: PATCH. Refresh of the embedding-model pin in Article IV.5
                from `Gemini text-embedding-004` to `Gemini
                gemini-embedding-001` with `output_dimensionality=768`. The
                underlying principle ("Gemini-provided embeddings, 768-dim,
                same model for ingest and query") is unchanged; only the
                model id moves, and the 768-dim schema commitment is
                preserved via the `output_dimensionality` parameter so no
                migration is required. Article IV is not load-bearing per
                the constitution's own classification — no I/II/III article
                is touched. Triggered by Google retiring the
                `text-embedding-004` id from the v1beta API on 2026-05-12
                (HTTP 404 "models/text-embedding-004 is not found for API
                version v1beta"), discovered during feature 002 ingest
                shakedown. Same retirement pattern as the IV.6 amendment a
                few hours earlier in the same session.

Modified principles:
  ~ Article IV — Stack Decisions Are Fixed
      Clause IV.5 now pins `gemini-embedding-001` with
      `output_dimensionality=768` (was `text-embedding-004`, 768-dim
      native). The "same model for ingest and query" requirement is
      unchanged, as is the 768-dim schema commitment in IV.3. All other
      clauses of Article IV are unchanged.

Added sections: none
Removed sections: none

Templates requiring updates:
  ✅ no-op    .specify/templates/plan-template.md — no specific model name
              embedded; Constitution Check gate remains dynamic.
  ✅ no-op    .specify/templates/spec-template.md — no constitution
              placeholders; no model names embedded.
  ✅ no-op    .specify/templates/tasks-template.md — no model names embedded.
  ✅ no-op    .specify/templates/checklist-template.md — feature-context driven.

Downstream artifacts requiring update (resolved by this commit):
  ✅ updated  src/rag/providers/gemini.py — GeminiProvider.embed passes
              `EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)` so
              gemini-embedding-001's native 3072-dim output is reshaped to
              match the vector(768) schema column. Module docstring updated.
  ✅ updated  src/rag/providers/__init__.py — package docstring updated.
  ✅ updated  src/rag/config.py — EMBEDDING_MODEL default and
              GEMINI_API_KEY/EMBEDDING_DIM docstrings reflect the new pin.
  ✅ updated  .env.example — comment block reflects the updated pin.
  ✅ updated  README.md — pipeline description + example /health payload.
  ✅ updated  tests/conftest.py, tests/unit/test_health.py,
              tests/integration/test_health_live.py, tests/unit/test_ui_routes.py
              — model-id literals updated to the new pin.

Spec artifacts (frozen historical context, intentionally NOT rewritten):
  ◦ specs/001-rag-boilerplate/** and specs/002-rag-query-and-ui/** retain
    `text-embedding-004` references; these document the decisions that
    were true at spec time. Same treatment as the IV.6 amendment used for
    `gemini-2.0-flash` references in the same specs.

Prior history (preserved for context):
  • 0.0.0 → 1.0.0 (2026-05-11): Initial ratification of all 8 articles.
  • 1.0.0 → 1.0.1 (2026-05-11): Added Article VIII clauses 5 (slide deck)
    and 6 (30-minute demo budget) to align with the Nymbl assessment brief.
  • 1.0.1 → 1.0.2 (2026-05-12): Article IV.6 generation-model pin bumped
    from `gemini-2.0-flash` to `gemini-2.5-flash` after Google retired
    the 2.0 id for new keys.

Follow-up TODOs: none deferred.
-->

# Nymbl RAG Assessment Constitution

## Purpose

Build a small RAG system that demonstrates senior AI engineering judgment, not just a working pipeline. The differentiators are grounding rigor, verifiable citations, and evaluation discipline. Every downstream spec, plan, and task MUST be evaluated against this document.

## Core Principles

### Article I — Grounding Is Non-Negotiable

1. Every claim in a generated answer MUST be traceable to one or more retrieved chunks.
2. The system MUST return "I don't know" when either (a) retrieval similarity scores fall below a configured threshold, or (b) a post-generation grounding check determines the answer is not entailed by the retrieved context.
3. Hallucinations are treated as defects, not edge cases. The codebase MUST contain an explicit, testable mechanism for refusal.

### Article II — Citations Carry Real Provenance

1. Each chunk persisted to the vector store MUST include: source document id, page number, character offsets (start, end), and the raw text span.
2. API responses MUST include, for every supporting chunk: the quoted span, page number, and a stable chunk id.
3. "Source: chunk_47" alone is insufficient. A reviewer MUST be able to open the PDF to the cited page and locate the evidence.

### Article III — Evaluation Before Demo

1. The repo MUST include a hand-curated eval set of ≥10 Q&A pairs covering: single-chunk factoids, multi-chunk synthesis, and intentionally out-of-scope questions whose correct answer is "I don't know."
2. Retrieval MUST be measured with Recall@k and MRR.
3. Answer quality MUST be graded via LLM-as-judge or a manual rubric, with results checked into the repo.
4. The README MUST display current eval numbers. Regressions in evals MUST block "done."

### Article IV — Stack Decisions Are Fixed

1. Language: Python 3.12, dependencies managed by `uv`.
2. API: FastAPI with typed request/response models (Pydantic v2).
3. Vector store: Postgres 16 + pgvector. The embedding column MUST pin dimensionality in the schema (`vector(768)`).
4. PDF extraction: Gemini File API (handles scanned/image pages without bolting on OCR).
5. Embeddings: Gemini `gemini-embedding-001` with `output_dimensionality=768` (the native default is 3072; the API reshapes to 768 to match the `vector(768)` schema column from IV.3). Embedding model MUST be the same for ingest and query, and the requested `output_dimensionality` MUST be the same for ingest and query.
6. Generation: Gemini 2.5 Flash. Pro is acceptable for the grounding check if cost permits.
7. Containerization: `docker compose` with at minimum `app` and `db` services using the `pgvector/pgvector:pg16` image.
8. Any deviation from the above MUST be justified inline in `spec.md`.

### Article V — Developer Experience

1. `make up` (or `docker compose up`) MUST bring the entire system to a queryable state on a fresh machine with only Docker and a Gemini API key.
2. Scripted commands MUST exist for: `ingest`, `query`, `eval`, `test`, `lint`.
3. All secrets come from environment variables. `.env.example` is checked in; `.env` is gitignored. No secrets in code, ever.
4. README MUST contain: one-paragraph problem statement, architecture diagram, setup instructions, example queries, eval results table, known limitations.

### Article VI — Code Quality Floor

1. `ruff` for lint and format; CI-equivalent local check via `make lint`.
2. `pytest` with tests covering chunking boundaries, retrieval ranking, citation construction, and the refusal path.
3. Type hints on all public functions.
4. Structured logging (stdlib `logging` with JSON formatter or `structlog`). No `print` in library code.
5. Errors MUST surface with actionable messages. No bare `except:`. No silent fallbacks that mask data issues.

### Article VII — Scope Discipline

**Out of scope** (do not build, do not spec):

- Multi-document corpora or collections.
- AuthN/AuthZ, multi-tenancy, user accounts.
- Production observability (Prometheus, OpenTelemetry, etc.).
- Streaming token responses.
- A polished frontend. A minimal Streamlit page or single HTMX route is sufficient.

**Stretch** (only after Articles I–III are green):

- Hybrid retrieval: BM25 via Postgres `tsvector` + dense vector, fused with reciprocal rank fusion.
- Cross-encoder reranker over top-N candidates.
- Table-aware chunking that preserves row/column structure.

### Article VIII — The Demo Is the Product

1. Spec-kit artifacts (`spec.md`, `plan.md`, `tasks.md`) and eval results are first-class deliverables, committed to the repo and walked through during the demo.
2. Commit history MUST be clean enough to narrate. Squash exploratory work before submission.
3. The README MUST stand alone: a reviewer who never runs the code should still be able to evaluate architecture, grounding strategy, and eval results.
4. The limitations section MUST be specific and honest. Generic disclaimers ("could be improved with more time") are insufficient.
5. A slide deck (PowerPoint, Google Slides, or AI-built) MUST accompany the demo, covering: architecture overview, live query flow, eval results, and limitations/next steps. The deck MUST be committed to the repo (under `docs/` or equivalent) or linked from the README.
6. The demo is scoped to **30 minutes total**: architecture walk-through, live query flow against the ingested PDF, limitations/next steps, and Q&A with the Nymbl team. A dry-run timed against this budget MUST be completed before submission.

## Governance

This constitution supersedes ad-hoc engineering practices for the duration of the Nymbl RAG Assessment build. All PRs, reviews, and `/speckit-*` artifacts MUST verify compliance with the articles above before they are considered "done."

**Amendment process**: Changes to this constitution during the build MUST be made as a dedicated commit that explains the trade-off (what was relaxed, what was added, why now). Amendments MUST bump the version per the rules below and update the `Last Amended` date.

**Load-bearing articles**: Articles I (Grounding), II (Citations), and III (Evaluation) carry the hiring signal and SHOULD NOT be relaxed. Any amendment touching them requires a written justification in the commit body — not just the diff.

**Versioning policy**:

- MAJOR — backward-incompatible governance changes or removal/redefinition of a load-bearing article.
- MINOR — new article added, or a material expansion of guidance within an existing article.
- PATCH — clarifications, wording fixes, or non-semantic refinements.

**Compliance review**: Every `/speckit-plan` invocation MUST evaluate the proposed plan against each article and surface violations in its Constitution Check section. Unjustified violations block plan approval.

**Version**: 1.0.3 | **Ratified**: 2026-05-11 | **Last Amended**: 2026-05-12
