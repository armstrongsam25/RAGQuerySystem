"""Root Typer app — `rag --help`.

Subcommands:
  * `ingest` — real (feature 002).
  * `query`  — real (feature 002).
  * `serve`  — new (feature 002), wraps uvicorn.
  * `eval`   — stub, delivered by feature 003-eval-harness.
"""

from __future__ import annotations

import asyncio
import sys

# Windows event-loop fix. Python 3.8+ defaults to ProactorEventLoop on
# Windows, but psycopg's async pool requires SelectorEventLoop. Set the
# policy at module-import time so every `asyncio.run(...)` invocation
# downstream (ingest, query) lands on a compatible loop. No-op on
# non-Windows platforms (including the Linux container).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import typer

from rag import __version__
from rag.cli.eval import eval_cmd
from rag.cli.ingest import ingest
from rag.cli.query import query
from rag.cli.serve import serve

app = typer.Typer(
    name="rag",
    help="Small RAG system CLI.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def _root(
    _version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """rag — small retrieval-augmented generation."""


app.command(name="ingest", help="Ingest a PDF into the vector store.")(ingest)
app.command(name="query", help="Ask a question over the ingested PDF.")(query)
app.command(name="serve", help="Run the FastAPI service (uvicorn).")(serve)
app.command(name="eval", help="(stub) Run the eval set and emit metrics.")(eval_cmd)
