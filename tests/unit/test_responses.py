"""Pydantic-level invariant tests for query responses (spec FR-013)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from rag.query.responses import (
    Citation,
    QueryAnswered,
    QueryNoDocuments,
    QueryRefused,
)


def _citation() -> Citation:
    return Citation(
        chunk_id=uuid4(),
        source_document_id=uuid4(),
        page_number=1,
        quoted_span="example",
        truncated=False,
    )


def test_answered_requires_at_least_one_citation():
    """FR-013: answered ↔ ≥1 citation."""
    with pytest.raises(ValidationError):
        QueryAnswered(
            answer="hello",
            citations=[],
            model="gemini-2.5-flash",
            trace_id="t",
        )


def test_answered_with_citation_ok():
    r = QueryAnswered(
        answer="hello",
        citations=[_citation()],
        model="gemini-2.5-flash",
        trace_id="t",
    )
    assert r.status == "answered"
    assert len(r.citations) == 1


def test_refused_rejects_citations_field():
    """FR-013: refused ↔ 0 citations — enforced by extra='forbid'."""
    with pytest.raises(ValidationError):
        QueryRefused.model_validate(
            {
                "status": "refused",
                "message": "no",
                "refusal_cause": "low_similarity",
                "model": "x",
                "trace_id": "t",
                "citations": [_citation().model_dump()],  # forbidden
            }
        )


def test_refusal_cause_enum_accepts_three_values():
    """Spec FR-015 (updated): three refusal causes."""
    for cause in ("low_similarity", "failed_grounding_check", "judge_no_supporting_spans"):
        r = QueryRefused(
            message="x",
            refusal_cause=cause,
            model="m",
            trace_id="t",
        )
        assert r.refusal_cause == cause


def test_refusal_cause_rejects_unknown_value():
    with pytest.raises(ValidationError):
        QueryRefused(
            message="x",
            refusal_cause="not_a_real_cause",  # type: ignore[arg-type]
            model="m",
            trace_id="t",
        )


def test_quoted_span_length_capped_at_401():
    """400-char cap + ellipsis = 401 (per R-016)."""
    with pytest.raises(ValidationError):
        Citation(
            chunk_id=uuid4(),
            source_document_id=uuid4(),
            page_number=1,
            quoted_span="x" * 402,
            truncated=True,
        )


def test_no_documents_response_minimum_shape():
    r = QueryNoDocuments(message="empty", trace_id="t")
    assert r.status == "no_documents"
