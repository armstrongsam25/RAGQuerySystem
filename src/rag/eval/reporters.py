"""Serializers for eval output — JSONL for tools, Markdown for humans."""

from __future__ import annotations

import json
from pathlib import Path

from rag.eval.models import EvalSummary, MetricRow


def _metric_rows(summary: EvalSummary) -> list[MetricRow]:
    ts = summary.timestamp.isoformat()
    rows: list[MetricRow] = []
    if summary.n_factoid_or_synthesis:
        rows.append(
            MetricRow(
                metric="recall_at_5",
                value=summary.recall_at_5,
                n_questions=summary.n_factoid_or_synthesis,
                model_versions=summary.model_versions,
                timestamp=ts,
            )
        )
        rows.append(
            MetricRow(
                metric="mrr",
                value=summary.mrr,
                n_questions=summary.n_factoid_or_synthesis,
                model_versions=summary.model_versions,
                timestamp=ts,
            )
        )
        rows.append(
            MetricRow(
                metric="answer_quality_judge",
                value=summary.answer_quality_judge,
                n_questions=summary.n_factoid_or_synthesis,
                model_versions=summary.model_versions,
                timestamp=ts,
            )
        )
    if summary.n_out_of_scope:
        rows.append(
            MetricRow(
                metric="refusal_precision",
                value=summary.refusal_precision,
                n_questions=summary.n_out_of_scope,
                model_versions=summary.model_versions,
                timestamp=ts,
            )
        )
    return rows


def write_jsonl(summary: EvalSummary, path: Path) -> None:
    """Write one metric per line, plus a final ``per_question`` row.

    Per-question details land as a single object with ``type=per_question``
    so a downstream consumer can ``jq 'select(.metric)'`` to get just the
    metric rows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for row in _metric_rows(summary):
        lines.append(
            json.dumps(
                {
                    "metric": row.metric,
                    "value": round(row.value, 4),
                    "n_questions": row.n_questions,
                    "model_versions": row.model_versions,
                    "timestamp": row.timestamp,
                }
            )
        )
    for result in summary.per_question:
        lines.append(
            json.dumps(
                {
                    "type": "per_question",
                    "question_id": result.question_id,
                    "category": result.category,
                    "expected_pages": result.expected_pages,
                    "retrieved_pages": result.retrieved_pages,
                    "response_status": result.response_status,
                    "refusal_cause": result.refusal_cause,
                    "citation_pages": result.citation_pages,
                }
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_markdown(summary: EvalSummary, path: Path) -> None:
    """Human-readable summary, linked from the README."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Eval results")
    lines.append("")
    lines.append(f"**Run timestamp**: {summary.timestamp.isoformat()}")
    lines.append(
        f"**Questions**: {summary.n_total} total · "
        f"{summary.n_factoid_or_synthesis} retrieval · {summary.n_out_of_scope} out-of-scope"
    )
    lines.append("**Model versions**:")
    for k, v in summary.model_versions.items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Headline metrics")
    lines.append("")
    lines.append("| Metric | Value | n |")
    lines.append("|---|---|---|")
    if summary.n_factoid_or_synthesis:
        lines.append(f"| Recall@5 | {summary.recall_at_5:.3f} | {summary.n_factoid_or_synthesis} |")
        lines.append(f"| MRR | {summary.mrr:.3f} | {summary.n_factoid_or_synthesis} |")
        lines.append(
            f"| Answer quality (judge) | {summary.answer_quality_judge:.3f} "
            f"| {summary.n_factoid_or_synthesis} |"
        )
    if summary.n_out_of_scope:
        lines.append(
            f"| Refusal precision | {summary.refusal_precision:.3f} | {summary.n_out_of_scope} |"
        )
    lines.append("")
    lines.append("## Per-question detail")
    lines.append("")
    lines.append("| ID | Category | Expected pages | Retrieved (top-5) | Status | Refusal cause |")
    lines.append("|---|---|---|---|---|---|")
    for r in summary.per_question:
        expected = ", ".join(str(p) for p in r.expected_pages) or "—"
        retrieved = ", ".join(str(p) for p in r.retrieved_pages) or "—"
        cause = r.refusal_cause or "—"
        lines.append(
            f"| {r.question_id} | {r.category} | {expected} | {retrieved} "
            f"| {r.response_status} | {cause} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
