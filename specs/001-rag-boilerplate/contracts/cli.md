# CLI Contract — `rag`

The boilerplate exposes a single Typer-based CLI installed by `uv` as the `rag` console script. Every command in this contract is reachable both directly (`uv run rag <cmd>`) and via the Makefile (`make <cmd>`).

This contract is the source of truth for spec FR-007 ("scripted command entry points") and FR-007 acceptance #3 ("discoverable from a single help listing").

## Root command

```text
$ rag --help

Usage: rag [OPTIONS] COMMAND [ARGS]...

  Small RAG system CLI. Subcommands marked "(stub)" exit non-zero
  with a "not yet implemented" message until the named feature lands.

Commands:
  ingest   (stub) Ingest a PDF into the vector store.
  query    (stub) Ask a question over the ingested PDF.
  eval     (stub) Run the eval set and emit metrics.
```

`--version` prints the package version from `pyproject.toml`.

## Subcommands shipped as stubs

Each stub MUST:
1. Emit a structured log line at INFO level: `{"event": "cli_stub_invoked", "command": "<name>", "feature": "<downstream-feature-id>"}`.
2. Print a human-readable message to **stderr**: `"rag <name>: not yet implemented — delivered by feature <downstream-feature-id>"`.
3. Exit with code **2** (distinct from `1` so test assertions can pin the boilerplate stub vs. a real error).

| Command | Downstream feature placeholder | Exit code |
|---------|-------------------------------|-----------|
| `rag ingest [PDF_PATH]` | `00X-pdf-ingest` (id assigned when the ingest feature is specified) | 2 |
| `rag query "<question>"` | `00X-query-pipeline` | 2 |
| `rag eval` | `00X-eval-harness` | 2 |

`PDF_PATH` and the query string are accepted *positionally* even by the stub so that downstream features inherit the surface without changing it — keeping CLI behavior stable across feature lands.

## Makefile dispatch

| Target | Equivalent command | Owned by |
|--------|-------------------|----------|
| `make up` | `docker compose up -d --build` | This feature |
| `make down` | `docker compose down` | This feature |
| `make logs` | `docker compose logs -f app` | This feature (small DX aid; not in spec but cheap) |
| `make test` | `uv run pytest -m "not integration"` | This feature |
| `make test-integration` | `RUN_INTEGRATION=1 uv run pytest -m integration` | This feature; runs against an already-up stack |
| `make lint` | `uv run ruff check . && uv run ruff format --check .` | This feature |
| `make fmt` | `uv run ruff format .` | This feature |
| `make ingest` | `uv run rag ingest` | Stub here; downstream feature |
| `make query` | `uv run rag query` | Stub here; downstream feature |
| `make eval` | `uv run rag eval` | Stub here; downstream feature |
| `make help` | Self-documenting target that greps the Makefile and prints command + one-line description | This feature |

`make help` exists so that FR-007 acceptance #3 ("discoverable from a single help listing") has a single canonical entry point — `make help` and `rag --help` both list every command.

## Non-goals

- No interactive mode (`rag repl`) at boilerplate stage.
- No shell completion installer.
- No telemetry, no usage tracking — even anonymous.
- No `rag config` subcommand for editing `.env`. `.env` is a plain file; we trust the developer with `$EDITOR`.

These are deliberately listed to forestall future PRs that add scope ahead of value.
