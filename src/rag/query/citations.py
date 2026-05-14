"""Citation construction from the judge's verdict (R-015 + R-016)."""

from __future__ import annotations

from rag.providers.base import JudgeVerdict
from rag.query.prompts import split_sentences
from rag.query.responses import Citation
from rag.repositories.base import RetrievedChunk


def _truncate_at_word(text: str, max_chars: int) -> tuple[str, bool]:
    """Truncate `text` to at most `max_chars`, breaking at word boundary.

    Appends a single Unicode ellipsis on truncation. Returns
    `(possibly-truncated text, truncated_flag)`.
    """
    if len(text) <= max_chars:
        return text, False
    # Reserve one char for the ellipsis.
    budget = max_chars
    # Find the last whitespace before `budget` chars.
    cut = text.rfind(" ", 0, budget)
    if cut < budget // 2:  # whitespace was way too far back; cut hard.
        cut = budget
    return text[:cut].rstrip() + "…", True


def build_citations(
    *,
    verdict: JudgeVerdict,
    retrieved: list[RetrievedChunk],
    span_max: int,
) -> list[Citation]:
    """Build the API citation list from a judge verdict + retrieved chunks.

    For each retrieved chunk: look up its supporting sentences. If empty,
    drop the citation. Otherwise join the named sentences, truncate to
    span_max chars at a word boundary if needed, and emit a `Citation`.
    """
    citations: list[Citation] = []
    for i, rc in enumerate(retrieved):
        passage_id = f"p{i}"
        idx_list = verdict.supports.get(passage_id, [])
        if not idx_list:
            continue

        sentences = split_sentences(rc.record.raw_text)
        # Filter to valid indices (the judge parser already enforces this,
        # but be defensive against any future caller).
        supports = [s for j, s in enumerate(sentences) if j in idx_list]
        if not supports:
            continue

        joined = " ".join(s.strip() for s in supports).strip()
        if not joined:
            continue

        quoted_span, truncated = _truncate_at_word(joined, span_max)
        citations.append(
            Citation(
                chunk_id=rc.record.id,
                source_document_id=rc.record.source_document_id,
                page_number=rc.record.page_number,
                quoted_span=quoted_span,
                truncated=truncated,
            )
        )
    return citations
