"""Citation-construction tests (Art VI.2 + FR-025 + research R-015/R-016)."""

from __future__ import annotations

from uuid import uuid4

from rag.providers.base import JudgeVerdict
from rag.query.citations import build_citations
from rag.repositories.base import ChunkRecord, RetrievedChunk


def _make_retrieved(text: str, page: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        record=ChunkRecord(
            id=uuid4(),
            source_document_id=uuid4(),
            page_number=page,
            char_offset_start=0,
            char_offset_end=len(text),
            raw_text=text,
            token_count=10,
            embedding=[0.1, 0.2, 0.3],
        ),
        similarity=0.9,
    )


def test_supporting_sentences_join_into_quoted_span():
    rc = _make_retrieved(
        "First sentence. Second sentence here. Third sentence ends.",
    )
    verdict = JudgeVerdict(entailed=True, supports={"p0": [0, 1]})
    citations = build_citations(verdict=verdict, retrieved=[rc], span_max=400)
    assert len(citations) == 1
    c = citations[0]
    assert "First sentence." in c.quoted_span
    assert "Second sentence here." in c.quoted_span
    assert c.truncated is False
    assert c.page_number == 1


def test_truncation_at_word_boundary_with_ellipsis():
    # Build a long supporting sentence whose join exceeds the cap.
    long_text = " ".join(f"word{i:03d}" for i in range(200)) + "."
    rc = _make_retrieved(long_text)
    verdict = JudgeVerdict(entailed=True, supports={"p0": [0]})
    citations = build_citations(verdict=verdict, retrieved=[rc], span_max=100)
    assert len(citations) == 1
    c = citations[0]
    assert c.truncated is True
    assert c.quoted_span.endswith("…")
    assert len(c.quoted_span) <= 101  # 100 + ellipsis
    # Must not break mid-word (the char before the ellipsis is not letter-then-cut).
    assert " " not in c.quoted_span[-2:-1] or c.quoted_span[-2:-1] == ""


def test_passages_with_empty_supports_are_dropped():
    rc1 = _make_retrieved("Relevant passage. With evidence.", page=1)
    rc2 = _make_retrieved("Irrelevant passage. No evidence here.", page=2)
    rc3 = _make_retrieved("Another irrelevant one.", page=3)
    # Judge supports only p0 (the first retrieved chunk).
    verdict = JudgeVerdict(entailed=True, supports={"p0": [0]})
    citations = build_citations(verdict=verdict, retrieved=[rc1, rc2, rc3], span_max=400)
    assert len(citations) == 1
    assert citations[0].page_number == 1


def test_no_supports_returns_empty_list():
    """Drives the R-016 degenerate-verdict recovery in the pipeline."""
    rc = _make_retrieved("Some passage.")
    verdict = JudgeVerdict(entailed=True, supports={})
    citations = build_citations(verdict=verdict, retrieved=[rc], span_max=400)
    assert citations == []


def test_invalid_sentence_indices_silently_ignored():
    rc = _make_retrieved("Only one sentence here.")
    # Indices 5 and 10 don't exist in this single-sentence passage.
    verdict = JudgeVerdict(entailed=True, supports={"p0": [5, 10]})
    citations = build_citations(verdict=verdict, retrieved=[rc], span_max=400)
    # No valid supporting sentences → drop the citation.
    assert citations == []
