---

description: "Task list for 002-rag-query-and-ui"
---

# Tasks: RAG Query Path + Minimal UI

**Input**: Design documents in [specs/002-rag-query-and-ui/](.)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Tests are **required** by spec FR-025 (constitution Art VI.2's four categories — chunking boundaries, retrieval ranking, citation construction, refusal — plus the empty-corpus path from FR-014). Included throughout, not optional.

**Organization**: Grouped by user story per spec.md (US1 / US2 / US3 / US4). Each story is independently testable. US3 is the precondition for US1/US2; US1 ships the answered path; US2 layers refusal logic on top; US4 puts a browser UI in front.

## Format

`[ID] [P?] [Story?] Description with file path`

- **[P]**: Parallelizable — different files, no dependency on incomplete tasks in the same phase.
- **[Story]**: User story (US1/US2/US3/US4) the task belongs to. Setup, Foundational, and Polish phases carry no story label.

## Path Conventions

Single-project layout extending feature 001's. All paths are repo-relative from `RAGQuerySystem/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies, env, and supporting assets the rest of the work needs in place before any code change compiles.

- [X] T001 Update `pyproject.toml` runtime deps: add `google-genai>=0.3`, `openai>=1.50`, `jinja2>=3.1`, `pypdf>=4.0`, `tiktoken>=0.7`. Bump project description from "boilerplate (feature 001-rag-boilerplate)" to "Small RAG system — query path + minimal UI (feature 002)". Add `python-multipart>=0.0.9` (FastAPI form-encoded body parsing for `POST /ui/query`). Run `uv lock` and commit `uv.lock`.
- [X] T002 [P] Add per-file `ruff` ignores in `pyproject.toml` for `src/rag/ui/templates/**` (Jinja files aren't Python — but in case any helper scripts land near them) and confirm `B008` ignore for `src/rag/cli/**` from feature 001 still covers the new CLI subcommands.
- [X] T003 [P] Commit a small public-domain PDF at `data/sample.pdf` (≤5 MB, ≤50 pages — see FR-029). Recommend the U.S. Government's [Plain Language Action Plan](https://www.plainlanguage.gov/) or a Project Gutenberg book exported to PDF (e.g., a Sherlock Holmes short story collection). Add `data/README.md` naming the source, the license, and the date downloaded.
- [X] T004 [P] Create `evals/questions.jsonl` with two illustrative entries that match the schema pinned in [contracts/eval-set.md](./contracts/eval-set.md): one `factoid` referencing pages from the committed sample PDF, one `out_of_scope`. The real ≥10-entry set is feature 003's deliverable — this file just locks the format in.
- [X] T005 [P] Update `docker-compose.yml`: add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `app` service so the grounding-judge endpoint at `host.docker.internal` resolves on Linux too (quickstart.md "Linux host networking" note). Leave the `db` service unchanged.
- [X] T006 [P] Update `Makefile`: change `ingest` target body from `uv run rag ingest` (stub-passthrough) to `uv run rag ingest data/sample.pdf` so `make ingest` works out of the box per quickstart.md. Change `query` target to accept `QUESTION` env var: `uv run rag query "$$QUESTION"`. Add new `serve` target dispatching to `uv run rag serve`.
- [X] T007 Update `Dockerfile` CMD from `["uvicorn", "rag.api:app", "--host", "0.0.0.0", "--port", "8000"]` to `["rag", "serve", "--host", "0.0.0.0", "--port", "8000"]` so the container entry point goes through the same CLI surface developers use locally (plan.md → V evidence).

**Checkpoint**: Dependencies installed, sample PDF + eval scaffold committed, compose + Makefile + Dockerfile reflect feature 002's new entry points. `make lint` still passes — no new code yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration, config extensions, abstraction layer (Providers + Repository), trace-id helper, and shared response models. Every user story depends on what lands here.

**⚠️ CRITICAL**: No user-story task may begin until this phase is complete.

- [X] T008 Write `migrations/0002_query_path.sql` exactly per [data-model.md](./data-model.md) — `ALTER TABLE chunk ADD COLUMN token_count INTEGER CHECK (token_count IS NULL OR token_count > 0)`, `CREATE INDEX idx_chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops)`, `ALTER TABLE source_document ADD COLUMN file_hash TEXT` + `UNIQUE` constraint. Migration is picked up automatically by the runner from feature 001 (`src/rag/migrations.py`); no code changes needed there.
- [X] T009 [P] Extend `src/rag/config.py`: add fields `RAG_TOP_K: int = 5` (gt=0, le=20), `RAG_SIM_FLOOR: float = 0.4` (ge=0, le=1), `RAG_EMBED_BATCH: int = 32` (gt=0, le=100), `RAG_GEMINI_CONCURRENCY: int = 4` (gt=0, le=16), `RAG_QUOTED_SPAN_MAX: int = 400` (gt=0, le=1000), `RAG_QUESTION_MAX_LEN: int = 1000` (gt=0, le=10000), `GROUNDING_JUDGE_BASE_URL: str`, `GROUNDING_JUDGE_API_KEY: SecretStr` (min_length=1), `GROUNDING_JUDGE_MODEL: str` (min_length=1). All keys are env-driven, defaults match plan.md / research.md.
- [X] T010 [P] Implement `src/rag/trace.py`: `new_trace_id() -> str` returns `uuid.uuid4().hex`; `TRACE_LOG_KEY = "trace_id"` constant. Per-call kwarg propagation per R-019; do NOT introduce `ContextVar`.
- [X] T011 [P] Implement `src/rag/providers/__init__.py`: re-export `LLMProvider`, `Providers`, `JudgeVerdict`, `ChunkForJudging`, `UpstreamProviderError`. Implement `src/rag/providers/base.py`: `class LLMProvider(Protocol)` with `async embed`, `async complete`, `async judge` methods; dataclass `ChunkForJudging(passage_id: str, sentences: list[str])`; dataclass `JudgeVerdict(entailed: bool, supports: dict[str, list[int]], reason: str)`; exception `UpstreamProviderError(provider: str, cause: Exception)`. Per R-012.
- [X] T012 Implement `src/rag/providers/gemini.py`: `GeminiProvider` class implementing `LLMProvider`. `embed` calls Gemini's `text-embedding-004` endpoint (batched per `RAG_EMBED_BATCH`); `complete` calls Gemini 2.5 Flash; `judge` raises `NotImplementedError` (judges never run via Gemini in this build — Art IV.6 deviation per plan.md Complexity Tracking). Also expose `extract_page_text(pdf_bytes: bytes, page_number: int) -> str` — calls Gemini File API with the per-page prompt from R-010. Wrap any SDK exceptions in `UpstreamProviderError("gemini", exc)`. Reference: research R-017, R-010.
- [X] T013 [P] Implement `src/rag/providers/openai_compat.py`: `OpenAICompatJudgeProvider` implementing `LLMProvider`. `embed` and `complete` raise `NotImplementedError`. `judge` calls the configured `GROUNDING_JUDGE_*` endpoint via the `openai` SDK's `AsyncOpenAI` client with `response_format={"type": "json_object"}` and parses the JSON per R-015's contract. Wrap any SDK exceptions in `UpstreamProviderError("judge", exc)`. The judge prompt template lives in `src/rag/query/prompts.py` (T026).
- [X] T014 [P] Implement `src/rag/repositories/__init__.py` + `src/rag/repositories/base.py`: `class ChunkRepository(Protocol)` with `async add_chunks`, `async search`, `async get_by_id` methods; dataclasses `ChunkRecord(id, source_document_id, page_number, char_offset_start, char_offset_end, raw_text, token_count, embedding)`, `RetrievedChunk(record, similarity: float)`. Per R-013.
- [X] T015 [P] Implement `src/rag/repositories/pgvector.py`: `PgVectorChunkRepository(pool: AsyncConnectionPool)` implementing `ChunkRepository`. `add_chunks` does a batched `INSERT ... ON CONFLICT (source_document_id, page_number, char_offset_start, char_offset_end) DO NOTHING`. `search` runs `SELECT id, ..., 1 - (embedding <=> %s) AS similarity FROM chunk WHERE embedding IS NOT NULL ORDER BY embedding <=> %s LIMIT %s`, then filters the in-memory result by `similarity >= sim_floor` (per R-013 — keeps HNSW index in play). `get_by_id` is a straight PK lookup. Uses `pgvector.psycopg.register_vector_async` (already configured in `src/rag/db.py`).
- [X] T016 [P] Implement `src/rag/repositories/memory.py`: `InMemoryChunkRepository` implementing `ChunkRepository`. Stores `ChunkRecord` instances in a list; `add_chunks` skips on `(source_document_id, page_number, char_offset_start, char_offset_end)` collision; `search` computes cosine similarity in pure Python via `numpy` (already a transitive dep through pgvector) and returns the top-k above sim_floor. For tests + eval (R-013).
- [X] T017 [P] Implement `src/rag/query/responses.py`: Pydantic v2 response models matching [contracts/query.yaml](./contracts/query.yaml) exactly — `Citation` (chunk_id, source_document_id, page_number, quoted_span, truncated), `QueryAnswered` (status="answered", answer, citations: list[Citation] with `min_length=1`, model, trace_id), `QueryRefused` (status="refused", message, refusal_cause: Literal[...], model, trace_id; NO citations field), `QueryNoDocuments` (status="no_documents", message, trace_id), `QueryResponse = QueryAnswered | QueryRefused | QueryNoDocuments` discriminated union. `model_config = ConfigDict(extra="forbid")` on every model so FR-013's invariant ("refused MUST NOT include citations") is enforced at the type level.
- [X] T018 Extend `src/rag/lifespan.py`: after creating the pool, additionally instantiate `PgVectorChunkRepository(pool)` and the two providers (`GeminiProvider(settings)`, `OpenAICompatJudgeProvider(settings)`) and stash them on `app.state` as `chunk_repo`, `gemini`, `judge`. Keep the existing health-check wiring intact.

**Checkpoint**: Migration applies cleanly; `app.state` exposes a repository and both providers; abstraction surface is testable in isolation. `make up && curl /health` still returns 200 with `schema_version=0002_query_path.sql`.

---

## Phase 3: User Story 3 — Ingest a PDF Into the Vector Store (Priority: P1)

**Story goal**: Running `rag ingest data/sample.pdf` extracts every page via Gemini File API, splits into page-bounded chunks, embeds them, and persists with all Article II provenance fields populated. Re-running is a no-op.

**Independent test**: On an empty `chunk` table, run `uv run rag ingest data/sample.pdf`. After it completes, `SELECT count(*) FROM chunk` is > 0; every row has `source_document_id`, `page_number`, `char_offset_start`, `char_offset_end`, `raw_text`, `embedding` populated; running ingest again produces zero new rows and exit code 0. Spec acceptance scenarios US3.1, US3.2, US3.3.

### Tests for User Story 3

Write these first; verify they fail.

- [X] T019 [P] [US3] Write `tests/unit/test_chunker.py` covering the chunking-boundaries category (Art VI.2 + FR-025). Cases: (a) a single page that fits in one chunk → exactly one chunk with `char_offset_start=0`, `char_offset_end=len(text)`; (b) a page that needs two chunks → both chunks reference the same `page_number`, offsets are non-overlapping into the page-local text, the second chunk's start equals the first chunk's end minus the 80-token overlap (within tokenizer approximation), neither breaks mid-word; (c) a page with strong paragraph breaks → split lands on `\n\n`; (d) a multi-paragraph page with one long paragraph → falls through to sentence boundary; (e) a page with one long sentence → falls through to word boundary; (f) **never crosses pages**: two pages with extracted text input → chunker output has chunks for each page with their respective `page_number`, no chunk straddles. Use a hand-built `tiktoken` encoder fixture; assertions are about chunk count + page numbers + offsets, not exact token counts.
- [X] T020 [P] [US3] Write `tests/unit/test_ingest_pipeline.py`: parametrize with a stub `LLMProvider` that returns scripted page texts and embeddings, plus an `InMemoryChunkRepository`. Cases: (a) happy path with 2 pages → 1 `source_document` row, N chunks per the chunker, every chunk's embedding length = 768; (b) re-ingest with same file content (same sha256) → returns "already_done" without invoking the provider; (c) Gemini extraction raises on page 2 → no chunks persisted, no `source_document` row remains, the exception propagates as `UpstreamProviderError`; (d) non-PDF file path → raises `ValueError` with a message naming the file.

### Implementation for User Story 3

- [X] T021 [US3] Implement `src/rag/ingest/__init__.py` re-exporting the public ingest function. Implement `src/rag/ingest/pdf.py`: `enumerate_pages(pdf_bytes: bytes) -> int` returns page count via `pypdf.PdfReader`; `extract_pages_via_gemini(pdf_bytes, gemini: GeminiProvider, concurrency: int) -> list[tuple[int, str]]` issues bounded-concurrent calls to `gemini.extract_page_text` per R-010 (semaphore sized to `RAG_GEMINI_CONCURRENCY`); returns `[(page_number, text), ...]` in page order even though calls are concurrent.
- [X] T022 [US3] Implement `src/rag/ingest/chunker.py`: `chunk_pages(pages: list[tuple[int, str]], *, target_tokens: int = 600, overlap_tokens: int = 80) -> list[ChunkRecord]`. The function MUST be page-bounded — it processes each `(page_number, text)` independently and returns chunks tagged with that page number. Internally: `_recursive_split(text, target, overlap, separators=["\n\n", _SENTENCE_RE, " "])` recursively descends the separator list. Per R-011. `token_count` is computed via `tiktoken.get_encoding("cl100k_base")` and documented in the module docstring as a Gemini-tokenizer approximation.
- [X] T023 [US3] Implement `src/rag/ingest/pipeline.py`: `async def ingest_pdf(pdf_path: Path, *, gemini: GeminiProvider, repo: ChunkRepository, trace_id: str, log) -> IngestOutcome`. Steps: (1) read bytes; (2) sha256 the bytes → file_hash; (3) attempt to insert `source_document(file_hash, display_filename)` — if it raises a unique-constraint violation, return `IngestOutcome(status="already_done", ...)`; (4) `enumerate_pages` + `extract_pages_via_gemini`; (5) `chunk_pages`; (6) `gemini.embed` in batches of `RAG_EMBED_BATCH`; (7) `repo.add_chunks(chunks)` inside the same DB transaction as step 3 so a partial failure rolls everything back per spec FR-006. Emit a structured log line at each step with the `trace_id` per R-019 + spec FR-005.
- [X] T024 [US3] Replace `src/rag/cli/ingest.py`'s stub body with the real implementation: accept positional `PDF_PATH`, `--concurrency` option per [contracts/cli.md](./contracts/cli.md); resolve the path to absolute, fail with exit 1 if missing / not a PDF / unreadable (Typer error display, no traceback); construct providers + repo from `get_settings()` and a temporary pool (CLI does not share the FastAPI lifespan; use `make_pool` + `pool.open(wait=True)` and close at end); call `ingest_pdf`; print the outcome ("Ingested N chunks across M pages from <file>" or "Already ingested (file_hash=<hash>); 0 new chunks"). Exit 0 on success or already-done; exit 1 on any provider failure or input error.
- [X] T025 [US3] Add the `data/` directory to `.dockerignore` if not already excluded — sample PDF stays in the repo for `uv run` from the host, but is not copied into the container (the container ingests via `docker compose exec app uv run rag ingest /mnt/sample.pdf` patterns that the user mounts on demand). Update `docker-compose.yml` to mount `./data:/app/data:ro` on the `app` service so `make ingest` (which runs inside the container per Makefile target T006) finds the file.

**Checkpoint**: `make up && make ingest` ends with structured success log + ≥1 chunk row per page in the database. `make ingest` a second time logs `ingest_already_done` and exits 0. Acceptance scenarios US3.1, US3.2, US3.3 all green; US3.4 (resume after mid-flight failure) is verified by hand against the test from T020c.

---

## Phase 4: User Story 1 — Ask a Question, Receive a Grounded, Cited Answer (Priority: P1) 🎯 MVP

**Story goal**: `POST /query` with an in-scope question returns `status=answered`, a non-empty answer, and ≥1 citation with `page_number`, `chunk_id`, and a ≤400-char quoted span that appears verbatim on the cited page. `rag query "<q>"` calls the same path and prints a human-readable summary.

**Independent test**: With the sample PDF ingested (Phase 3 done), `curl -X POST localhost:8000/query -H 'Content-Type: application/json' -d '{"question":"<an in-scope question>"}'` returns 200 with the `QueryAnswered` shape; opening `data/sample.pdf` to the cited page locates the quoted span. Spec acceptance scenarios US1.1, US1.2, US1.4.

### Tests for User Story 1

- [X] T026 [P] [US1] Write `tests/unit/test_citation_construction.py` covering the citation-construction category (Art VI.2 + FR-025). Cases: (a) judge returns 2 supporting sentences from one passage → citation's `quoted_span` is the joined sentences, `truncated=false` when ≤400 chars; (b) judge returns sentences whose joined length > 400 chars → `quoted_span` truncated at the nearest word boundary with a trailing `…`, `truncated=true`; (c) judge returns `supports={passage_id: []}` for some passages → those citations are dropped from the response; (d) judge returns `entailed=true, supports={}` (degenerate) → response is converted to refused with `refusal_cause=judge_no_supporting_spans` per R-016.
- [X] T027 [P] [US1] Write `tests/unit/test_retrieval_ranking.py` covering the retrieval-ranking category (Art VI.2 + FR-025). Uses `InMemoryChunkRepository` populated with a small fixture corpus (chunks with hand-crafted embeddings whose cosine similarity to a fixture query is known). Cases: (a) top-k ordering is by descending cosine similarity; (b) chunks with `embedding=None` are excluded; (c) `sim_floor=0.4` filters below-threshold results; (d) k=5 returns at most 5 chunks even if 10 are above floor.
- [X] T028 [P] [US1] Write `tests/unit/test_query_pipeline.py` for the answered path: parametrize with stub providers (embedding returns a known vector, complete returns a fixed answer, judge returns `entailed=true` with supporting sentence indices) and `InMemoryChunkRepository`. Assert the resulting `QueryAnswered` has the expected answer, the expected citation list with the expected page numbers, and a populated `trace_id`. Assert the model name in the response equals the configured generation model.

### Implementation for User Story 1

- [X] T029 [US1] Implement `src/rag/query/prompts.py`: `GENERATION_SYSTEM` constant (string), `build_generation_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str` formats the chunks as numbered passages with explicit page-number labels and instructs Gemini Flash to draw only from the labeled passages. `JUDGE_SYSTEM` constant per R-015. `build_judge_user_prompt(question: str, answer: str, passages: list[ChunkForJudging]) -> str` formats sentences as enumerated lists per passage. All templates are constants in source — no runtime editing.
- [X] T030 [US1] Implement `src/rag/query/citations.py`: `build_citations(judge_verdict: JudgeVerdict, retrieved: list[RetrievedChunk], *, span_max: int) -> list[Citation]` per R-015 + R-016. For each retrieved chunk: look up the supports list from the verdict; if empty, drop the chunk; otherwise join the named sentences (using the same sentence splitter as the chunker, T022's `_SENTENCE_RE`), truncate at the nearest word boundary if over `span_max`, append `…` and set `truncated=True`. Return the list of citations.
- [X] T031 [US1] Implement `src/rag/query/pipeline.py`: `async def answer_question(question: str, *, repo: ChunkRepository, gemini: LLMProvider, judge: LLMProvider, settings: Settings, trace_id: str, log) -> QueryResponse`. Steps with logs at each: (1) validate question (non-empty after strip, length ≤ `RAG_QUESTION_MAX_LEN`, raise `ValueError` otherwise); (2) check corpus non-empty via `repo.search` of any zero vector with `sim_floor=0` and `k=1` — actually a cleaner approach: a dedicated `repo.has_any_chunks()` Protocol method (add to T014 if not already present); on empty → return `QueryNoDocuments`; (3) embed the question via `gemini.embed([question])`; (4) `repo.search(emb, k=settings.RAG_TOP_K, sim_floor=settings.RAG_SIM_FLOOR)`; (5) if zero chunks → return `QueryRefused(refusal_cause="low_similarity")` — sim-floor short-circuit per FR-010 (this branch is exercised by US2 tests, but the *plumbing* lives here); (6) build generation prompt, call `gemini.complete`, get the answer; (7) build judge prompt, call `judge.judge`; (8) if `entailed=False` → `QueryRefused(refusal_cause="failed_grounding_check")`; (9) `build_citations(...)`; if zero → `QueryRefused(refusal_cause="judge_no_supporting_spans")`; (10) return `QueryAnswered(answer, citations, model=settings.GENERATION_MODEL, trace_id)`. Catches `UpstreamProviderError` and re-raises with context for the API layer to translate to 503.

      *Note*: T031 implements ALL branches because they share a function. US1 verifies the answered branch; US2 verifies the three refused branches. Splitting the function would create a parallel-implementation footgun.
- [X] T032 [US1] Extend `src/rag/api.py`: add a `class QueryRequest(BaseModel)` matching [contracts/query.yaml](./contracts/query.yaml) (`question: str`, `top_k: int | None = None`). Add route `@app.post("/query", responses={...})` that generates `trace_id = new_trace_id()`, calls `answer_question(...)`, sets the `X-RAG-Trace-Id` header on the response, and returns the `QueryResponse`. On `ValueError` from the pipeline → 400 with the `Error` shape. On `UpstreamProviderError` → 503 with `error="upstream_<provider.name>"`. Both error responses still carry the `trace_id`. Keep the existing `/health` route untouched.
- [X] T033 [US1] Replace `src/rag/cli/query.py`'s stub body: accept positional `QUESTION` and `--top-k`/`--json` options per [contracts/cli.md](./contracts/cli.md). Same lifecycle as `rag ingest` — open a pool, build providers + repo, call `answer_question`, print the human-readable summary (or `--json` raw response). Exit 0 regardless of `status` (refused / no_documents are not CLI errors); exit 1 only on validation error or `UpstreamProviderError`.

**Checkpoint**: `POST /query` with an in-scope question returns the answered payload. `rag query "..."` works from the terminal. Acceptance scenarios US1.1, US1.2, US1.4 all green. US1.3 (empty corpus) is verified in Phase 5 alongside the other "non-answered" branches.

---

## Phase 5: User Story 2 — Refuse Out-of-Scope Questions (Priority: P1)

**Story goal**: Questions whose answer is not in the PDF return `status=refused` with no citations. Three causes are observable: `low_similarity` (no chunks clear the sim floor), `failed_grounding_check` (judge says not entailed), `judge_no_supporting_spans` (judge says entailed but points nowhere). The empty-corpus case from US1's acceptance scenario 3 is also covered here as it shares the same response-type discriminator.

**Independent test**: After `make ingest`, issue queries that exercise each refusal cause (an out-of-domain question for `low_similarity`; a paraphrased-but-wrong question for `failed_grounding_check`; a degenerate-judge case can be exercised via the integration test's stub judge). Each returns `status=refused` with the matching `refusal_cause`, no citations, and a structured log line naming the cause. Spec acceptance scenarios US2.1, US2.2, US2.3, US1.3.

### Tests for User Story 2

- [X] T034 [P] [US2] Write `tests/unit/test_refusal.py` covering the refusal-path category (Art VI.2 + FR-025) plus the empty-corpus path (FR-014 → spec acceptance scenario US1.3). Parametrize over the three refusal causes plus the no-documents case using stub providers and `InMemoryChunkRepository`. Cases: (a) empty corpus → `QueryNoDocuments` with the ingest-command hint in `message`; (b) corpus populated but `repo.search` returns zero results above `sim_floor` → `QueryRefused(refusal_cause="low_similarity")` and generation is NEVER called (assert the stub `complete` was not invoked); (c) chunks retrieved but judge returns `entailed=false` → `QueryRefused(refusal_cause="failed_grounding_check")`; (d) judge returns `entailed=true, supports={}` → `QueryRefused(refusal_cause="judge_no_supporting_spans")`. Assert no citations field exists on any refused response (FR-013 + extra="forbid" on the model from T017).
- [X] T035 [P] [US2] Write `tests/integration/test_query_live.py` marked `@pytest.mark.integration`: hits a running stack (the test fixture spins up a stub OpenAI-compat HTTP server returning scripted JSON for the judge — small fixture, not LM Studio). Cases: (1) ingest fixture PDF + query in-scope → 200 + answered; (2) query before ingest → 200 + no_documents; (3) out-of-scope question → 200 + refused with `refusal_cause=low_similarity` (assuming the sim_floor=0.4 default catches it); (4) trace_id round-trip: response header `X-RAG-Trace-Id` matches body `trace_id` matches the `trace_id` in the logs (asserted by `make logs` shell-out within the test — acceptable here because the test is already gated behind `RUN_INTEGRATION`).

### Implementation for User Story 2

US2's *implementation* is the union of branches already wired in T031 (sim_floor short-circuit, judge-entailed-false, judge-no-supporting-spans). What this phase ships is **proof that those branches behave correctly** plus the empty-corpus pathway's surface polish.

- [X] T036 [US2] Add `async has_any_chunks(self) -> bool` to `ChunkRepository` Protocol (T014), and implement on `PgVectorChunkRepository` (`SELECT 1 FROM chunk LIMIT 1`) and `InMemoryChunkRepository` (returns `len(self._chunks) > 0`). Wire into `answer_question` (T031 step 2). Without this, the empty-corpus check would be a hack (sim_floor=0 with k=1), and the cause classification would be ambiguous.
- [X] T037 [US2] Add the message texts as module-level constants in `src/rag/query/responses.py`: `REFUSAL_MESSAGE_LOW_SIMILARITY`, `REFUSAL_MESSAGE_FAILED_GROUNDING`, `REFUSAL_MESSAGE_JUDGE_NO_SPANS`, `NO_DOCUMENTS_MESSAGE` (the last must name `rag ingest <path>` per FR-014). The `answer_question` pipeline (T031) reads these when building refused / no_documents responses, so the messages are one source of truth across JSON API, CLI, and UI templates.
- [X] T038 [US2] Wire the refusal-cause log fields into `src/rag/query/pipeline.py` per spec FR-015: every refused / no_documents return path emits a JSON log at INFO with fields `{event: "query_refused" | "query_no_documents", refusal_cause: ..., trace_id: ..., top_chunk_similarities: [...]}` (top similarities included on `low_similarity` refusals for debug visibility).

**Checkpoint**: All three refusal causes are demonstrable via curl + `make logs | Select-String trace_id`. Acceptance scenarios US2.1, US2.2, US2.3, and US1.3 (empty corpus) all green.

---

## Phase 6: User Story 4 — Ask Questions Through a Minimal Web UI (Priority: P2)

**Story goal**: Opening `http://localhost:8000/` in a browser shows a question form. Submitting issues an HTMX-swap to a response area showing the answer + citations, or a visually-distinct refusal / no-documents card.

**Independent test**: With the stack up and PDF ingested, open `/` in a browser, type an in-scope question, submit → answer + citations swap in. Type an out-of-scope question, submit → refusal card swaps in, visually distinct. Drop the corpus, query → no-documents card, visually distinct from refusal. Spec acceptance scenarios US4.1, US4.2, US4.3, US4.4.

### Tests for User Story 4

- [X] T039 [P] [US4] Write `tests/unit/test_ui_routes.py`: build the FastAPI app with stubbed `answer_question` (monkeypatch). Cases: (a) `GET /` returns 200 with `Content-Type: text/html`; body contains the `<form>` element with `hx-post="/ui/query"`, the `#response` div, and the `#thinking` indicator; (b) `POST /ui/query` with form data and a stub returning `QueryAnswered` returns 200 HTML containing the answer text, a `<ul class="citations">`, and the `status-answered` CSS class; (c) refused stub → HTML with `status-refused` and no `<ul class="citations">`; (d) no_documents stub → HTML with `status-empty` and the ingest command in `<code>`; (e) the trace_id HTML comment is present in every partial.

### Implementation for User Story 4

- [X] T040 [P] [US4] Create `src/rag/ui/templates/base.html`: minimal HTML5 doc, one `<link rel="stylesheet" href="/ui/static/styles.css">`, one `<script src="https://unpkg.com/htmx.org@2.0.3" integrity="<SRI hash>" crossorigin="anonymous"></script>` (use the official SRI from htmx.org's release notes), `<form>` with `<textarea name="question" maxlength="1000" required>`, submit button, `<div id="response"></div>`, `<span id="thinking" class="htmx-indicator">Thinking…</span>`. HTMX attributes on the form: `hx-post="/ui/query"`, `hx-target="#response"`, `hx-swap="innerHTML"`, `hx-indicator="#thinking"`. Per [contracts/ui.md](./contracts/ui.md).
- [X] T041 [P] [US4] Create `src/rag/ui/templates/_answered.html`: `<div class="status-answered">` with `<p class="answer">{{ response.answer }}</p>` and `<ul class="citations">` of `<li>` items per citation, each with `<span class="page-badge">p. {{ c.page_number }}</span><blockquote>{{ c.quoted_span }}</blockquote><small class="chunk-id">{{ c.chunk_id }}</small>`. Trailing `<!-- trace_id: {{ response.trace_id }} -->`.
- [X] T042 [P] [US4] Create `src/rag/ui/templates/_refused.html`: `<div class="status-refused">` with a `<span class="badge badge-refused">Not in document</span>` and `<p>{{ response.message }}</p>`. No citation block. Trailing trace_id comment.
- [X] T043 [P] [US4] Create `src/rag/ui/templates/_no_documents.html`: `<div class="status-empty">` with a `<span class="badge badge-empty">Empty corpus</span>`, `<p>{{ response.message }}</p>`, and `<pre><code>rag ingest data/sample.pdf</code></pre>`. Trailing trace_id comment.
- [X] T044 [P] [US4] Create `src/rag/ui/templates/_error.html`: `<div class="status-error">` for 400/503 cases — shows the error code (`{{ error.error }}`), short message, and trace_id comment.
- [X] T045 [P] [US4] Create `src/rag/ui/static/styles.css`: ~50 lines, plain CSS, no framework. Distinct visual treatment for `.status-answered`, `.status-refused`, `.status-empty`, `.status-error` (different left-border colors + badge backgrounds suffice). Style `.citations` as a vertical list with adequate spacing for readable quoted spans. No theming or dark mode (out of scope).
- [X] T046 [US4] Implement `src/rag/ui/__init__.py` + `src/rag/ui/routes.py`: register a Jinja2 `Templates` instance pointing at `src/rag/ui/templates/`; mount `src/rag/ui/static/` as a `StaticFiles` route at `/ui/static`. Two routes: `GET /` calls `templates.TemplateResponse("base.html", ...)`; `POST /ui/query` accepts `Form(...)` `question`, generates a `trace_id`, calls `answer_question(...)` exactly as the JSON endpoint does, renders the right partial template based on `response.status` (`_answered.html` / `_refused.html` / `_no_documents.html`), or on `ValueError` / `UpstreamProviderError` renders `_error.html` with the matching HTTP status. Per [contracts/ui.md](./contracts/ui.md) + R-018.
- [X] T047 [US4] Wire `src/rag/ui/routes.py` into `src/rag/api.py` by calling `app.include_router(ui_router)` after the existing route definitions. Confirm both `/` (HTML) and `/query` (JSON) coexist without route ordering issues.

**Checkpoint**: Browser at `http://localhost:8000/` renders the form, submits queries, and shows visually distinct response cards. Acceptance scenarios US4.1, US4.2, US4.3, US4.4 all green.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, sample data verification, hardening — the trim work that lifts the feature from "passes tests" to "demo-ready."

- [X] T048 [P] Update `README.md`: add a "Query the system" section after the existing boilerplate stand-up section. Document the ingest command, the UI URL, the `rag query "..."` CLI alternative, and a one-line note that the grounding judge uses a local OpenAI-API-compatible LLM (pointer to quickstart.md for setup details). Update the "Scripted commands" listing to reflect `rag ingest`/`rag query`/`rag serve` being real and `rag eval` still a stub.
- [X] T049 [P] Update `README.md` "Known limitations" section: name the Art IV.6 deviation explicitly (grounding judge runs on a local LLM, not Gemini Pro), one paragraph on why this is a deliberate choice, pointer to plan.md Complexity Tracking.
- [X] T050 [P] Add `tests/unit/test_providers_gemini.py` and `tests/unit/test_providers_openai_compat.py`: provider-level unit tests using SDK mocking (monkeypatch the `genai.Client` and `AsyncOpenAI` constructors). Cases per provider: (a) the success path produces the expected `LLMProvider` return type; (b) SDK exceptions are wrapped in `UpstreamProviderError` with the correct `provider` field; (c) the `judge` method's JSON parsing correctly handles malformed JSON by raising `UpstreamProviderError` (not a refusal — FR-016 invariant).
- [X] T051 Run `make lint` and fix any violations introduced by Phase 1-6 code. The boilerplate's `ruff` config (UP, BLE, RUF, SIM, I, E, F, W, B) catches the typical regressions; pay special attention to `BLE001` (no bare excepts) in the provider wrappers — every `except Exception as exc` MUST be a typed `raise UpstreamProviderError(...) from exc`.
- [X] T052 Run `make test` and confirm all unit tests pass on a fresh checkout (SC-002 / Art VI.2 / FR-025 acceptance).
- [ ] T053 Run the quickstart.md flow end-to-end on a developer machine: clone (or `git status` clean), `cp .env.example .env`, fill `GEMINI_API_KEY`, start a local LLM server (LM Studio with default port works), `make up`, `make ingest`, open browser, ask 3 in-scope questions and 3 out-of-scope questions — verify each renders correctly and the citations open the PDF to verifiable spans. Captures SC-001 (ingest ≤ 3 min), SC-002 (query ≤ 10 s), SC-003 (out-of-scope 100% refuse), SC-004 (citations verify), SC-006 (clone-to-answer ≤ 10 min), SC-007 (visual states).
- [ ] T054 Run `make test-integration` against the stack from T053 and confirm green.

**Checkpoint**: Feature 002 ships. Demo-ready. Eval harness (feature 003) is unblocked.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion. BLOCKS every user story.
- **US3 — Ingest (Phase 3)**: Depends on Foundational. Precondition for testing US1 and US2 against real data.
- **US1 — Answered query (Phase 4)**: Depends on Foundational. *Functionally* requires US3 to test live, but US1's unit tests use `InMemoryChunkRepository` with seeded fixtures — so the implementation phases can interleave.
- **US2 — Refusal (Phase 5)**: Depends on Foundational + US1's pipeline scaffold (T031 ships the branches; T034–T038 verify them). Sharing T031 is the *point* — refusal lives in the same function as answered, and "splitting the pipeline" would be a parallel-implementation footgun.
- **US4 — UI (Phase 6)**: Depends on US1 + US2 (the JSON API is what `POST /ui/query` ultimately wraps).
- **Polish (Phase 7)**: Depends on all user-story phases complete.

### Within Each User Story

Tests before implementation. Models before services. Services before endpoints. Story complete before the next priority starts.

### Parallel Opportunities

- **Phase 1 [P] tasks**: T002, T003, T004, T005, T006 can land in parallel (different files).
- **Phase 2 [P] tasks**: T009, T010, T011, T013, T014, T015, T016, T017 can run in parallel after T008 (migration) lands. T012 (GeminiProvider) needs T011 (base Protocol). T018 (lifespan extension) waits on all providers + repos.
- **Phase 3 tests** (T019, T020) can be authored in parallel; implementation tasks T021, T022 are different files [P]; T023 (ingest pipeline) needs both; T024 (CLI) needs T023.
- **Phase 4 tests** (T026, T027, T028) are different files [P]; implementation T029, T030 are different files [P]; T031 needs both plus T036 from Phase 5 (sequencing note: T036 is in Phase 5 numerically but lands before T031 chronologically — see "Sequencing note" below).
- **Phase 6 templates** (T040–T045) are all different files [P].
- **Phase 7 polish tasks** (T048, T049, T050) are independent docs / new test files [P].

### Sequencing note — T036 lands before T031

T036 (the `has_any_chunks` Protocol addition) is listed in Phase 5 because it's exercised by US2's empty-corpus test (T034 case a). However, T031 (Phase 4's pipeline) imports it. **Implementation order**: T036 ships first, then T031. This is intentional — the *story phase* is about which story's tests prove the work, not which code module the work lives in. If working sequentially, treat T036 as part of Phase 4's prep; the phase label exists for traceability, not for blocking ordering inside Foundational+US3+US1+US2.

---

## Parallel Example: Phase 2 (Foundational)

After T008 (migration) lands:

```text
# Different files, no shared imports → run in parallel:
Task: T009 — Extend src/rag/config.py with new env-driven fields
Task: T010 — Implement src/rag/trace.py
Task: T011 — Implement src/rag/providers/__init__.py + base.py
Task: T013 — Implement src/rag/providers/openai_compat.py
Task: T014 — Implement src/rag/repositories/__init__.py + base.py
Task: T017 — Implement src/rag/query/responses.py

# Sequential within the providers / repos groups:
Task: T012 — GeminiProvider (depends on T011's Protocol)
Task: T015 — PgVectorChunkRepository (depends on T014's Protocol)
Task: T016 — InMemoryChunkRepository (depends on T014's Protocol)

# Last in the phase:
Task: T018 — Extend lifespan to wire everything onto app.state
```

---

## Implementation Strategy

### MVP First (US3 + US1)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories).
3. Complete Phase 3: US3 (Ingest). Verify by `make ingest && SELECT count(*) FROM chunk > 0`.
4. Complete Phase 4: US1 (Answered path). Verify by `curl POST /query` with an in-scope question.
5. **STOP and VALIDATE**: This pair of stories is a demoable slice if needed. Refusal works narrowly through the pipeline's branches; the *unit-test coverage* of those branches is what Phase 5 adds.

### Incremental Delivery

- Phase 1 + 2 + 3 → ingest works → can run eval (feature 003) against retrieval alone.
- + Phase 4 → JSON API answers questions with citations.
- + Phase 5 → refusal is observable + tested across all three causes.
- + Phase 6 → browser UI.
- + Phase 7 → README + integration + e2e walkthrough.

Each increment is a clean commit boundary.

### Parallel Team Strategy

Solo build, but the [P] markers identify the natural points where work can interleave when iterating in a single context window.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in the same phase.
- [Story] label maps task to a user story for spec-traceability; phases are organized in priority order, but the labels are what the spec's acceptance scenarios point at.
- The four required test categories from Art VI.2 land in: T019 (chunking), T027 (retrieval ranking), T026 (citation construction), T034 (refusal). Plus T034 case (a) covers the empty-corpus path from FR-014.
- Verify each test fails before its implementation tasks land.
- Commit at every `**Checkpoint**` boundary; feature 001 set the precedent of clean, narratable commit history (Art VIII.2).
- Avoid: cross-story dependencies that break independence; same-file conflicts on `src/rag/api.py` and `src/rag/cli/main.py` (multiple tasks touch them — sequence by phase).
