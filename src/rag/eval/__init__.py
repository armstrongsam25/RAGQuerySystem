"""Eval harness for the RAG pipeline.

Closes constitution Article III (Evaluation Before Demo): produce Recall@5,
MRR, refusal precision, and judge-graded answer quality over a curated
question set checked into ``evals/questions.jsonl``. Outputs land in
``evals/results.jsonl`` (machine-readable, one row per metric) and
``evals/results.md`` (human summary that the README links to).
"""

from __future__ import annotations

from rag.eval.metrics import (
    compute_answer_quality_judge,
    compute_mrr,
    compute_recall_at_k,
    compute_refusal_precision,
)
from rag.eval.models import EvalQuestion, EvalSummary, QuestionResult
from rag.eval.runner import load_questions, run_eval

__all__ = [
    "EvalQuestion",
    "EvalSummary",
    "QuestionResult",
    "compute_answer_quality_judge",
    "compute_mrr",
    "compute_recall_at_k",
    "compute_refusal_precision",
    "load_questions",
    "run_eval",
]
