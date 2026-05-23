"""Citation construction from the judge's verdict (R-015 + R-016)."""

from __future__ import annotations

import re

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
    source_file_hash: str = "",
) -> list[Citation]:
    """Build the API citation list from a judge verdict + retrieved chunks.

    For each retrieved chunk: look up its supporting sentences. If empty,
    drop the citation. Otherwise join the named sentences, truncate to
    span_max chars at a word boundary if needed, and emit a `Citation`.

    Citations are numbered 1..N in the order they appear — these reference
    numbers correspond to the [N] markers the LLM places in its answer.
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
                source_file_hash=source_file_hash,
                page_number=rc.record.page_number,
                quoted_span=quoted_span,
                truncated=truncated,
                ref_number=len(citations) + 1,
            )
        )
    return citations


# Regex for [N] or [N, M, ...] citation markers in LLM answer text.
_CITE_MARKER_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def answer_with_inline_citation_links(
    answer: str,
    citations: list[Citation],
) -> str:
    """Replace [N] markers in answer text with HTML links to citation anchors.

    Converts LLM-generated citation markers like [1] or [2, 3, 5] into
    clickable HTML `<a>` tags that jump to the corresponding citation
    entry in the sources list below. This makes every factual claim's
    citation clickable in the rendered answer.

    The HTML is safe because citation numbers are strictly integers.
    """
    # Build a lookup: ref_number -> Citation
    cite_by_ref: dict[int, Citation] = {c.ref_number: c for c in citations}

    def _replace_marker(match: re.Match[str]) -> str:
        raw = match.group(1)
        refs = [int(n.strip()) for n in raw.split(",")]
        links: list[str] = []
        for r in refs:
            if r in cite_by_ref:
                c = cite_by_ref[r]
                links.append(
                    f'<a href="#cite-{r}" class="cite-inline" '
                    f'title="See source — page {c.page_number}">[{r}]</a>'
                )
            else:
                links.append(f"[{r}]")
        return '<span class="cite-group">' + ", ".join(links) + "</span>"

    # Simple approach: just replace [N] markers
    return _CITE_MARKER_RE.sub(_replace_marker, answer)
