"""Pure metric computations for the eval harness.

These functions are deliberately I/O-free and synchronous so the unit
test suite can pin behavior against fixed inputs without spinning a
fake provider or repository. The runner in :mod:`rag.eval.runner`
produces :class:`QuestionResult` rows and then calls into these.
"""

from __future__ import annotations

from collections.abc import Iterable

from rag.eval.models import QuestionResult

# Categories that contribute to retrieval-quality metrics.
_RETRIEVAL_CATEGORIES = {"factoid", "synthesis"}


def _is_retrieval_question(result: QuestionResult) -> bool:
    return result.category in _RETRIEVAL_CATEGORIES and bool(result.expected_pages)


def compute_recall_at_k(results: Iterable[QuestionResult], *, k: int = 5) -> tuple[float, int]:
    """Recall@k — fraction of retrieval questions whose top-k retrieved pages
    overlap at least one expected page.

    Returns ``(value, n_questions)`` where ``n_questions`` counts only the
    retrieval-category rows that contributed.
    """
    hits = 0
    n = 0
    for r in results:
        if not _is_retrieval_question(r):
            continue
        n += 1
        top_k_pages = r.retrieved_pages[:k]
        if any(p in top_k_pages for p in r.expected_pages):
            hits += 1
    return (hits / n if n else 0.0, n)


def compute_mrr(results: Iterable[QuestionResult]) -> tuple[float, int]:
    """Mean Reciprocal Rank over retrieval questions.

    Rank is 1-indexed; questions with no hit contribute 0 to the sum
    (mirroring the standard MRR definition).
    """
    total = 0.0
    n = 0
    for r in results:
        if not _is_retrieval_question(r):
            continue
        n += 1
        rr = 0.0
        for idx, page in enumerate(r.retrieved_pages, start=1):
            if page in r.expected_pages:
                rr = 1.0 / idx
                break
        total += rr
    return (total / n if n else 0.0, n)


def compute_refusal_precision(results: Iterable[QuestionResult]) -> tuple[float, int]:
    """For ``category=out_of_scope`` questions, fraction that produced any refusal."""
    correct = 0
    n = 0
    for r in results:
        if r.category != "out_of_scope":
            continue
        n += 1
        if r.response_status == "refused":
            correct += 1
    return (correct / n if n else 0.0, n)


def compute_answer_quality_judge(results: Iterable[QuestionResult]) -> tuple[float, int]:
    """Judge-entailment proxy: fraction of retrieval questions that produced
    an ``answered`` response (the pipeline only answers when the grounding
    judge returns entailed, so this is exactly the judge's verdict).

    Excludes out-of-scope questions and excludes retrieval questions that
    refused for ``low_similarity`` (no answer was generated, so judge had
    nothing to score).
    """
    entailed = 0
    n = 0
    for r in results:
        if r.category == "out_of_scope":
            continue
        # Skip questions where no answer was attempted at all.
        if r.refusal_cause == "low_similarity":
            continue
        n += 1
        if r.response_status == "answered":
            entailed += 1
    return (entailed / n if n else 0.0, n)
