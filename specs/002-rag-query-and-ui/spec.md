# Feature Specification: RAG Query Path + Minimal UI

**Feature Branch**: `002-rag-query-and-ui`
**Created**: 2026-05-12
**Status**: Draft
**Input**: User description: "Begin to build the backend stack and start creating the frontend"

## Overview

Turn the boilerplate from feature 001 into a working end-to-end RAG slice: ingest one PDF, retrieve relevant passages for a user's question, generate a grounded answer with verifiable citations, refuse when the question falls outside the document, and surface all of this through a minimal web UI plus an HTTP API.

This is the **demo-bearing feature**. After it lands, a reviewer on a fresh machine can run a single command to bring the stack up, run a single command to ingest the assessment PDF, open a URL in their browser, type a question, and see an answer accompanied by citations they can open the PDF to verify. The constitution's load-bearing articles (I — Grounding, II — Citations) become observable behavior, not promises in a schema.

Eval harness (Article III) is **not** in this feature; it is feature 003, which depends on the query path existing to score it. Hybrid retrieval, rerankers, and any frontend polish beyond a working chat-style form are also out of scope.

## Clarifications

### Session 2026-05-12

- Q: Frontend mechanism — Streamlit (third service), HTMX-in-FastAPI, or static SPA? → A: HTMX route(s) on the existing FastAPI app, server-rendered via Jinja2 templates. Two services total; UI logic lives in the same code path as the API.
- Q: Grounding-check entailment mechanism — LLM-as-judge, heuristic only, or hybrid? → A: LLM-as-judge against a **local OpenAI-API-compatible endpoint** (e.g., LM Studio / Ollama / llama.cpp server), configured via env vars. This is a deviation from Article IV.6 (which names Gemini Pro as the acceptable judge) — justified inline below per Article IV.8.
- Q: Demo PDF — committed to the repo, supplied separately, or both? → A: A small public-domain PDF is committed at `data/sample.pdf` for self-contained smoke-testing; the README documents how to swap in any other PDF via `rag ingest <path>` so the real assessment PDF can be the live demo target without re-shaping the codebase.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a Question, Receive a Grounded, Cited Answer (Priority: P1)

A reviewer with the stack running and the assessment PDF already ingested types a question whose answer is in the PDF (e.g., a definition, a stated fact, a numbered procedure). The system retrieves the most relevant passages, generates an answer that draws only from those passages, and returns the answer alongside a list of citations. Each citation names the page number and includes the verbatim text span the answer drew on. The reviewer can open the PDF to that page and see the quoted text.

**Why this priority**: This is the demo's moment of truth and the embodiment of Articles I and II of the constitution. If this path doesn't work, the hiring signal collapses regardless of how clean the boilerplate is. Every other story in this feature exists to make this one demonstrable.

**Independent Test**: With a PDF already ingested (precondition delivered by US3), issue a query for a fact known to be in the PDF through the HTTP API. Verify (a) the response contains an answer string, (b) the response contains at least one citation with a page number, chunk id, and quoted text span, (c) the quoted text appears verbatim on the named page of the source PDF.

**Acceptance Scenarios**:

1. **Given** the stack is up and the assessment PDF has been ingested, **When** the reviewer issues a query whose answer is stated explicitly in the PDF, **Then** the response includes (a) a non-empty answer, (b) a `status` of `answered`, and (c) at least one citation containing page number, stable chunk identifier, and a quoted text span ≤ the chunk length.
2. **Given** a returned citation, **When** a reviewer opens the source PDF to the cited page, **Then** the quoted text span appears verbatim on that page.
3. **Given** the stack is up but no PDF has been ingested yet, **When** the reviewer issues a query, **Then** the response is a clear "no documents available" message with a non-200 status and an actionable hint naming the ingest command — the system does not fabricate an answer.
4. **Given** the generation model is temporarily unreachable, **When** the reviewer issues a query, **Then** the API returns a 503 with an error payload naming the upstream failure, and the structured log records the failed call — the system does not retry indefinitely or return a partial answer.

---

### User Story 2 - Refuse Out-of-Scope Questions (Priority: P1)

A reviewer asks the system a question whose answer is **not** in the ingested PDF (e.g., a question about a different domain, a current-events question, or a question the PDF deliberately doesn't address). The system recognizes the gap and returns "I don't know" with no citations and no fabricated content. The reviewer cannot, by any phrasing of the question, coax a hallucinated answer out of the system on a topic the PDF doesn't cover.

**Why this priority**: Article I.3 of the constitution states "Hallucinations are treated as defects, not edge cases." The refusal path is what makes Articles I.1 and I.2 testable. Without a demonstrable refusal, "grounded" is unverifiable — any answer could be a coincidence. This story shares P1 with US1 because the demo's credibility rests on showing both: the system answers what it can and **refuses what it can't**.

**Independent Test**: With a PDF ingested, issue a query about a topic the PDF demonstrably does not cover. Verify the response has `status: refused`, an empty (or absent) citations list, and a refusal message — not a generic answer that happens to omit citations. Repeat with at least three differently-phrased out-of-scope questions to confirm the refusal is robust to surface rewording.

**Acceptance Scenarios**:

1. **Given** the assessment PDF has been ingested, **When** the reviewer asks a question on a topic the PDF does not address, **Then** the response has `status: refused`, no citations, and a message indicating the system does not have information to answer — and structured logs record the refusal cause (`low_similarity` or `failed_grounding_check`).
2. **Given** a question whose embedding retrieves chunks at similarity scores below the configured threshold, **When** the query is processed, **Then** the system refuses before invoking the generation model — saving a model call and avoiding the temptation to "fill in" from weakly-relevant context.
3. **Given** retrieval returns chunks above the threshold but the generated answer is not entailed by those chunks (e.g., the model drifted), **When** the post-generation grounding check runs, **Then** the system replaces the model's answer with the refusal response and records the grounding-check failure in logs.

---

### User Story 3 - Ingest a PDF Into the Vector Store (Priority: P1)

A developer (or the reviewer themselves) runs a single command naming a local PDF file. The system extracts the text page by page, splits it into provenance-carrying chunks (page number, character offsets, raw text), embeds each chunk, and persists the chunks into the vector store. The developer sees progress in structured logs and a clear success or failure message. Re-running the same command against the same PDF is a no-op — no duplicate chunks are created.

**Why this priority**: US1 and US2 are theoretical without a populated vector store. This story is the developer-facing precondition for the demo, and it's P1 because it must land in the same feature as the query path — splitting them would leave one or the other unmerged-able. The CLI stub from feature 001 (`rag ingest`) is the slot this story fills.

**Independent Test**: On a stack with an empty `chunk` table, run the ingest command against the assessment PDF. Verify (a) the command exits zero, (b) the `chunk` table contains rows with every provenance field populated (source_document_id, page_number, char_offset_start, char_offset_end, raw_text), (c) every chunk row has an embedding vector of the constitutionally-mandated dimensionality, and (d) re-running the same command produces zero new rows.

**Acceptance Scenarios**:

1. **Given** the stack is up and the `chunk` table is empty, **When** the developer runs the ingest command pointing at a valid PDF, **Then** the command exits zero, a `source_document` row is created, and `chunk` rows are persisted with all five Article II provenance fields populated and embedding vectors of the pinned dimensionality.
2. **Given** the same PDF has already been ingested, **When** the developer runs the ingest command again, **Then** no new chunk rows are created, the command exits zero, and the structured log records a "no new content" outcome rather than failing.
3. **Given** the developer runs ingest against a file that is missing, unreadable, or not a PDF, **When** the command runs, **Then** it exits non-zero with an actionable error message naming the file and the specific failure (not found, permission denied, unsupported type) — the system does not partially persist.
4. **Given** the upstream PDF-extraction service returns an error mid-ingest for one page, **When** ingest is in flight, **Then** the entire ingest run aborts cleanly (no half-written chunks), the error is logged with the page number and upstream error, and the command exits non-zero — re-running after the upstream recovers MUST resume without producing duplicates of previously-uningested pages or skipping pages.

---

### User Story 4 - Ask Questions Through a Minimal Web UI (Priority: P2)

A reviewer opens a browser to a URL printed by the `make up` output. They see a single page with a question input, a submit control, and an area for the response. They type a question, submit, and see the answer rendered alongside its citations (page number + quoted span for each). Refusals are visually distinct from answers so the reviewer can see at a glance whether the system answered or declined. The UI is intentionally plain — no styling system, no client-side state beyond the current question and response.

**Why this priority**: P2 because the HTTP API from US1 already satisfies the demo's core technical requirement (a reviewer can `curl` the endpoint and see the same payload). The UI exists to make the live-query portion of the 30-minute demo flow well (Article VIII.6) — typing in a browser is more demo-friendly than reading JSON. But if the UI somehow doesn't land, the demo can still be conducted from the terminal. P2 reflects that fallback availability, not unimportance.

**Independent Test**: With the stack up and a PDF ingested, open the documented UI URL in a browser. Type a question known to be in-scope and submit; verify the answer appears with at least one rendered citation showing page number and quoted span. Type a question known to be out of scope and submit; verify the response is visually distinguishable as a refusal (different color, label, or icon — the choice is implementation-level, but the distinction MUST be perceptible at a glance).

**Acceptance Scenarios**:

1. **Given** the stack is up and the URL of the UI is documented in the README, **When** the reviewer opens the URL in a modern browser, **Then** the page loads without console errors and displays a question input, a submit control, and an empty response area.
2. **Given** a query that yields an answered response, **When** the reviewer submits, **Then** the page renders the answer text and a list of citations, each citation displaying at minimum its page number and the quoted text span.
3. **Given** a query that yields a refused response, **When** the reviewer submits, **Then** the page renders the refusal message in a visually distinct way (different color, badge, or icon) and shows no citations.
4. **Given** a query in flight, **When** the reviewer submits and the response has not yet arrived, **Then** the page visibly indicates work-in-progress (spinner, disabled submit, or "Thinking..." text) — the user is never left wondering whether their submit registered.

---

### Edge Cases

- **Empty corpus**: A query before any PDF is ingested MUST return a clear "no documents ingested" response with an actionable hint (not a refusal, since the question may be perfectly valid — the system simply has no data). The UI MUST surface this state distinctly from a refusal.
- **Malformed/empty question**: An empty question, a question consisting only of whitespace, or a question exceeding a reasonable length cap MUST be rejected at the API boundary with HTTP 400 and a message naming the violation. The UI MUST disable the submit control while the input is empty.
- **PDF with no extractable text** (e.g., a corrupt or password-protected file): Ingest MUST exit non-zero with an actionable error naming the cause; the database MUST be left in a clean state (no partial `source_document` row, no orphaned chunks).
- **Re-ingestion mid-flight on the same PDF**: If a developer accidentally invokes ingest twice in parallel for the same file, the second invocation MUST detect the first is in progress (or detect that prior chunks for the same source exist) and either no-op or fail with a clear concurrency message — it MUST NOT silently double-write or corrupt the chunk table.
- **Question that retrieves chunks above threshold but is still ambiguous** (e.g., "what does it say?"): The system MUST attempt an answer; the grounding check is the safety net. Ambiguity at the question level is not the system's job to resolve.
- **Citation requested for a chunk whose `raw_text` is very long**: The API MUST cap the quoted span at a configured maximum length (with an indication if truncated) so a citation payload remains compact for the UI.
- **Upstream model rate limit or transient error during generation**: The API MUST return 503 with an error payload naming the failure; it MUST NOT mask the failure as a refusal (that would corrupt the grounding signal — a refusal must mean "I don't know," not "the model timed out").
- **Long question / very long answer**: A reasonable upper bound MUST exist for both (capped at submit time for questions; capped via prompt instructions and truncation for answers) so the UI never has to render a screen-filling response.

## Requirements *(mandatory)*

### Functional Requirements

#### Ingest

- **FR-001**: The system MUST accept a local PDF file path through the `rag ingest` CLI entry point (whose slot was created in feature 001) and produce a populated `source_document` row plus one or more `chunk` rows for that PDF.
- **FR-002**: Each persisted chunk MUST carry every Article II provenance field (source document id, page number, character offset start, character offset end, raw text) populated from the actual PDF content — none of these fields may be filled with placeholders, defaults, or zeros standing in for missing data.
- **FR-003**: Each persisted chunk MUST carry an embedding vector of the constitutionally-pinned dimensionality (matching the schema's `vector(768)` column). The embedding MUST be produced by the same embedding model that the query path uses, ensuring vectors are comparable.
- **FR-004**: Re-running ingest against a PDF whose chunks already exist MUST NOT create duplicate chunk rows. Detection MUST use stable identity (the existing UNIQUE constraint on source document + page + character offsets), not filename-only matching.
- **FR-005**: Ingest MUST emit structured log records for at minimum: ingest start (with file path and resolved source document id), per-page extraction completion (with page number and chunk count), embedding completion (with chunk count and model id), and ingest completion or failure (with outcome and elapsed time).
- **FR-006**: An ingest run that fails partway through MUST leave the database in a state where the same PDF can be re-ingested cleanly without duplicate chunks and without manual cleanup. The implementation MAY use a transactional boundary, a draft-then-promote scheme, or any other approach; the requirement is on the observable outcome, not the mechanism.

#### Query API

- **FR-007**: The system MUST expose an HTTP endpoint that accepts a question (string) in a JSON request body and returns a typed JSON response containing at minimum: a `status` field (`answered`, `refused`, or `no_documents`), an `answer` field (a string; empty or absent when refused or when no documents are ingested), a `citations` array (empty when refused or when no documents are ingested), and a `model` field identifying which generation model produced the answer.
- **FR-008**: Each citation in the response MUST include: a stable chunk identifier (matching the `chunk.id` in the schema), a source document identifier, a page number, and a quoted text span (a substring of the chunk's `raw_text`, capped at a configured maximum length, with truncation indication if the cap was applied).
- **FR-009**: Retrieval for the query MUST use vector similarity on the chunk embedding column, returning the top *k* chunks (where *k* is configurable via environment variable with a sensible default). Retrieval MUST exclude chunks whose embedding is NULL.
- **FR-010**: When the top retrieved chunks' similarity scores fall below a configured threshold (per constitution Article I.2.a), the system MUST short-circuit the generation step and return `status: refused` with a refusal message. The threshold MUST be configurable via environment variable.
- **FR-011**: When retrieval scores clear the threshold, the system MUST construct a generation prompt that includes the retrieved chunks as context and the user's question, and obtain a generated answer from the constitutionally-mandated generation model. The prompt template MUST be source-controlled, not runtime-editable, so a reviewer can read it.
- **FR-012**: After generation, the system MUST perform a grounding check that verifies the generated answer is entailed by the retrieved chunks (per constitution Article I.2.b). The check MUST be implemented as an **LLM-as-judge call** against a configurable OpenAI-API-compatible endpoint (see FR-028). If the judge determines the answer is not entailed, the system MUST replace the answer with the refusal response and record the grounding-check outcome (`entailed` / `not_entailed`) in structured logs.
- **FR-028**: The grounding judge's endpoint URL, API key, and model identifier MUST be configurable via environment variables, so the judge can run against a local OpenAI-API-compatible server (LM Studio, Ollama, llama.cpp, vLLM, etc.) without code changes. The judge endpoint MUST be reachable from inside the `app` container — if the judge runs on the developer's host machine, the docker compose configuration MUST establish the necessary networking (e.g., `host.docker.internal` resolution) so the README's stand-up command remains a single step.
- **FR-013**: Refused responses MUST NOT include citations. Answered responses MUST include at least one citation. (This invariant makes it impossible to surface a "grounded" answer with no traceable evidence.)
- **FR-014**: When no documents have been ingested at all, the query endpoint MUST return `status: no_documents` with an actionable hint naming the ingest command — distinct from a refusal, since the question may be valid and the corpus is simply empty.
- **FR-015**: The query endpoint MUST emit a structured log record per request including: the question (optionally truncated for log volume), the top-k retrieved chunk ids and their similarity scores, the generation model id, the outcome (`answered`, `refused`, or `no_documents`), the refusal cause when refused (`low_similarity`, `failed_grounding_check`, or `judge_no_supporting_spans`), and the end-to-end latency. (The `judge_no_supporting_spans` cause closes a degenerate-judge loophole — see Phase 1 research R-016 — where the entailment check returns `entailed=true` but identifies no supporting sentences; this MUST NOT silently become an answered response with zero citations.)
- **FR-016**: All upstream model failures (PDF extraction, embedding, generation, grounding check) MUST surface as actionable errors with HTTP status codes that distinguish client errors from upstream failures. The system MUST NOT mask an upstream failure as a refusal — refusals MUST mean "the answer is not in the document," not "the model could not be reached."

#### Frontend

- **FR-017**: A web UI MUST be reachable at a URL produced by the running stack after `make up` (no additional service the reviewer must start). The URL MUST be documented in the README.
- **FR-018**: The UI MUST present a question input, a submit control, and a response area on a single page. No navigation, no authentication, no persistent client-side state across reloads is required.
- **FR-019**: The UI MUST render answered responses as the answer text followed by a list of citations. Each rendered citation MUST display at minimum the page number and the quoted text span; the chunk identifier MUST be visible (e.g., in a small label or tooltip) so a reviewer can cross-reference logs.
- **FR-020**: The UI MUST render refused responses in a visually distinct way from answered responses (different color, badge, label, or icon — the choice is implementation-level), so a reviewer can perceive at a glance which path the system took. Empty-corpus responses MUST also be visually distinct from refusals.
- **FR-021**: The UI MUST indicate when a query is in flight (e.g., spinner, "Thinking…" label, or disabled submit button), so the reviewer is never left wondering whether the submit registered.
- **FR-022**: The UI MUST NOT include analytics, telemetry, third-party trackers, or any external network calls beyond the request to the local backend API.

#### Cross-Cutting

- **FR-023**: All new public functions MUST carry type annotations and pass the linter checks the boilerplate already enforces (carried forward from feature 001 FR-013).
- **FR-024**: The boilerplate's `query` CLI stub (`rag query "<question>"`) MUST be implemented in this feature to call the same query path as the HTTP endpoint, so the same code path is exercised whether a reviewer uses the terminal or the UI.
- **FR-025**: Test coverage MUST include, at minimum: chunking boundary behavior, retrieval ranking correctness on a small fixture corpus, citation construction from retrieved chunks, the refusal path (both low-similarity and failed-grounding-check causes), and the empty-corpus path — all four of the categories the constitution's Article VI.2 requires.
- **FR-026**: No PDF, model output, or any user-supplied content MAY be persisted outside the database (no logs of full PDFs to disk, no caching of full answers to a filesystem). Structured logs MAY contain truncated samples for observability.
- **FR-027**: All Gemini API keys MUST continue to be sourced from environment variables as in feature 001; no key material may be committed or hard-coded.
- **FR-029**: A small public-domain PDF MUST be committed to the repository at `data/sample.pdf` so that a fresh clone has an ingestible document available with no external download step. The committed PDF MUST be small enough (under ~5 MB, fewer than ~50 pages) to keep clones fast and the SC-001 ingest-time budget realistic. The README MUST document both `rag ingest data/sample.pdf` (the self-contained default) and `rag ingest <other-path>` (the swap-in for the real assessment PDF during the live demo).

### Key Entities *(include if feature involves data)*

The persistence-layer entities (`source_document`, `chunk`, `schema_migrations`) are inherited from feature 001 and not redefined here. This feature introduces the following **runtime** entities that flow through the API surface:

- **Query Request**: A user's question. Carries the question text and, optionally, retrieval parameters (top-k override) for debugging.
- **Query Response**: The system's reply. Carries a `status` (`answered`, `refused`, or `no_documents`), the answer text (when answered), a citations list (when answered), the identifier of the generation model that produced the answer, and a refusal cause (when refused). The structure MUST make it impossible to be `answered` with zero citations or `refused` with non-empty citations.
- **Citation**: A single piece of evidence attached to an answered response. References a `chunk` by its stable identifier and carries the page number and the quoted text span surfaced to the reviewer. A reviewer holding the citation alone MUST be able to open the source PDF and find the quoted text on the named page.
- **Generation Prompt**: The internal prompt assembled from retrieved chunks plus the user's question. Not part of the API surface but called out here because the prompt template's content directly determines grounding behavior, and it MUST be source-controlled.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer with the stack up can ingest the assessment PDF using the documented command and see a "complete" outcome in under 3 minutes for a PDF of up to 50 pages, with every resulting chunk row carrying all Article II provenance fields populated.
- **SC-002**: A reviewer submitting an in-scope question through the UI receives an answered response with at least one citation in under 10 seconds end-to-end (typing-submit-to-rendered-result), assuming the stack has had at least one warm query.
- **SC-003**: On a hand-curated set of at least 5 in-scope questions and at least 5 out-of-scope questions, the system answers 100% of the out-of-scope questions with a refusal (no fabricated content, no citations) and produces an answer with at least one citation for at least 80% of the in-scope questions. (Note: a 100% answer rate on in-scope is not required by this feature — that is what the eval harness in feature 003 will systematically measure.)
- **SC-004**: Every citation produced by the system corresponds to a verifiable span in the source PDF: a reviewer opening the PDF to the cited page number can locate the quoted text without ambiguity. 100% of citations checked during the demo dry-run MUST pass this test.
- **SC-005**: Re-running the ingest command against the same PDF 5 consecutive times produces zero duplicate chunk rows in the database and zero failures.
- **SC-006**: A reviewer on a fresh machine, following only the README, can go from `git clone` to a rendered answer in the browser in under 10 minutes (including stack stand-up from feature 001 and ingest from this feature).
- **SC-007**: The UI distinguishes answered, refused, and empty-corpus responses visually such that a reviewer correctly identifies which case occurred 100% of the time across a sample of at least 6 responses (2 of each type).

## Assumptions

- **Stack is binding**: The constitution's Article IV pins the PDF extraction service (Gemini File API), the embedding model (Gemini `text-embedding-004`, 768-dim), the generation model (Gemini 2.5 Flash, with Pro allowed for the grounding check), and the database (Postgres 16 + pgvector). This feature follows those choices without re-litigating them.
- **Eval is out of scope here**: Article III's eval harness (curated Q&A set, Recall@k, MRR, LLM-as-judge results in the README) is feature 003. This feature creates the runtime that the eval harness will measure but does not run the eval itself. SC-003 above is a *demo-readiness* sanity check, not the systematic eval Article III requires.
- **Multi-document is out of scope**: One PDF at a time, per constitution Article VII. The schema already supports multiple source documents, but ingest and retrieval treat the corpus as "everything in the chunk table." Filtering by source document is a downstream concern.
- **Frontend is minimal by design**: Per the 2026-05-12 clarification, the UI is delivered as HTMX route(s) on the existing FastAPI app, server-rendered via Jinja2 templates — keeping the compose topology at two services (`app` + `db`) and putting UI logic in the same code path the API tests already cover. Visual polish, branding, theming, dark mode, accessibility audits, and mobile responsiveness are explicitly out of scope. The bar is "the demo flows well in a browser" — nothing more.
- **Grounding check approach**: Constitution Article I.2 lists similarity threshold (a) *and* post-generation entailment check (b). This feature implements **both**: threshold first (cheap, fast, prevents weakly-grounded answers from being generated), and an entailment check second (catches drift when retrieval succeeds but generation strays). Per the 2026-05-12 clarification, the entailment check is implemented as an LLM-as-judge call to a configurable OpenAI-API-compatible endpoint (see FR-012 / FR-028 + the Article IV.6 deviation note below).

- **Article IV.6 deviation — grounding judge on a local OpenAI-API-compatible LLM**: Constitution Article IV.6 says "Pro is acceptable for the grounding check if cost permits." This feature instead routes the grounding judge to a local OpenAI-API-compatible server (LM Studio, Ollama, llama.cpp, vLLM, or equivalent), configured via env vars. **Justification per Art IV.8**: (1) cost — keeps the demo zero-marginal-cost per query for the grounding leg, which makes iterative tuning and dry-run rehearsals (Art VIII.6) frictionless; (2) operational signal — demonstrates the codebase can speak to multiple LLM backends behind a clean interface, which is a sane senior-engineer pattern when the production stack is opinionated; (3) scope-preserving — the *behavior* required by Article I.2.b (a post-generation entailment check that can block an answer) is unchanged, only the model behind the check moves. The generator (Article IV.6, first sentence — Gemini 2.5 Flash per constitution v1.0.2) is **not** affected by this deviation; Gemini 2.5 Flash remains the answer-generating model.
- **Single embedding model for ingest and query**: Per constitution Article IV.5, the same model embeds chunks at ingest time and embeds the question at query time. Any mismatch would silently break retrieval.
- **Chunking strategy is implementation-level**: The requirement is "every chunk carries its provenance" (FR-002). Whether chunks are fixed-size, paragraph-aware, page-aware, or token-budget-aware is a design choice for `/speckit-plan`. The spec deliberately does not pin this so the plan can choose based on the PDF's structure.
- **Test PDF**: Per the 2026-05-12 clarification, a small public-domain PDF is committed at `data/sample.pdf` so a fresh clone is self-contained and SC-006 (clone-to-answer in under 10 minutes) holds without any external download step. The README documents `rag ingest data/sample.pdf` as the default and `rag ingest <other-path>` as the swap-in for the actual assessment PDF during the live demo. The feature itself is independent of which PDF is ingested — `data/sample.pdf` is a smoke-test fixture, not a corpus-coupled dependency.
- **No streaming**: Per constitution Article VII, streaming token responses are out of scope. Responses are returned whole.
- **Authentication is out of scope**: Per constitution Article VII, no auth, no multi-tenancy, no user accounts. The UI is unauthenticated and assumes a local-development trust boundary.
- **Network access at runtime**: The stack requires outbound connectivity to the Gemini API during ingest and query. Offline operation is not a goal of this feature.
- **Frontend served from the stack**: The UI is reachable from `make up` without a second start command. Per the 2026-05-12 clarification, this is satisfied by route(s) on the existing FastAPI app — no additional compose service.
