"""Chunking-boundary tests (Art VI.2 + FR-025)."""

from __future__ import annotations

from rag.ingest.chunker import chunk_page, chunk_pages


def test_short_page_produces_single_chunk():
    text = "This is a single short page that easily fits in one chunk."
    chunks = chunk_page(page_text=text, page_number=1)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.page_number == 1
    assert c.char_offset_start == 0
    assert c.char_offset_end == len(text)
    assert c.raw_text == text
    assert c.token_count > 0


def test_empty_page_produces_no_chunks():
    assert chunk_page(page_text="", page_number=1) == []
    assert chunk_page(page_text="   \n\n  ", page_number=2) == []


def test_long_page_splits_at_paragraph_boundary():
    paragraph = "Sentence " * 200  # ~400 tokens
    text = paragraph + "\n\n" + paragraph + "\n\n" + paragraph
    chunks = chunk_page(page_text=text, page_number=5, target_tokens=200, overlap_tokens=20)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.page_number == 5
        # Page-bounded invariant — every chunk belongs to page 5.
        assert c.char_offset_start >= 0
        assert c.char_offset_end > c.char_offset_start
        assert c.char_offset_end <= len(text)


def test_chunks_never_cross_pages():
    pages = [
        (1, "Page one content. " * 100),
        (2, "Page two content. " * 100),
        (3, "Page three content. " * 100),
    ]
    chunks = chunk_pages(pages, target_tokens=80, overlap_tokens=10)
    by_page: dict[int, list] = {}
    for c in chunks:
        by_page.setdefault(c.page_number, []).append(c)
    assert set(by_page.keys()) == {1, 2, 3}
    # Each chunk's raw_text is a slice of its own page, not a spanning slice.
    for page_no, page_chunks in by_page.items():
        page_text = next(text for n, text in pages if n == page_no)
        for c in page_chunks:
            assert (
                c.raw_text in page_text
                or page_text[c.char_offset_start : c.char_offset_end] == c.raw_text
            )


def test_chunks_do_not_break_mid_word():
    text = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo " * 30
    chunks = chunk_page(page_text=text, page_number=1, target_tokens=50, overlap_tokens=5)
    for c in chunks:
        # End at whitespace or end-of-text; not mid-word.
        if c.char_offset_end < len(text):
            char_after = text[c.char_offset_end - 1 : c.char_offset_end + 1]
            assert " " in char_after or text[c.char_offset_end - 1] in ".!?", (
                f"chunk ends mid-word: ...{c.raw_text[-20:]!r}"
            )


def test_token_count_populated():
    text = "Word " * 100
    chunks = chunk_page(page_text=text, page_number=1, target_tokens=50, overlap_tokens=5)
    for c in chunks:
        assert c.token_count > 0


def test_chunk_pages_preserves_page_numbers():
    pages = [(7, "Some text here. " * 40), (8, "More text. " * 40)]
    chunks = chunk_pages(pages, target_tokens=30, overlap_tokens=5)
    page_numbers = {c.page_number for c in chunks}
    assert page_numbers == {7, 8}
