# RAG Query System

> Tiny retrieval-augmented generation over a single PDF, with grounded citations and explicit refusals.

[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Postgres 16 + pgvector](https://img.shields.io/badge/Postgres-16%20%2B%20pgvector-336791?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Gemini 2.5 Flash](https://img.shields.io/badge/Gemini-2.5%20Flash-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)
[![HTMX](https://img.shields.io/badge/HTMX-2.0-3366CC?logo=htmx&logoColor=white)](https://htmx.org/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Tests](https://img.shields.io/badge/tests-77%20passing-brightgreen)](#)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)

---

## What it does

- **Ingest** a PDF — Gemini File API extracts pages, the chunker keeps page boundaries, embeddings land in Postgres + pgvector (HNSW, 768 dims).
- **Ask questions** via the HTMX UI, the JSON API, or the `rag` CLI.
- **Answers carry citations** — every quoted span is tied to a chunk id and a page number a reviewer can open and verify.
- **Refuses cleanly** when the document doesn't cover the question. Two tiers: cosine similarity floor, then an LLM-as-judge entailment check.

## Quickstart

```bash
git clone <repo>
cd RAGQuerySystem

# 1. Configure
cp .env.example .env        # fill all fields

# 2. Start a local OpenAI-compatible LLM on the host
#    (LM Studio :1234, Ollama :11434, llama.cpp :8080 — any one)
#    or use Google Gemini services.

# 3. One-time: generate the sample PDF or use one of the curated PDFs in data/sample-pdfs/curated/.
uv run python scripts/make_sample_pdf.py

# 4. Bring the stack up
make up

# 5. Ingest the sample
make ingest
-or-
Upload any PDF in the frontend UI.

# 6. Open the UI → http://localhost:8000/
```

Health check:

```bash
curl -s http://localhost:8000/health | jq
```

See `.env.example` for all configuration and `make help` for every target.

## Try it

In-scope (answered, with a page citation):

```bash
make query QUESTION='How long must patients fast from solids before the procedure?'
```

Out-of-scope (refused, no citations):

```bash
make query QUESTION='What is the current price of Bitcoin in US dollars?'
```

Or via curl:

```bash
curl -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"How long must patients fast?"}'
```

## Commands

| Command | What it does |
|---|---|
| `make up` / `make down` | Start / stop the `app` + `db` stack. |
| `make logs` | Tail JSON-structured app logs (grep by `trace_id`). |
| `make ingest` | Ingest `data/sample.pdf` (idempotent on SHA-256). |
| `make reingest` | Re-ingest with `--force`, overwriting prior state. |
| `make query QUESTION='…'` | Ask a question via the CLI. |
| `make serve` | Run the FastAPI service locally (non-Docker dev). |
| `make test` | Unit tier — hermetic, no Docker. |
| `make test-integration` | Integration tier against the running stack. |
| `make lint` / `make fmt` | `ruff check` / `ruff format`. |
| `make sample-pdf` | Generate `data/sample.pdf` after a fresh clone. |

All targets are also available as `uv run rag …` console-script subcommands.

## Project layout

```
.
├── src/rag/        # FastAPI app, ingest + query pipelines, HTMX UI, CLI
├── tests/          # Unit (hermetic) + integration tiers
├── migrations/     # Versioned SQL — runs on app startup
├── specs/          # Feature specs, plans, contracts, research
├── data/           # sample.pdf, sample-pdfs/curated/, and any PDFs you mount in
├── scripts/        # make_sample_pdf.py and other one-shots
├── evals/          # questions.jsonl (eval harness lands in a later feature)
├── Makefile        # Single entry point for every command
└── docker-compose.yml
```

## Sample data

Three small PDFs are tracked under [`data/sample-pdfs/curated/`](data/sample-pdfs/curated/) so you have something to upload immediately after cloning.

For a larger corpus to exercise ingest and query at scale, download the **[Dataset of PDF Files](https://www.kaggle.com/datasets/manisha717/dataset-of-pdf-files)** from Kaggle (~1,000 PDFs, ~870 MB) and drop the contents into `data/sample-pdfs/`. Everything in that directory outside `curated/` is gitignored, so the dataset stays local.

```bash
# Requires a Kaggle account + API token (~/.kaggle/kaggle.json)
uv run --with kaggle kaggle datasets download -d manisha717/dataset-of-pdf-files \
  -p data/sample-pdfs --unzip
```

## Tech stack

- **Backend**: Python 3.12, FastAPI, Pydantic, Uvicorn, Typer (CLI)
- **Frontend**: Jinja2 + HTMX 2.0, plain CSS
- **Data**: Postgres 16 + pgvector (HNSW, 768-dim vectors)
- **Models**: `gemini-embedding-001` (embeddings), `gemini-2.5-flash` (generation), local OpenAI-compatible LLM (grounding judge)
- **Tooling**: `uv`, `ruff`, `pytest` + `pytest-asyncio`, Docker Compose

## Design docs

Full specs, plans, contracts, and research notes live under [`specs/`](specs/). The project constitution is at [`.specify/memory/constitution.md`](.specify/memory/constitution.md).

## License

Apache 2.0 — see [LICENSE](LICENSE).
