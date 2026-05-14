"""`rag query "<question>"` — real implementation (feature 002).

Calls the same `answer_question` orchestrator the HTTP endpoint uses, so
the same path is exercised whether the reviewer uses curl, the UI, or the
terminal (spec FR-024).
"""

from __future__ import annotations

import asyncio
import json as json_lib
import sys

import typer

from rag.config import Settings, get_settings
from rag.db import make_pool
from rag.log import configure_logging, get_logger
from rag.providers import (
    GeminiProvider,
    OpenAICompatJudgeProvider,
    Providers,
    UpstreamProviderError,
)
from rag.query.pipeline import answer_question
from rag.query.responses import QueryAnswered, QueryNoDocuments, QueryRefused, QueryResponse
from rag.repositories import PgVectorChunkRepository
from rag.trace import new_trace_id

logger = get_logger(__name__)


def query(
    question: str = typer.Argument(..., help="The natural-language question."),
    top_k: int = typer.Option(
        None,
        "--top-k",
        help="Override retrieval top-k for this call. Defaults to RAG_TOP_K.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit the full response as JSON (matches POST /query body).",
    ),
) -> None:
    """Ask a question over the ingested corpus."""
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    trace_id = new_trace_id()

    try:
        response = asyncio.run(_run(question, top_k, settings, trace_id))
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except UpstreamProviderError as exc:
        typer.secho(
            f"error: upstream {exc.provider} failed: {exc.cause}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    if json_output:
        sys.stdout.write(response.model_dump_json(indent=2))
        sys.stdout.write("\n")
        return

    _render_human(response)


async def _run(
    question: str,
    top_k: int | None,
    settings: Settings,
    trace_id: str,
) -> QueryResponse:
    pool = make_pool(settings.database_dsn)
    await pool.open(wait=True, timeout=10)
    try:
        repo = PgVectorChunkRepository(pool)
        gemini = GeminiProvider(settings)
        judge = OpenAICompatJudgeProvider(settings)
        providers = Providers(embedder=gemini, generator=gemini, judge=judge)
        return await answer_question(
            question,
            repo=repo,
            providers=providers,
            settings=settings,
            trace_id=trace_id,
            top_k_override=top_k,
        )
    finally:
        await pool.close()


def _render_human(response: QueryResponse) -> None:
    short_trace = response.trace_id[:8]
    if isinstance(response, QueryAnswered):
        typer.secho(f"ANSWERED  (trace={short_trace})", fg=typer.colors.GREEN, bold=True)
        typer.echo(response.answer)
        typer.echo("\nCitations:")
        for i, c in enumerate(response.citations, start=1):
            trunc = " (truncated)" if c.truncated else ""
            typer.echo(f'  [{i}] page {c.page_number}  "{c.quoted_span}"{trunc}')
            typer.echo(f"      chunk_id={c.chunk_id}")
        return
    if isinstance(response, QueryRefused):
        typer.secho(
            f"REFUSED ({response.refusal_cause})  (trace={short_trace})",
            fg=typer.colors.YELLOW,
            bold=True,
        )
        typer.echo(response.message)
        return
    if isinstance(response, QueryNoDocuments):
        typer.secho(f"NO DOCUMENTS  (trace={short_trace})", fg=typer.colors.YELLOW, bold=True)
        typer.echo(response.message)
        return
    # Should be unreachable thanks to the discriminated union.
    typer.echo(json_lib.dumps(response.model_dump(), indent=2))
