"""Deterministic metric tests for the eval harness.

The runner in :mod:`rag.eval.runner` plumbs queries through the live
pipeline (DB + Gemini), but the metric math lives in pure functions
that consume :class:`QuestionResult` rows. Those are the contracts we
pin here: same input → same output, regardless of upstream behavior.
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

from rag.eval.metrics import (
    compute_answer_quality_judge,
    compute_mrr,
    compute_recall_at_k,
    compute_refusal_precision,
)
from rag.eval.models import EvalSummary, QuestionResult
from rag.eval.reporters import write_jsonl, write_markdown
from rag.eval.runner import load_questions


def _result(
    qid: str,
    category: str,
    expected_pages: list[int],
    retrieved_pages: list[int],
    *,
    response_status: str = "answered",
    refusal_cause: str | None = None,
    citation_pages: list[int] | None = None,
) -> QuestionResult:
    return QuestionResult(
        question_id=qid,
        category=category,
        expected_pages=expected_pages,
        retrieved_pages=retrieved_pages,
        response_status=response_status,
        refusal_cause=refusal_cause,
        answer="stub" if response_status == "answered" else None,
        citation_pages=citation_pages if citation_pages is not None else [],
    )


# ---- Recall@k ------------------------------------------------------------


def test_recall_at_k_full_hit() -> None:
    results = [
        _result("q1", "factoid", [2], [2, 3, 1]),
        _result("q2", "factoid", [1], [1, 4, 5]),
    ]
    value, n = compute_recall_at_k(results, k=5)
    assert value == 1.0
    assert n == 2


def test_recall_at_k_partial() -> None:
    results = [
        _result("q1", "factoid", [2], [2, 3, 1]),  # hit
        _result("q2", "factoid", [9], [1, 4, 5]),  # miss — page 9 not in retrieved
    ]
    value, n = compute_recall_at_k(results, k=5)
    assert value == 0.5
    assert n == 2


def test_recall_at_k_truncates_to_k() -> None:
    # The expected page only appears at rank 6 — Recall@5 should miss it.
    results = [_result("q1", "factoid", [9], [1, 2, 3, 4, 5, 9])]
    value, _ = compute_recall_at_k(results, k=5)
    assert value == 0.0


def test_recall_at_k_skips_out_of_scope() -> None:
    results = [
        _result(
            "q-oos",
            "out_of_scope",
            [],
            [1, 2],
            response_status="refused",
            refusal_cause="low_similarity",
        ),
    ]
    value, n = compute_recall_at_k(results, k=5)
    assert n == 0  # nothing counted
    assert value == 0.0


def test_recall_at_k_skips_retrieval_question_with_no_expected_pages() -> None:
    # Defensive: a retrieval-category question with empty expected_pages
    # is malformed but shouldn't crash the metric — it just doesn't count.
    results = [_result("q-bad", "factoid", [], [1, 2])]
    value, n = compute_recall_at_k(results, k=5)
    assert n == 0
    assert value == 0.0


# ---- MRR -----------------------------------------------------------------


def test_mrr_first_hit_at_rank_1() -> None:
    results = [_result("q1", "factoid", [2], [2, 3, 4])]
    value, _ = compute_mrr(results)
    assert value == 1.0


def test_mrr_first_hit_at_rank_3() -> None:
    results = [_result("q1", "factoid", [5], [1, 2, 5, 4])]
    value, _ = compute_mrr(results)
    assert value == 1.0 / 3.0


def test_mrr_no_hit_is_zero_contribution() -> None:
    results = [
        _result("q1", "factoid", [9], [1, 2, 3]),  # no hit
        _result("q2", "factoid", [2], [2, 3, 4]),  # rank 1
    ]
    value, n = compute_mrr(results)
    assert n == 2
    # (0 + 1)/2 = 0.5
    assert value == 0.5


def test_mrr_handles_synthesis_category() -> None:
    # synthesis questions count alongside factoids.
    results = [_result("q-syn", "synthesis", [3], [1, 2, 3])]
    value, n = compute_mrr(results)
    assert n == 1
    assert value == 1.0 / 3.0


# ---- Refusal precision ---------------------------------------------------


def test_refusal_precision_all_refused() -> None:
    results = [
        _result(
            "q-oos1",
            "out_of_scope",
            [],
            [],
            response_status="refused",
            refusal_cause="low_similarity",
        ),
        _result(
            "q-oos2",
            "out_of_scope",
            [],
            [],
            response_status="refused",
            refusal_cause="failed_grounding_check",
        ),
    ]
    value, n = compute_refusal_precision(results)
    assert value == 1.0
    assert n == 2


def test_refusal_precision_one_falsely_answered() -> None:
    results = [
        _result(
            "q-oos1",
            "out_of_scope",
            [],
            [],
            response_status="refused",
            refusal_cause="low_similarity",
        ),
        _result(
            "q-oos2",
            "out_of_scope",
            [],
            [],
            response_status="answered",
            citation_pages=[1],
        ),
    ]
    value, n = compute_refusal_precision(results)
    assert value == 0.5
    assert n == 2


def test_refusal_precision_only_counts_out_of_scope() -> None:
    results = [
        _result("q-factoid", "factoid", [2], [2, 3]),  # not OOS
        _result(
            "q-oos",
            "out_of_scope",
            [],
            [],
            response_status="refused",
            refusal_cause="low_similarity",
        ),
    ]
    value, n = compute_refusal_precision(results)
    assert n == 1
    assert value == 1.0


# ---- Answer-quality (judge proxy) ----------------------------------------


def test_answer_quality_judge_all_entailed() -> None:
    results = [
        _result("q1", "factoid", [1], [1, 2]),
        _result("q2", "factoid", [2], [1, 2]),
    ]
    value, n = compute_answer_quality_judge(results)
    assert value == 1.0
    assert n == 2


def test_answer_quality_judge_some_refused_by_judge() -> None:
    results = [
        _result("q1", "factoid", [1], [1, 2]),  # answered → entailed
        _result(
            "q2",
            "factoid",
            [2],
            [1, 2],
            response_status="refused",
            refusal_cause="failed_grounding_check",
        ),  # judge said NOT entailed → 0
    ]
    value, n = compute_answer_quality_judge(results)
    assert n == 2
    assert value == 0.5


def test_answer_quality_judge_excludes_low_similarity_refusals() -> None:
    # If retrieval refused, the judge never spoke — exclude from this metric.
    results = [
        _result(
            "q1",
            "factoid",
            [1],
            [],
            response_status="refused",
            refusal_cause="low_similarity",
        ),
        _result("q2", "factoid", [1], [1, 2]),
    ]
    value, n = compute_answer_quality_judge(results)
    assert n == 1
    assert value == 1.0


def test_answer_quality_judge_skips_out_of_scope() -> None:
    results = [
        _result(
            "q-oos",
            "out_of_scope",
            [],
            [],
            response_status="refused",
            refusal_cause="low_similarity",
        ),
    ]
    value, n = compute_answer_quality_judge(results)
    assert n == 0
    assert value == 0.0


# ---- Loader --------------------------------------------------------------


def test_load_questions_parses_committed_set() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    questions = load_questions(repo_root / "evals" / "questions.jsonl")
    assert len(questions) >= 10, "Article III.1 requires at least 10 questions"
    categories = {q.category for q in questions}
    assert "factoid" in categories
    assert "out_of_scope" in categories
    # IDs unique.
    ids = [q.id for q in questions]
    assert len(set(ids)) == len(ids)


def test_load_questions_rejects_malformed_lines(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id":"q1"}\n', encoding="utf-8")  # missing question/category
    try:
        load_questions(bad)
    except ValueError as exc:
        assert "missing required field" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


# ---- Reporters -----------------------------------------------------------


def _summary_fixture() -> EvalSummary:
    from datetime import datetime

    results = [
        _result("q1", "factoid", [1], [1, 2]),
        _result("q2", "factoid", [3], [3, 4]),
        _result(
            "q-oos",
            "out_of_scope",
            [],
            [],
            response_status="refused",
            refusal_cause="low_similarity",
        ),
    ]
    return EvalSummary(
        timestamp=datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC),
        n_total=3,
        n_factoid_or_synthesis=2,
        n_out_of_scope=1,
        recall_at_5=1.0,
        mrr=1.0,
        refusal_precision=1.0,
        answer_quality_judge=1.0,
        per_question=results,
        model_versions={
            "embedding": "gemini-embedding-001@768",
            "generation": "gemini-2.5-flash",
            "judge": "gemini-2.5-flash-lite",
        },
    )


def test_write_jsonl_emits_metric_rows_and_per_question(tmp_path: Path) -> None:
    out = tmp_path / "results.jsonl"
    write_jsonl(_summary_fixture(), out)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line]
    metric_rows = [r for r in rows if r.get("metric")]
    per_q_rows = [r for r in rows if r.get("type") == "per_question"]
    metric_names = {r["metric"] for r in metric_rows}
    assert metric_names == {"recall_at_5", "mrr", "answer_quality_judge", "refusal_precision"}
    assert len(per_q_rows) == 3


def test_write_markdown_has_headline_metrics(tmp_path: Path) -> None:
    out = tmp_path / "results.md"
    write_markdown(_summary_fixture(), out)
    body = out.read_text(encoding="utf-8")
    assert "Recall@5" in body
    assert "MRR" in body
    assert "Refusal precision" in body
    assert "answer_quality" in body.lower() or "judge" in body.lower()
