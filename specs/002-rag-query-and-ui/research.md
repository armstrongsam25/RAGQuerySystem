# Phase 0 Research: RAG Query Path + Minimal UI

**Feature**: [002-rag-query-and-ui](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-05-12

## Purpose

The spec and the user's `/speckit-plan` input together pin the high-level architecture (page-bounded chunking, two-tier refusal gate, `LLMProvider` + `ChunkRepository` abstractions, HNSW retrieval, HTMX UI, JSON logs with `trace_id`). Phase 0 resolves the **inside-each-decision** questions a senior engineer still has to answer before tasks can be enumerated — chunker boundaries, judge-prompt shape, async coordination between two SDKs, HNSW parameter defaults, eval-set schema. Each decision below names the spec FR or constitution article it serves and stops there; the spec and constitution are not re-narrated.

---

## R-010 — Page-by-page extraction via Gemini File API

**Decision**: Use `pypdf` to enumerate page count, then render each page to a temporary single-page PDF (or page-image) in-process and call the Gemini File API once per page with the prompt "Return the plaintext content of this page exactly as it appears in reading order. Do not summarize, do not infer, do not add headings or formatting that are not in the source." Store `{page_number, extracted_text}` tuples in memory; chunking runs over those.

**Rationale**:
- Single-page calls keep page identity intact at the API boundary — the response *is* page N's text, no parsing of "Page 1: …\nPage 2: …" delimiters from a multi-page response. That parsing is the kind of code that fails silently on edge cases (footers that look like page numbers, hyphenated word breaks across pages) and the failure shows up as Article II citation drift.
- The Gemini File API is documented to accept multi-page PDFs but the per-page guarantee on output ordering is weaker. Per-page calls trade slightly more network round-trips for a clean invariant: every byte we ingest has a page number we did not have to infer.
- Concurrency: page calls are independent and can be issued with bounded concurrency (e.g., `asyncio.Semaphore(4)`) so a 50-page PDF doesn't take 50 × per-call latency. Bounded so we don't trip Gemini rate limits on a free tier.

**Alternatives considered**:
- **Single multi-page Gemini call, parse a structured response (JSON with `pages: [{n, text}]`)**: requires trusting the model to honor an output schema across pages; cheaper in API calls; rejected because schema drift is exactly the silent failure mode that compromises Art II. The 50-page extra-round-trip cost is acceptable inside the 3-minute SC-001 budget.
- **Local PDF text extraction (`pypdf.extract_text`) with Gemini used only as a fallback for image-heavy pages**: constitution Art IV.4 names Gemini File API as the extractor; "handles scanned/image pages without bolting on OCR" is the explicit reason. Adding `pypdf` as the primary path and Gemini as fallback would invert that and re-introduce the OCR-bolting problem on the first scanned PDF.
- **PyMuPDF / `pdfplumber`**: faster but Art IV.4 again — choosing it would be a constitution conflict and would have to be flagged before proceeding.

**Conflict check**: none. Constitution Art IV.4 satisfied; `pypdf` is used purely for page enumeration (counting and rendering), not for text extraction.

---

## R-011 — Page-bounded recursive character splitting

**Decision**: Each page's extracted text is independently split into chunks of ~600 tokens with ~80 token overlap. **Chunks never cross page boundaries** — this is the load-bearing invariant for Art II. Token count is computed via `tiktoken` (`cl100k_base` encoder as a stand-in for Gemini's tokenizer; documented approximation, see "Conflict check" below). Split priority within a page: paragraph break (`\n\n`) → sentence boundary (regex `(?<=[.!?])\s+(?=[A-Z])` as a serviceable approximation) → word boundary (whitespace). Recursive: if a candidate split is still over budget, retry with the next-finer separator. Each persisted chunk row carries `source_document_id`, `page_number`, `char_offset_start`, `char_offset_end`, `token_count`, `raw_text`.

**Rationale**:
- The page-boundary rule converts "which page does this chunk cite?" from a question into a column. The schema's `page_number` is set unambiguously per chunk, and `char_offset_start` / `char_offset_end` are offsets **into that page's extracted text**, not into a concatenated document — so a reviewer can deterministically locate the span on the source page (spec FR-002, SC-004, Art II).
- 600 tokens / 80 overlap is a defensible default for single-page PDFs at typical density: large enough to carry a complete idea (multi-sentence definitions, numbered steps), small enough that 5 chunks of context (top-k=5) fit comfortably inside Gemini 2.5 Flash's input budget alongside system + question.
- Priority order (paragraph → sentence → word) means most chunks end at semantically clean boundaries; only pathological pages (one long unbroken paragraph) fall through to word-boundary splits. Falling all the way through to character-level split is intentionally not allowed — a chunk that breaks mid-word is unacceptable for citation display (a reviewer reading "...the patient's heart ra" mid-quote is a credibility hit).

**Alternatives considered**:
- **Cross-page chunks of 600 tokens with page provenance computed per character**: would carry "primary page" + "secondary page" fields and complicate every downstream consumer. Rejected — Art II asks for a page, not a page interval, and the chunker side-steps the ambiguity by refusing to create one.
- **Fixed-size 512-token chunks**: simpler but produces uniformly bad sentence-break behavior on prose PDFs. Rejected; the recursive-separator approach is well-trodden (LangChain, LlamaIndex both default to similar logic).
- **Larger 1000-token chunks**: would reduce chunk count and improve recall per chunk but inflate prompt size and dilute Article II's "the quoted span fits on one screen" property. 600 stays the default; `RAG_CHUNK_TOKENS` is not exposed as a knob in this feature (tuning lives in a future eval-driven feature, not in the env surface a reviewer sees).

**Conflict check (tokenizer approximation)**: Gemini does not publish a `tiktoken`-compatible tokenizer; we approximate with `cl100k_base`. Empirically, `cl100k_base` and Gemini's tokenizer agree within ~10% on English prose. The chunker's 600-token target is therefore "600 ± ~60 tokens by Gemini's count," which is safely inside the model's input budget. This approximation is documented in the chunker's module docstring (a task-level concern) and called out in `data-model.md` so a future reviewer doesn't expect byte-identical accounting.

---

## R-012 — `LLMProvider` interface: one abstraction, two implementations

**Decision**: A single `LLMProvider` Protocol with two methods:
- `async embed(texts: list[str]) -> list[list[float]]` — used by ingest (batched) and query (single text).
- `async complete(system: str, user: str, *, model: str | None = None) -> str` — the answer generator. `model` argument allows the caller to override the default for a per-call decision.
- `async judge(question: str, answer: str, chunks: list[ChunkForJudging]) -> JudgeVerdict` — the entailment check. Returns a typed verdict: `entailed: bool`, `supporting_sentences: list[int]` (indices into the chunks), `reason: str` (short text, logged not surfaced).

Two implementations: `GeminiProvider` (covers `embed` via `text-embedding-004` and `complete` via Gemini 2.5 Flash; raises `NotImplementedError` on `judge` — judges are never run via Gemini in this build per the Art IV.6 deviation in plan.md), and `OpenAICompatJudgeProvider` (covers `judge` against the configured `GROUNDING_JUDGE_*` env vars; raises on `embed`/`complete`).

The DI layer assembles a `Providers` named-tuple of `(embedder, generator, judge)` pointing at whichever implementation owns each verb. Tests inject a `FakeProvider` that records calls and returns scripted responses.

**Rationale**:
- One Protocol with mode-specific raises is simpler than three Protocols (`Embedder`, `Generator`, `Judge`). The number of concrete implementations is small (2 today, maybe 3 if Gemini Pro is later wired for `judge`); the small risk of `NotImplementedError` is worth the cleaner DI surface.
- Returning `supporting_sentences: list[int]` from `judge` is what makes the 400-char quoted span (R-015) implementable without a second LLM call: the judge does double duty — gate + sentence picker.
- Per spec FR-016, upstream failures must surface, not mask. Each implementation raises a typed exception (`UpstreamProviderError`) that the request handler turns into an HTTP 503; refusals (spec FR-013) MUST come only from a clean `judge` verdict of `entailed=False`, never from a caught exception.

**Alternatives considered**:
- **Three separate Protocols** (`Embedder`, `Generator`, `Judge`): cleaner separation, but the DI registry duplicates code and tests have to mock three things instead of one. Marginal win, real cost.
- **Direct SDK calls everywhere with no abstraction**: rejected — eval (feature 003) and the test suite both want the same fake substitution, and threading a `use_real_gemini=False` flag through the call chain is the kind of pattern that turns into a maintenance footgun.

**Conflict check**: none. The abstraction is purely internal; the constitution does not forbid abstractions, only premature ones, and the second implementation (the judge) makes the abstraction concrete from day one.

---

## R-013 — `ChunkRepository` interface: pgvector behind a Protocol

**Decision**: A `ChunkRepository` Protocol with three methods:
- `async add_chunks(chunks: list[ChunkRecord]) -> None` — bulk insert, idempotent against the existing `UNIQUE (source_document_id, page_number, char_offset_start, char_offset_end)` constraint from feature 001 (`ON CONFLICT DO NOTHING`).
- `async search(query_embedding: list[float], *, k: int, sim_floor: float) -> list[RetrievedChunk]` — returns chunks above `sim_floor` ordered by cosine similarity descending, capped at `k`. May return fewer than `k`, or zero. Computed in a single SQL: `SELECT ..., 1 - (embedding <=> $1) AS similarity FROM chunk WHERE embedding IS NOT NULL ORDER BY embedding <=> $1 LIMIT $2`, then filter by similarity ≥ sim_floor in Python (the alternative — a SQL `WHERE` on a computed expression — disables the HNSW index for that query path).
- `async get_by_id(chunk_id: UUID) -> ChunkRecord | None` — for citation re-resolution on subsequent UI interactions if any (currently no UI feature uses it, but the eval harness will when reproducing a stored citation against a known chunk id).

Two implementations: `PgVectorChunkRepository` (production) and `InMemoryChunkRepository` (tests, eval).

**Rationale**:
- The "filter in Python after a LIMIT in SQL" pattern preserves HNSW index usage. HNSW is an ANN index; a `WHERE similarity > X` clause becomes a sequential scan after candidate retrieval and silently drops to O(n). The k=5 cap on the SQL side keeps the read narrow; in-Python filter on the small result set is cheap.
- Idempotent `add_chunks` via `ON CONFLICT DO NOTHING` satisfies spec FR-004 / FR-005 / SC-005 without requiring application-side dedup logic.
- An in-memory fake makes the four constitutionally-mandated test categories (Art VI.2) trivial: chunking tests don't need a database, retrieval-ranking tests can set up a fixture corpus in a list and assert ordering, refusal-path tests can return empty results.

**Alternatives considered**:
- **Direct psycopg calls inside ingest/query modules**: cheaper LOC, but eval and unit tests then need a real Postgres or a complex mock — and the four required test categories from Art VI.2 want easy substitution, not docker-compose-for-every-test.
- **An ORM (SQLAlchemy)**: rejected for the same reason feature 001's R-001 rejected it — the surface area we use (one bulk insert, one ranked query, one get-by-id) doesn't justify the abstraction.

**Conflict check**: none.

---

## R-014 — HNSW index parameters

**Decision**: Migration 0002 creates `CREATE INDEX idx_chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops);`. No explicit `m` / `ef_construction` overrides — pgvector defaults (`m=16`, `ef_construction=64`) are correct for our corpus size (low thousands of chunks). Query-time `ef_search` is left at the default (40) and not exposed via env. Index is created **after** any seed `add_chunks` calls run during initial ingest of `data/sample.pdf` if a setup task does that — but since ingest happens at runtime via the CLI and migrations apply at app startup, the index is in place before any chunks exist, which is the expected pgvector usage pattern.

**Rationale**:
- HNSW (not IVFFlat) per user input. IVFFlat needs a training step and recall degrades on small corpora; HNSW indexes immediately, has no training phase, and is the pgvector default recommendation for corpora under ~100k vectors.
- `vector_cosine_ops`: matches the cosine-similarity floor (`RAG_SIM_FLOOR=0.4`) and the `<=>` operator used in the search query. Using `vector_l2_ops` with a cosine threshold would silently misorder results.
- Defaults are tuned for our scale; tuning is a future-feature concern (and an eval-driven one — see feature 003).

**Alternatives considered**:
- **IVFFlat**: requires a training step on existing data; produces silently worse recall on small corpora until tuned. Rejected per user input + corpus-size argument.
- **Explicit `m=32` / `ef_construction=128` for higher recall**: marginal improvement on a corpus of low thousands, real index build/space cost. Defer until eval surfaces a need.

**Conflict check**: none. Constitution Art IV.3 pins `vector(768)`; HNSW indexes vectors of arbitrary fixed dimensionality.

---

## R-015 — Grounding judge prompt and sentence-selection contract

**Decision**: The judge prompt is a single system message of the form:
> "You are a grounding verifier. Given a question, a proposed answer, and a set of source passages, decide whether every factual claim in the answer is supported by at least one of the passages. For each passage, list the indices of sentences that support the answer (0-indexed within the passage). Respond as JSON: `{entailed: bool, supports: {passage_id: [sentence_idx, …]}, reason: short_string}`."

The user message contains the question, the answer, and the passages with passage ids and pre-split sentences (the judge does not re-split). Sentences are pre-split server-side by the same sentence regex used in the chunker (R-011), so the judge's indices line up 1:1 with what citation construction will quote.

**Rationale**:
- Returning sentence indices (not character offsets, not free-text quotes) makes the judge's output trivially parseable and verifiable: the server cross-checks each index is in range and constructs the 400-char quoted span by joining the named sentences and capping length (spec FR-008 + R-016 below).
- Pre-splitting sentences server-side keeps the judge's tokenizer assumptions irrelevant to the output schema. The model never has to "rewrite" the passage.
- JSON-mode responses are supported by every OpenAI-API-compatible server worth using (LM Studio, Ollama with `format: json`, vLLM with grammars, llama.cpp with grammar files). The implementation passes `response_format={"type": "json_object"}` and parses on the server. If the local model returns malformed JSON, the request fails as an upstream error per spec FR-016 — not as a refusal.
- `reason: short_string` is logged (with `trace_id`) but never surfaced to the UI: the UI's job is to show the refusal, not to debug the judge.

**Alternatives considered**:
- **Free-text quotes from the judge**: brittle (the judge can hallucinate quote marks; the server has to fuzzy-match back into the chunk). Rejected — indices are checkable.
- **Two separate judge calls**: one for entailed/not entailed, one for span selection. Rejected — doubles latency and cost for no signal gain.

**Conflict check**: none.

---

## R-016 — 400-char quoted-span construction

**Decision**: For an `entailed=True` verdict, the response builder constructs each citation's `quoted_span` by:
1. Joining the judge's named supporting sentences in order with single spaces.
2. If the joined string exceeds 400 chars, truncating to 400 chars at the nearest word boundary and appending `…` (one Unicode ellipsis).
3. If the judge returned no supporting indices for a given passage (the passage was retrieved but contributed nothing the judge could pin), the citation is **dropped** — answered responses MUST have ≥1 citation per spec FR-013, but they need not include every retrieved passage. The judge's sentence list is the citation-worthiness filter.

If after dropping the answered response would have zero citations (the judge returned `entailed=True` but listed no supporting sentences anywhere — a degenerate verdict), the server treats this as `failed_grounding_check`: refusal, logged, with `refusal_cause=judge_no_supporting_spans`. This closes the loophole where a confused judge could "yes-and" with no evidence.

**Rationale**:
- 400 chars is the spec's `quoted_span_max` (FR-008 + R-015). Truncate at word boundary so the UI never renders a mid-word break.
- Dropping unsupported retrieved passages is what makes the citation list trustworthy: a reviewer scanning citations sees only the chunks the judge actually pointed at, not every chunk that survived retrieval.
- The "judge said yes but pointed nowhere" recovery is a small but important corner — without it, a paranoid judge that returns `entailed=True, supports={}` could produce answered-without-citations responses, violating FR-013.

**Alternatives considered**:
- **Server-side sentence extraction without judge guidance** (e.g., highest-similarity sentence within the chunk): cheaper, but the picked sentence may not match what the answer actually drew on — and "what the answer drew on" is the only honest definition of a citation.
- **Always return the full chunk text capped at 400 chars**: simpler, but the citation often contains the answer-irrelevant remainder of the chunk, weakening the verifiability signal.

**Conflict check**: none.

---

## R-017 — Async coordination: psycopg async + Gemini SDK + openai SDK

**Decision**: All three SDKs operate inside the event loop:
- `psycopg` already async via `AsyncConnectionPool` in feature 001.
- `google-genai`: the SDK exposes `async` methods on its `AsyncClient`; use that path. Where only sync methods are available for a given Gemini surface (e.g., File API uploads in some SDK versions), wrap the sync call in `asyncio.to_thread` rather than blocking the loop.
- `openai`: the SDK has first-class `AsyncOpenAI` client; use it directly.

A bounded concurrency limit on Gemini calls (semaphore initialized to `RAG_GEMINI_CONCURRENCY`, default 4) prevents a 50-page ingest from issuing 50 simultaneous extractions and hitting rate limits. Embeddings during ingest are batched at `RAG_EMBED_BATCH=32` per Gemini's per-request limits.

**Rationale**:
- Async end-to-end was a user-input commitment ("Async FastAPI handlers end-to-end. Both Gemini and Postgres benefit from concurrency; sync code will bottleneck the demo"). The semaphore is the discipline that prevents "async means unlimited parallelism."
- `asyncio.to_thread` as a fallback for sync-only SDK methods is the standard escape hatch; documented inline where used so a future reader doesn't think it's a mistake.

**Alternatives considered**:
- **Sync handlers + thread pool**: gives up async's connection-pool concurrency advantages for psycopg. Rejected per user input.
- **No concurrency limit on Gemini calls**: faster on a free PDF, surfaces as a 429 storm on Gemini's rate-limited tier. Semaphore is cheap.

**Conflict check**: none.

---

## R-018 — HTMX + Jinja2 UI shape

**Decision**: Two routes on the existing FastAPI app:
- `GET /` — renders the base page (Jinja2 template) with an empty response area, the question input, and a submit button. Includes the htmx.org script via a single `<script>` tag with SRI.
- `POST /ui/query` — accepts the form-encoded question, calls the same query function the JSON `POST /query` endpoint uses, and renders a Jinja2 partial (`_response.html`) returning HTML — not JSON. HTMX swaps the partial into the response area via `hx-target` / `hx-swap`.

Three template variants in `_response.html` driven by the `status` field: `answered` (answer text + citations list), `refused` (refusal message with a "Not in the document" badge), `no_documents` (empty-corpus message with the ingest command quoted).

Templates use plain server-rendered HTML — no JS framework, no client-side state. The htmx attributes (`hx-post`, `hx-target`, `hx-indicator`) live in the base template; the `hx-indicator` points at a spinner element that HTMX shows during the in-flight period (spec FR-021).

**Rationale**:
- HTMX + Jinja is what Q1's clarification picked. Two routes is the minimum that satisfies "page + form submit" without inventing a JSON-then-render hop.
- The HTML-returning `POST /ui/query` is distinct from the JSON `POST /query` so the API contract stays clean: the JSON endpoint is for programmatic consumers (curl, eval harness), the HTML endpoint is for the browser. They share the query function below the surface.
- Visual distinction (FR-020) is implemented by template branching on `status`: each branch renders a different `<div class="status-...">` so a single CSS file styles them differently without conditional logic at render time.

**Alternatives considered**:
- **Single endpoint returning HTML or JSON via `Accept` header negotiation**: clever, but content negotiation in FastAPI requires per-route work and the two response shapes don't share validators. Rejected.
- **Client-side JS that hits `/query` and renders the response**: introduces a vanilla-JS layer with no server-side template, contradicting Q1's "Jinja templates" specifier.

**Conflict check**: none.

---

## R-019 — Trace ID propagation

**Decision**: Each query (CLI or HTTP, JSON or HTML route) generates a `trace_id` (`uuid4` hex) at the entry point and passes it as a keyword argument to every function in the query pipeline: `embed`, `repository.search`, `provider.complete`, `provider.judge`, response assembler. Every JSON log line in the path includes `trace_id`. The HTTP response includes the `trace_id` in a header (`X-RAG-Trace-Id`); the JSON response body includes it as a `trace_id` field; the HTMX response renders it as a small comment in the page footer for grep-from-the-demo.

`contextvars.ContextVar` is **not** used (despite being the more elegant async-safe option). Reasoning: a keyword argument is grep-able and visible at every call site; a ContextVar is invisible until you read the right module. For a demo-narratable codebase (Art VIII.2), explicitness wins.

**Rationale**:
- "Where did this answer come from?" is one of the questions a demo gets asked. A `trace_id` that links logs ↔ response ↔ judge verdict ↔ retrieved chunks turns "I'll have to dig" into "here's the line."
- The kwarg propagation is verbose but textbook — no surprises during code review.

**Alternatives considered**:
- **`contextvars.ContextVar`** — async-safe, less typing, but invisible to grep. Right answer for an observability layer, wrong answer for "I want to show a senior reviewer how the trace is built."
- **OpenTelemetry**: constitution Art VII explicitly puts "production observability (Prometheus, OpenTelemetry, etc.)" out of scope.

**Conflict check**: none. Constitution Art VII forbids prod-grade observability, not basic correlation IDs; structured JSON logs with `trace_id` are still stdlib `logging`.

---

## R-020 — Eval set shape (`evals/questions.jsonl`)

**Decision**: One JSON object per line, with fields:
- `id: string` (stable identifier, e.g., `q-001`)
- `question: string`
- `expected_answer: string | null` — `null` when the question is intentionally out-of-scope and the correct outcome is refusal.
- `expected_pages: list[int]` — page numbers of the supporting evidence. Empty list when `expected_answer` is null.
- `category: "factoid" | "synthesis" | "out_of_scope"` — matches constitution Art III.1's three categories.
- `notes: string | null` — free text for the eval author's bookkeeping (e.g., "tests numbered-list extraction across page break").

This file is **scaffolded** in feature 002 (an example `q-000-example.jsonl` line or two demonstrating the schema, committed at `evals/questions.jsonl`). The full ≥10 hand-curated set is feature 003's deliverable. Feature 002 lands the shape; feature 003 fills it.

**Rationale**:
- Defining the shape here lets feature 003 be written without renegotiating the schema. Schema drift between "what the eval expects" and "what the query path produces" is a slow-bleed defect; locking it in this feature prevents it.
- JSONL (not a single JSON array) so a partially-written file is still parseable line-by-line and so `git diff` reads cleanly when an eval is added.

**Alternatives considered**:
- **YAML or TOML**: nicer to author but loses streamability and forces a parser dep.
- **A SQL table for eval data**: overkill for a hand-curated set of 10–30 items.
- **Defer the schema to feature 003 entirely**: viable, but it's a 30-line decision and locking it now lets the `rag eval` stub from feature 001 stay coherent (it points at `evals/questions.jsonl` without ambiguity).

**Conflict check**: none. Constitution Art III names the categories; this schema enumerates them.

---

## Resolved NEEDS CLARIFICATION items

All technical-context fields in plan.md are concrete. No `NEEDS CLARIFICATION` markers remain. Phase 1 can proceed.
