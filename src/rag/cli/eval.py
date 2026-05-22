"""`rag eval` — run the eval set against the live stack and emit metrics."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from rag.config import Settings, get_settings
from rag.db import make_pool
from rag.eval.models import EvalSummary
from rag.eval.reporters import write_jsonl, write_markdown
from rag.eval.runner import load_questions, run_eval
from rag.log import configure_logging, get_logger
from rag.providers import LocalEmbeddingProvider, LocalEmbeddingProviderEmbedder, OpenAIProvider, Providers
from rag.repositories import PgVectorChunkRepository

logger = get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_QUESTIONS = _REPO_ROOT / "evals" / "questions.jsonl"
_DEFAULT_RESULTS_JSONL = _REPO_ROOT / "evals" / "results.jsonl"
_DEFAULT_RESULTS_MD = _REPO_ROOT / "evals" / "results.md"


def eval_cmd(
    questions: Path = typer.Option(
        _DEFAULT_QUESTIONS,
        "--questions",
        help="Path to the JSONL question set.",
    ),
    results_jsonl: Path = typer.Option(
        _DEFAULT_RESULTS_JSONL,
        "--results-jsonl",
        help="Path to write machine-readable per-metric rows.",
    ),
    results_md: Path = typer.Option(
        _DEFAULT_RESULTS_MD,
        "--results-md",
        help="Path to write the human-readable summary.",
    ),
    top_k: int = typer.Option(5, "--top-k", help="Retrieval top-k used for Recall@k and MRR."),
) -> None:
    """Run the eval set against the running stack."""
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    summary = asyncio.run(_run(questions, top_k, settings))
    write_jsonl(summary, results_jsonl)
    write_markdown(summary, results_md)
    typer.echo(
        f"Eval complete: {summary.n_total} questions "
        f"(retrieval={summary.n_factoid_or_synthesis}, out_of_scope={summary.n_out_of_scope})"
    )
    if summary.n_factoid_or_synthesis:
        typer.echo(
            f"  Recall@{top_k}={summary.recall_at_5:.3f}  "
            f"MRR={summary.mrr:.3f}  "
            f"answer_quality_judge={summary.answer_quality_judge:.3f}"
        )
    if summary.n_out_of_scope:
        typer.echo(f"  Refusal precision={summary.refusal_precision:.3f}")
    typer.echo(f"  Wrote {results_jsonl} and {results_md}")


async def _run(questions_path: Path, top_k: int, settings: Settings) -> EvalSummary:
    pool = make_pool(settings.database_dsn)
    await pool.open(wait=True, timeout=10)
    try:
        repo = PgVectorChunkRepository(pool)
        local_embed = LocalEmbeddingProvider(settings)
        embedder = LocalEmbeddingProviderEmbedder(local_embed)
        llm = OpenAIProvider(settings)
        providers = Providers(embedder=embedder, generator=llm, judge=llm)
        questions = load_questions(questions_path)
        return await run_eval(
            questions, repo=repo, providers=providers, settings=settings, top_k=top_k
        )
    finally:
        await pool.close()