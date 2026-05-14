# Implementation Plan: RAG Query Path + Minimal UI

**Branch**: `002-rag-query-and-ui` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-rag-query-and-ui/spec.md`

## Summary

Turn the boilerplate from feature 001 into a working end-to-end RAG slice. PDF ingestion runs page-by-page through the Gemini File API and produces page-bounded chunks (~600 tokens / 80-token overlap, never crossing a page boundary so Article II citations are always coherent). Chunks are embedded with `text-embedding-004` and persisted via a `ChunkRepository` abstraction so eval and tests can swap in an in-memory fake without touching `pgvector`. The query path is two-stage: a cheap cosine pre-filter (`RAG_SIM_FLOOR=0.4`) drops the obvious misses before a single `text-embedding-004` query embedding goes through an HNSW retrieval; surviving chunks feed Gemini 2.5 Flash through an `LLMProvider.complete()` call; the answer plus the retrieved chunks then go through `LLMProvider.judge()` (a local OpenAI-API-compatible LLM, per the 2026-05-12 clarification — the Art IV.6 deviation tracked in Complexity Tracking below). The judge identifies the supporting sentence(s) so the API can return a tight 400-character quoted span per citation rather than the whole chunk. A minimal HTMX-on-FastAPI UI renders the answer + citations and visually distinguishes answered / refused / no-documents states. Every query carries a `trace_id` that propagates through retrieve → generate → judge → respond and into every JSON log line.

## Technical Context

**Language/Version**: Python 3.12 (unchanged from feature 001; constitution Art IV.1).

**Primary Dependencies (new in this feature)**:
- `google-genai` — Gemini File API (PDF extraction), `text-embedding-004` (embeddings), Gemini 2.5 Flash (generation). The official Google SDK; `google-generativeai` is the legacy name and is deprecated in favor of `google-genai`.
- `openai` v1+ — used purely as a transport for the local OpenAI-API-compatible grounding judge (LM Studio / Ollama / llama.cpp / vLLM). Configured via `GROUNDING_JUDGE_BASE_URL`; no calls to api.openai.com.
- `jinja2` — HTMX-on-FastAPI templating per Q1 clarification. Pinned directly to keep the install lean.
- `pypdf` — page-count enumeration before the per-page Gemini File API call. Used for **iteration**, not for OCR; Gemini does the actual extraction.
- `tiktoken` (or a small custom tokenizer wrapper) — token budgeting for the chunker. Gemini's tokenization is not byte-identical to OpenAI's but is close enough at the ~600-token target; a documented approximation is acceptable per spec FR-002.

**Storage**: Postgres 16 + pgvector with the schema from feature 001's `0001_init_vector_store.sql`. Migration **0002_query_path.sql** in this feature adds (a) `chunk.token_count INTEGER` for chunker bookkeeping, (b) an **HNSW index** on `chunk.embedding USING vector_cosine_ops` for the retrieval hot path, and (c) `source_document.file_hash TEXT UNIQUE` to detect re-ingests by content rather than filename (the boilerplate's data-model.md called this out as the ingest feature's responsibility).

**Testing**: Two-tier carried forward from feature 001. The unit tier covers the four constitutionally-mandated test categories (chunking boundaries, retrieval ranking, citation construction, refusal path) plus the empty-corpus path (FR-014). Hermetic by design: the `LLMProvider` and `ChunkRepository` interfaces let tests bypass Gemini / pgvector entirely. The integration tier (`RUN_INTEGRATION=1`) exercises the real `pgvector` HNSW retrieval and the real grounding-judge HTTP path against a stubbed local OpenAI server (a small test fixture, not LM Studio).

**Target Platform**: Linux containers on the developer's Docker Desktop / Docker Engine. The local grounding judge runs on the host machine; compose declares `host.docker.internal` so the `app` container can reach it on Linux as well as macOS/Windows.

**Project Type**: Single project, web service + companion CLI + SQL migrations + Jinja templates. The HTMX UI is **a route on the existing FastAPI service** (Q1 clarification), not a separate compose service.

**Performance Goals**: Spec SC-002: end-to-end query (typed-to-rendered) under 10 s on a warm stack. Spec SC-001: ingest of a ≤50-page PDF under 3 minutes. Both budgets are loose enough that no specific concurrency / batch-size targeting is required at this stage; embedding calls are batched at a documented batch size and the rest is straight-line async.

**Constraints**: One PDF at a time per constitution Art VII. No streaming responses. Async FastAPI handlers end-to-end — sync code in the request path is rejected at review. No secrets committed (feature 001 FR-014 carries forward as spec FR-027). The grounding judge endpoint MUST be configurable via env vars (spec FR-028).

**Scale/Scope**: One PDF, one tenant, single concurrent user (the demo reviewer). The HNSW index is sized for low thousands of chunks (the upper end of a single hand-curated PDF); index parameters (`m`, `ef_construction`, `ef_search`) use pgvector defaults — no tuning at this stage.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution: `Nymbl RAG Assessment Constitution` v1.0.2 (amended 2026-05-12 to repin Art IV.6 generation model from Gemini 2.0 Flash to Gemini 2.5 Flash after Google retired the 2.0 ID for new keys).

| Article | Title | Status | Evidence / Note |
|---------|-------|--------|-----------------|
| I | Grounding Is Non-Negotiable | **PASS** | Refusal path is two-tier: cosine pre-filter `RAG_SIM_FLOOR=0.4` short-circuits weakly-grounded queries before calling generation (Art I.2.a), and an LLM-as-judge entailment check (Art I.2.b) catches drift when retrieval succeeds. Spec FR-010 + FR-012 + FR-013's "answered ↔ ≥1 citation, refused ↔ 0 citations" invariant make refusal observable and testable. |
| II | Citations Carry Real Provenance | **PASS** | Page-bounded chunking guarantees `char_offset_start` / `char_offset_end` are always offsets into a single page's extracted text, not into a concatenated multi-page stream — so the citation a reviewer reads always lines up with the page they open. The schema's NOT-NULL constraints inherited from feature 001 make it structurally impossible to persist a chunk without provenance. Spec FR-008 + the 400-character quoted-span cap ensure the API response carries the verbatim text a reviewer can locate without re-extracting the PDF. |
| III | Evaluation Before Demo | N/A this feature | Eval harness is feature 003, by explicit deferral in the spec Overview. This feature defines the `evals/questions.jsonl` shape (so feature 003 can be written without renegotiating it) but does not run an eval. The `rag eval` CLI stub from feature 001 stays a stub. |
| IV | Stack Decisions Are Fixed | **PASS, with one declared deviation** | Python 3.12 + uv ✓ (carried). FastAPI + Pydantic v2 ✓. Postgres 16 + pgvector ✓. PDF extraction via Gemini File API ✓ (Art IV.4). Embeddings via Gemini `text-embedding-004` (768-dim, single model for ingest and query) ✓ (Art IV.5). Generation via Gemini 2.5 Flash ✓ (Art IV.6 first sentence, post v1.0.2 amendment). `docker compose` topology unchanged from feature 001 ✓ (Art IV.7). **Declared deviation, Art IV.6 second sentence**: the grounding judge runs on a local OpenAI-API-compatible LLM, not Gemini Pro. Justification recorded in spec.md (Assumptions → "Article IV.6 deviation") and in Complexity Tracking below. Deviation is per Art IV.8. |
| V | Developer Experience | **PASS** | `make up` is unchanged. Two previously-stub CLI commands move from "exit 2" to real implementations: `rag ingest <path>`, `rag query "<question>"`. `rag eval` stays a stub (still owned by feature 003). One new entry — `rag serve` — wraps uvicorn so the dispatch surface (`rag --help` / `make help`) lists every runtime; the Dockerfile CMD switches to `rag serve` so the entry point is uniform. `.env.example` already updated with `GROUNDING_JUDGE_*` keys during `/speckit-clarify` (FR-028). README updates documented in quickstart.md. |
| VI | Code Quality Floor | **PASS** | The four test categories Art VI.2 mandates (chunking boundaries, retrieval ranking, citation construction, refusal) ship with their owning code in this feature, not after. Type hints on public functions (Art VI.3) carried forward via existing `ruff` config (UP, BLE, RUF rules already configured in `pyproject.toml`). Structured logging extended: every query path log carries `trace_id` (Art VI.4), enabling end-to-end correlation in the demo. No bare `except` / no silent fallbacks remains enforced by `ruff`'s `BLE001`. |
| VII | Scope Discipline | **PASS** | Multi-document, auth, observability beyond logs, streaming, polished frontend explicitly out of scope per spec Assumptions. Stretch features (hybrid retrieval, reranker, table-aware chunking) deferred — HNSW is the only index added; BM25 / `tsvector` is not. The committed `data/sample.pdf` is a smoke-test fixture, not a corpus-coupled dependency. |
| VIII | The Demo Is the Product | **PASS** | This feature IS the demo path. Spec-kit artifacts continue under `specs/002-rag-query-and-ui/`. README will be updated to cover ingest + query flow + UI URL (FR-017). The slide deck (Art VIII.5) and 30-minute dry-run (Art VIII.6) remain submission-time tasks not in this feature's scope, but the demoable surface this feature lands is what those artifacts will narrate. |

**Gate result**: PASS — single declared deviation (Art IV.6 grounding-judge model) is justified inline per Art IV.8 and recorded in Complexity Tracking. All other articles pass without conditions. Article III is "N/A this feature" by explicit deferral, not by violation.

**Post-Phase-1 re-check (2026-05-12)**: Re-evaluated after `research.md`, `data-model.md`, `contracts/`, and `quickstart.md` were written. No new violations surfaced. Phase 1 strengthens Art I (R-016 added the `judge_no_supporting_spans` degenerate-verdict recovery, closing a potential "answered without citation" loophole that FR-013 implied but did not previously make impossible). The Art IV.6 deviation remains the single declared violation; its justification still holds against the Phase 1 design. Gate: still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/002-rag-query-and-ui/
├── plan.md              # This file
├── research.md          # Phase 0 — resolved decisions for this feature's layer
├── data-model.md        # Phase 1 — migration 0002 + token_count + HNSW + file_hash
├── quickstart.md        # Phase 1 — developer walkthrough (clone → ingest → query)
├── contracts/
│   ├── query.yaml       # OpenAPI for POST /query
│   ├── ui.md            # HTMX route surface (GET /, POST /ui/query)
│   ├── cli.md           # Updates feature 001's CLI contract — real commands + `rag serve`
│   └── eval-set.md      # `evals/questions.jsonl` schema (consumed by feature 003)
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # NOT created here — /speckit-tasks output
```

### Source Code (repository root)

Per the user's `/speckit-plan` input, exact file layout and module boundaries are intentionally **deferred to `/speckit-tasks`**. This feature adds:

- **Ingest pipeline**: per-page PDF extraction → page-bounded recursive character splitter → embedding batches → repository write.
- **Query pipeline**: query embedding → cosine pre-filter via `ChunkRepository.search` → generation through `LLMProvider.complete` → grounding via `LLMProvider.judge` → response assembly with citations.
- **Two provider implementations**: `GeminiProvider` (embedding + completion) and `OpenAICompatJudgeProvider` (grounding judge).
- **One repository implementation**: pgvector-backed `ChunkRepository` plus an in-memory fake for tests.
- **HTMX UI**: one Jinja2 base template, one query-form partial, two FastAPI routes (`GET /` for the page, `POST /ui/query` for the form submit returning rendered HTML).
- **CLI**: real `rag ingest <path>`, real `rag query "<question>"`, new `rag serve` wrapping `uvicorn`. `rag eval` stays a stub.
- **Migration `0002_query_path.sql`**: `chunk.token_count`, HNSW index, `source_document.file_hash`.
- **Sample PDF**: a single committed public-domain PDF at `data/sample.pdf` per FR-029.
- **Eval set scaffold**: `evals/questions.jsonl` shape documented in `contracts/eval-set.md`; the actual ≥10 hand-curated Q&A pairs are owned by feature 003.

**Structure Decision**: continues feature 001's single-project layout. Tasks own the concrete filenames and module boundaries within that layout.

## Complexity Tracking

> One declared violation. Justified per Art IV.8.
>
> *History note*: A second deviation (generation model bumped to
> `gemini-2.5-flash` because Google retired `gemini-2.5-flash` for new
> API keys on 2026-05-12) was recorded here briefly during implementation.
> It was resolved on 2026-05-12 by amending the constitution to v1.0.2,
> which pins Gemini 2.5 Flash directly. The runtime now matches Art IV.6
> literally; no live deviation remains on this axis.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| **Art IV.6 deviation** — grounding judge on a local OpenAI-API-compatible LLM rather than Gemini 2.5 Pro. | (a) Zero marginal cost per grounding call, so iterative tuning and demo dry-runs (Art VIII.6) don't incur a budget — the grounding judge is called on **every** query, doubling per-query API cost if both legs are paid. (b) Demonstrates the codebase handles multiple LLM backends behind a clean interface (`LLMProvider`), which is a senior-engineer pattern that a Gemini-only build can't show. (c) The *behavior* required by Art I.2.b (a post-generation entailment check that can block an answer) is unchanged — only the model behind the check moves. | Using Gemini Pro for the judge would (i) double per-query upstream cost and latency, (ii) couple the demo cost ceiling to a Gemini quota that the candidate doesn't control, (iii) prevent the `LLMProvider` abstraction from being demonstrably necessary (a Gemini-only build would land Gemini-coupled code, which is the wrong signal). The generator stays Gemini Flash per the constitution. |
