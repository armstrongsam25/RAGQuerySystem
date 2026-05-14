# Quickstart — Feature 002 Developer Flow

**Feature**: [002-rag-query-and-ui](./spec.md)
**Plan**: [plan.md](./plan.md)
**Date**: 2026-05-12

Once feature 002 lands, this is the path from clone to a rendered answer in a browser. The user-facing README will eventually carry an abridged version; this file is the developer-facing reference.

## Prerequisites

1. **Docker** — Docker Desktop on macOS/Windows or Docker Engine + compose plugin on Linux.
2. **A Gemini API key** — get one at [aistudio.google.com](https://aistudio.google.com/app/apikey). Required for PDF extraction (File API), embeddings (`text-embedding-004`), and generation (Gemini 2.5 Flash).
3. **A local OpenAI-API-compatible LLM running on the host** — for the grounding judge per the 2026-05-12 Q2 clarification and the Art IV.6 deviation in plan.md. Use any of:
   - **LM Studio** (default `:1234`) — recommended for first run; GUI, no terminal config.
   - **Ollama** (`:11434`, with `/v1` shim) — `ollama serve` + `ollama pull llama3.1:8b-instruct`.
   - **llama.cpp server** (`:8080`).
   - **vLLM** (`:8000` — collides with `app`; pick a different port).

   Suggested model: a 7-8B instruction-tuned model with JSON-mode support (Llama 3.1 8B Instruct, Mistral 7B Instruct, Qwen2.5 7B). The judge needs to follow a strict JSON schema (R-015); larger is fine, smaller may struggle.

## One-time setup

```pwsh
git clone <repo>
cd RAGQuerySystem
Copy-Item .env.example .env
# Edit .env:
#   - Set GEMINI_API_KEY=<your-key>
#   - Confirm GROUNDING_JUDGE_BASE_URL points at your local LLM
#     (default http://host.docker.internal:1234/v1 works for LM Studio with
#     default port on macOS/Windows; Linux see "Linux host networking" below).
#   - Set GROUNDING_JUDGE_MODEL=<the model id your local server exposes>
```

### Linux host networking

`host.docker.internal` is **not** resolvable from a Linux container by default. The compose file delivered by this feature adds `extra_hosts: ["host.docker.internal:host-gateway"]` to the `app` service so it works on Linux too. No manual step required, but worth knowing: if a Linux user reports "judge unreachable," check that this line is in `docker-compose.yml` and that the local LLM is bound to all interfaces (not just `127.0.0.1`).

## Bring the stack up

```pwsh
make up
```

This is unchanged from feature 001: builds the app image, starts `app` and `db`, applies migrations (now including `0002_query_path.sql`), and waits for the health endpoint. Expect ~60-90 s on a cold build, ~10-15 s on a warm one.

Verify:

```pwsh
curl http://localhost:8000/health
# {"status":"ok","schema_version":"0002_query_path.sql","db":"ok",...}
```

## Ingest the sample PDF

```pwsh
make ingest
# equivalent to: uv run rag ingest data/sample.pdf
```

A small public-domain PDF is committed at `data/sample.pdf` (FR-029) so the clone is self-contained. To ingest a different PDF instead — e.g., the Nymbl assessment PDF — pass the path:

```pwsh
uv run rag ingest path\to\your.pdf
```

Expect structured JSON log lines per page:

```text
{"event":"ingest_started","pdf_path":"data/sample.pdf","trace_id":"…"}
{"event":"file_hash_computed","file_hash":"a1b2…","trace_id":"…"}
{"event":"page_extracted","page_number":1,"chars":2841,"trace_id":"…"}
…
{"event":"chunks_persisted","count":47,"trace_id":"…"}
{"event":"ingest_complete","elapsed_s":52.3,"trace_id":"…"}
```

Re-running `make ingest` against the same PDF logs `ingest_already_done` and exits 0 (spec FR-004 + SC-005).

## Ask a question

### Via the browser (the demo path)

Open <http://localhost:8000/> in any modern browser. Type a question whose answer is in the PDF, click submit. Expect the response area to swap in:

- **Answered**: the answer paragraph followed by a citation list, each with a page-number badge and a quoted span ≤ 400 chars.
- **Refused**: a "Not in document" badge and a refusal message. No citations rendered.
- **No documents**: shouldn't happen after a successful ingest, but if you query an empty corpus the UI shows the corpus-empty message and the ingest command.

### Via the CLI

```pwsh
uv run rag query "How long must patients fast before the procedure?"
```

Same query path, different surface. Add `--json` for the raw response body.

### Via curl

```pwsh
curl -X POST http://localhost:8000/query `
  -H "Content-Type: application/json" `
  -d '{"question":"How long must patients fast?"}'
```

Response shape is specified in [`contracts/query.yaml`](./contracts/query.yaml).

## Inspect a trace

Every request emits a `trace_id`. To follow a single query end-to-end:

```pwsh
make logs | Select-String "<trace_id-hex>"
```

You'll see the chain: query_received → embedding_computed → retrieval_complete → generation_complete → judge_complete → query_responded, each on its own JSON line with the same `trace_id`. The HTTP response carries the same id in `X-RAG-Trace-Id` and (for JSON responses) the `trace_id` field.

## Run the tests

Unit tier (hermetic, no Docker needed):

```pwsh
make test
```

Integration tier (requires `make up` and a reachable grounding judge):

```pwsh
$env:RUN_INTEGRATION = "1"
make test-integration
```

The integration tier in this feature exercises the real pgvector HNSW retrieval and a stub OpenAI-compatible HTTP server (a small test fixture, not LM Studio) for the judge path.

## Common issues

- **"upstream_judge" 503 on every query**: your local LLM isn't reachable from inside the `app` container. Check `GROUNDING_JUDGE_BASE_URL` and verify the host can serve a request to that URL from the container: `docker compose exec app curl -v $GROUNDING_JUDGE_BASE_URL/models`.
- **"upstream_gemini" 503 during ingest**: `GEMINI_API_KEY` is wrong, the key is revoked, or you're past the free-tier rate limit. The error message names the upstream.
- **Migrations didn't apply**: `/health` reports a schema version less than `0002_query_path.sql`. Run `make down` (volume is preserved) and `make up` again; the runner is idempotent.
- **Re-ingest produces "ingest_already_done"**: expected behavior. To force re-ingest, drop the row by file_hash: `docker compose exec db psql -U rag -d rag -c "DELETE FROM source_document WHERE file_hash = '<hash>';"` (CASCADE removes chunks).

## What's next

Feature 003 will deliver:

- The hand-curated `evals/questions.jsonl` (≥10 entries, the three categories from constitution Art III.1).
- The `rag eval` real implementation (currently a stub).
- The Recall@k / MRR / LLM-as-judge scoring (Art III.2-3).
- Eval results checked into `evals/results/` and surfaced in the README (Art III.4).

After feature 003: slide deck and 30-minute demo dry-run (Art VIII.5-6).
