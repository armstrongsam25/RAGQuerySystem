"""`rag ingest <pdf_path>` — real implementation (feature 002)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from rag.config import Settings, get_settings
from rag.db import make_pool
from rag.ingest import IngestOutcome, ingest_pdf
from rag.log import configure_logging, get_logger
from rag.providers import (
    LocalEmbeddingProvider,
    LocalEmbeddingProviderEmbedder,
    OpenAIProvider,
    RateLimitedError,
    UpstreamProviderError,
)
from rag.repositories import PgVectorChunkRepository
from rag.trace import new_trace_id

logger = get_logger(__name__)


def ingest(
    pdf_path: Path = typer.Argument(
        ...,
        help="Path to the PDF file to ingest.",
    ),
    concurrency: int = typer.Option(
        2,
        "--concurrency",
        help=(
            "Per-page LLM call concurrency limit. Default 2. Lower to 1 if "
            "you see 429s."
        ),
        min=1,
        max=16,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help=(
            "Overwrite any prior ingest of this PDF (by file_hash). Drops the "
            "existing source_document row + its chunks via ON DELETE CASCADE, "
            "then re-ingests from scratch."
        ),
    ),
) -> None:
    """Ingest a PDF: extract text per page, chunk, embed, and persist."""
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    if concurrency != settings.RAG_PROVIDER_CONCURRENCY:
        settings = settings.model_copy(update={"RAG_PROVIDER_CONCURRENCY": concurrency})

    trace_id = new_trace_id()
    try:
        outcome = asyncio.run(_run(pdf_path, settings, trace_id, force=force))
    except FileNotFoundError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except RateLimitedError as exc:
        hint = ""
        if exc.retry_hint_s:
            hint = f" Server suggested waiting {exc.retry_hint_s:.0f}s before retrying."
        typer.secho(
            "error: LLM rate limit exceeded after retries.",
            fg=typer.colors.RED,
            err=True,
            bold=True,
        )
        typer.secho(
            "\nLikely causes:",
            fg=typer.colors.YELLOW,
            err=True,
        )
        typer.echo(
            "  - Free-tier daily quota exhausted.\n"
            "  - Per-minute request cap hit (try --concurrency 1 and wait).\n"
            f"\nActionable next steps:{hint}\n"
            "  - Wait for the per-day quota to reset.\n"
            "  - Enable billing if using a paid tier.\n"
            "  - Reduce --concurrency to 1 if the failure was per-minute, not per-day.\n",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except UpstreamProviderError as exc:
        typer.secho(
            f"error: upstream {exc.provider} failed: {exc.cause}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    if outcome.status == "already_done":
        typer.echo(
            f"Already ingested (file_hash={outcome.file_hash[:12]}…); 0 new chunks. "
            f"Use --force to overwrite."
        )
    elif outcome.status == "reingested":
        typer.echo(
            f"Re-ingested (force): {outcome.chunks_inserted} chunks across "
            f"{outcome.pages} pages from {pdf_path.name} "
            f"({outcome.elapsed_s:.1f}s, trace={trace_id[:8]})"
        )
    else:
        typer.echo(
            f"Ingested {outcome.chunks_inserted} chunks across {outcome.pages} pages "
            f"from {pdf_path.name} ({outcome.elapsed_s:.1f}s, trace={trace_id[:8]})"
        )


async def _run(
    pdf_path: Path,
    settings: Settings,
    trace_id: str,
    *,
    force: bool,
) -> IngestOutcome:
    pool = make_pool(settings.database_dsn)
    await pool.open(wait=True, timeout=10)
    try:
        repo = PgVectorChunkRepository(pool)
        local_embed = LocalEmbeddingProvider(settings)
        embedder = LocalEmbeddingProviderEmbedder(local_embed)
        llm = OpenAIProvider(settings)
        return await ingest_pdf(
            pdf_path,
            gemini=embedder,  # parameter name kept for API compat; only embed used for ingest
            repo=repo,
            settings=settings,
            trace_id=trace_id,
            force=force,
        )
    finally:
        await pool.close()