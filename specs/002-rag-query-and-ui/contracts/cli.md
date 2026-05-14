# CLI Contract — `rag` (updated for feature 002)

Two previously-stub subcommands move to real implementations; one new subcommand wraps uvicorn; the eval subcommand stays a stub for feature 003.

This contract supersedes [`specs/001-rag-boilerplate/contracts/cli.md`](../../../001-rag-boilerplate/contracts/cli.md) for the commands it covers; everything not listed here is unchanged from feature 001.

## Root command (updated)

```text
$ rag --help

Usage: rag [OPTIONS] COMMAND [ARGS]...

  Small RAG system CLI.

Commands:
  ingest   Ingest a PDF into the vector store.
  query    Ask a question over the ingested PDF.
  serve    Run the FastAPI service (uvicorn).
  eval     (stub) Run the eval set and emit metrics.
```

## `rag ingest <pdf_path>` — real (was stub)

```text
$ rag ingest --help

Usage: rag ingest [OPTIONS] PDF_PATH

  Ingest a PDF: extract per page via Gemini File API, chunk page-by-page,
  embed, and persist to the vector store. Idempotent — re-running against a
  previously-ingested PDF (same file_hash) is a no-op.

Arguments:
  PDF_PATH    Path to the PDF file [required]

Options:
  --concurrency INTEGER  Per-page Gemini call concurrency limit [default: 4]
  --help                 Show this message and exit.
```

**Exit codes**:
- `0` — ingest completed (new chunks written) OR ingest was a no-op (PDF already ingested by `file_hash`).
- `1` — file not found, not a PDF, unreadable, or upstream model error. Stderr names the cause.
- `2` — reserved for "stub" semantics; `rag ingest` never exits 2 anymore (it used to in feature 001).

**Side effects on success**:
- One new `source_document` row keyed by `file_hash` (or zero rows on re-ingest).
- N new `chunk` rows (or zero on re-ingest).
- Structured JSON logs for ingest_started → file_hash_computed → page_extracted (per page) → chunks_persisted → ingest_complete (spec FR-005).

## `rag query "<question>"` — real (was stub)

```text
$ rag query --help

Usage: rag query [OPTIONS] QUESTION

  Ask a question over the ingested corpus. Hits the same query function the
  HTTP API uses; prints the response as a human-readable summary and exits.

Arguments:
  QUESTION    The natural-language question [required]

Options:
  --top-k INTEGER  Override retrieval top-k for this call [default: $RAG_TOP_K]
  --json           Emit the full response as JSON (matches POST /query body)
  --help           Show this message and exit.
```

**Output (default, human-readable)**:

```text
ANSWERED  (trace=7b3c…)
The patient should fast for 8 hours before the procedure.

Citations:
  [1] page 12  "Patients are required to fast for a minimum of 8 hours prior…"
  [2] page 14  "Fasting requirements: 8 hours minimum, water permitted up to 2…"
```

For `refused` / `no_documents` the human output prints the status badge and the message; no citation block.

With `--json`, the output is the verbatim `POST /query` response body.

**Exit codes**:
- `0` — query completed (regardless of status: answered / refused / no_documents). The CLI does not consider refusal an error.
- `1` — invalid input (empty/whitespace question, too long) or upstream model error. The stderr message and exit code mirror the JSON 400 / 503 surface.

## `rag serve` — new

```text
$ rag serve --help

Usage: rag serve [OPTIONS]

  Run the FastAPI service via uvicorn. This is what the Dockerfile CMD calls;
  developers can run it locally for non-Docker debugging.

Options:
  --host TEXT     Bind host [default: 0.0.0.0]
  --port INTEGER  Bind port [default: 8000]
  --reload        Enable uvicorn auto-reload (development only)
  --help          Show this message and exit.
```

**Why this exists**: spec FR-017 + R-018 require the UI to be reachable from a URL the running stack produces after `make up`. With `rag serve` as the single entry point, the Dockerfile CMD switches from `uvicorn rag.api:app …` to `rag serve`, and the dispatch surface (`rag --help` / `make help`) lists every runtime including the server.

**Exit codes**: passes through uvicorn's exit codes (0 on clean shutdown).

## `rag eval` — still a stub (owned by feature 003)

Unchanged from feature 001's contract: emits the structured log line, prints the "not yet implemented" message to stderr naming `00X-eval-harness`, exits with code 2.

The shape of `evals/questions.jsonl` is pinned in [`contracts/eval-set.md`](./eval-set.md) so feature 003's implementation can begin without renegotiating the schema.

## Makefile dispatch (updated)

| Target | Equivalent command | Owned by |
|--------|-------------------|----------|
| `make ingest` | `uv run rag ingest data/sample.pdf` (default) — real in feature 002 | This feature |
| `make query QUESTION='<q>'` | `uv run rag query "$$QUESTION"` — real in feature 002 | This feature |
| `make eval` | `uv run rag eval` (stub) | Feature 003 |
| `make serve` | `uv run rag serve` — new | This feature |

All other targets (`up`, `down`, `logs`, `test`, `test-integration`, `lint`, `fmt`, `help`) are unchanged from feature 001.
