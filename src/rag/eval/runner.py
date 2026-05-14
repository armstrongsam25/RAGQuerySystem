"""Orchestration: load questions, run them through the pipeline, aggregate.

The runner is intentionally thin — every metric computation lives in
:mod:`rag.eval.metrics` so the math is testable in isolation. The runner
just plumbs questions through ``answer_question`` (the same orchestrator
the HTTP endpoint and ``rag query`` use) plus a direct ``repo.search``
call so retrieval pages are observable even when the pipeline refuses.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from rag.config import Settings
from rag.eval.metrics import (
    compute_answer_quality_judge,
    compute_mrr,
    compute_recall_at_k,
    compute_refusal_precision,
)
from rag.eval.models import EvalQuestion, EvalSummary, QuestionResult
from rag.log import get_logger
from rag.providers.base import Providers, UpstreamProviderError
from rag.query.pipeline import answer_question
from rag.query.responses import QueryAnswered, QueryRefused
from rag.repositories.base import ChunkRepository
from rag.trace import new_trace_id

logger = get_logger(__name__)


def load_questions(path: Path) -> list[EvalQuestion]:
    """Parse ``evals/questions.jsonl`` into typed rows.

    Skips blank lines so an editor can add separators without breaking
    parsing. Unknown fields are tolerated (forward-compat with future
    columns) but required fields raise.
    """
    questions: list[EvalQuestion] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no} is not valid JSON: {exc}") from exc
        try:
            questions.append(
                EvalQuestion(
                    id=str(payload["id"]),
                    question=str(payload["question"]),
                    expected_answer=payload.get("expected_answer"),
                    expected_pages=[int(p) for p in payload.get("expected_pages") or []],
                    category=str(payload["category"]),
                    notes=str(payload.get("notes", "")),
                )
            )
        except KeyError as exc:
            raise ValueError(f"{path}:{line_no} missing required field {exc}") from exc
    return questions


async def _evaluate_one(
    question: EvalQuestion,
    *,
    repo: ChunkRepository,
    providers: Providers,
    settings: Settings,
    top_k: int = 5,
) -> QuestionResult:
    """Run one question through retrieval + the full pipeline.

    Embedding is shared across the retrieval-only call and the pipeline
    by running them sequentially against the same query; the cost is
    one extra ``repo.search`` per question, which is negligible against
    the LLM-call cost the full pipeline already pays.
    """
    trace_id = new_trace_id()

    # Direct retrieval pass — sim_floor=0 so we observe the actual top-k
    # ordering even when the pipeline will refuse on similarity grounds.
    embeddings = await providers.embedder.embed([question.question])
    if not embeddings:
        raise UpstreamProviderError(
            "gemini", RuntimeError(f"eval embed returned no vectors for {question.id}")
        )
    retrieved = await repo.search(embeddings[0], k=top_k, sim_floor=0.0)
    retrieved_pages = [rc.record.page_number for rc in retrieved]

    # Full pipeline pass — this is what produces the answer/refusal we
    # actually grade.
    response = await answer_question(
        question.question,
        repo=repo,
        providers=providers,
        settings=settings,
        trace_id=trace_id,
    )

    if isinstance(response, QueryAnswered):
        return QuestionResult(
            question_id=question.id,
            category=question.category,
            expected_pages=question.expected_pages,
            retrieved_pages=retrieved_pages,
            response_status="answered",
            refusal_cause=None,
            answer=response.answer,
            citation_pages=[c.page_number for c in response.citations],
        )
    if isinstance(response, QueryRefused):
        return QuestionResult(
            question_id=question.id,
            category=question.category,
            expected_pages=question.expected_pages,
            retrieved_pages=retrieved_pages,
            response_status="refused",
            refusal_cause=response.refusal_cause,
            answer=None,
            citation_pages=[],
        )
    # QueryNoDocuments — corpus empty, abort the run loudly.
    raise RuntimeError(
        f"eval question {question.id!r} hit no_documents — ingest a PDF before running eval"
    )


async def run_eval(
    questions: Iterable[EvalQuestion],
    *,
    repo: ChunkRepository,
    providers: Providers,
    settings: Settings,
    top_k: int = 5,
) -> EvalSummary:
    """Run every question, compute aggregates, return a typed summary."""
    per_question: list[QuestionResult] = []
    questions_list = list(questions)
    for q in questions_list:
        logger.info("eval_question_start", extra={"event": "eval_question_start", "id": q.id})
        result = await _evaluate_one(
            q, repo=repo, providers=providers, settings=settings, top_k=top_k
        )
        logger.info(
            "eval_question_done",
            extra={
                "event": "eval_question_done",
                "id": q.id,
                "status": result.response_status,
                "category": result.category,
            },
        )
        per_question.append(result)

    recall, n_retrieval = compute_recall_at_k(per_question, k=top_k)
    mrr, _ = compute_mrr(per_question)
    refusal, _ = compute_refusal_precision(per_question)
    quality, _ = compute_answer_quality_judge(per_question)

    return EvalSummary(
        timestamp=datetime.now(UTC),
        n_total=len(questions_list),
        n_factoid_or_synthesis=n_retrieval,
        n_out_of_scope=sum(1 for r in per_question if r.category == "out_of_scope"),
        recall_at_5=recall,
        mrr=mrr,
        refusal_precision=refusal,
        answer_quality_judge=quality,
        per_question=per_question,
        model_versions={
            "embedding": f"{settings.EMBEDDING_MODEL}@{settings.EMBEDDING_DIM}",
            "generation": settings.GENERATION_MODEL,
            "judge": settings.GROUNDING_JUDGE_MODEL,
        },
    )
