"""Dataclasses for the eval harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class EvalQuestion:
    """One row of ``evals/questions.jsonl``."""

    id: str
    question: str
    expected_answer: str | None
    expected_pages: list[int]
    category: str
    notes: str = ""


@dataclass(frozen=True)
class QuestionResult:
    """One question after running through the pipeline.

    Carries enough to compute every aggregate metric without re-running
    the query (the metric functions in :mod:`rag.eval.metrics` consume
    these directly).
    """

    question_id: str
    category: str
    expected_pages: list[int]
    retrieved_pages: list[int]
    response_status: str
    refusal_cause: str | None
    answer: str | None
    citation_pages: list[int]


@dataclass(frozen=True)
class MetricRow:
    """One aggregate metric — what gets serialized to results.jsonl."""

    metric: str
    value: float
    n_questions: int
    model_versions: dict[str, str]
    timestamp: str
    delta_vs_baseline: float | None = None
    ship_disposition: str | None = None


@dataclass
class EvalSummary:
    """End-to-end run summary."""

    timestamp: datetime
    n_total: int
    n_factoid_or_synthesis: int
    n_out_of_scope: int
    recall_at_5: float
    mrr: float
    refusal_precision: float
    answer_quality_judge: float
    per_question: list[QuestionResult] = field(default_factory=list)
    model_versions: dict[str, str] = field(default_factory=dict)
