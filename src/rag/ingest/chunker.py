"""Page-bounded chunker.

Load-bearing invariants (Art II + research R-011):

  * Page-bounded: a chunk never spans two pages. `page_number` is unambiguous;
    `char_offset_start`/`char_offset_end` are offsets into that page's
    extracted text.
  * Word-bounded: chunks always land on token boundaries — never mid-word.
  * Overlap is by token count, expressed as offset overlap between adjacent
    chunks rather than by mutating `raw_text`.

Algorithm:
  1. Tokenize the page with `tiktoken.cl100k_base`. tiktoken gives us token
     ids; we use the byte-offset stream `encode_with_offsets`-equivalent by
     iteratively decoding chunks of token ids back to text and locating them
     in the original string.
  2. Walk the token sequence, packing tokens into chunks of ≤ `target_tokens`,
     starting each new chunk at `target_tokens - overlap_tokens` positions
     after the previous chunk's start.
  3. Snap each chunk's start/end to whitespace boundaries in the source text.
     Token boundaries are character-level (BPE), so a token can land mid-word;
     the whitespace snap is what produces "no mid-word breaks for citations."
  4. `raw_text = page_text[char_offset_start:char_offset_end]`.

`tiktoken.cl100k_base` is a documented approximation of Gemini's tokenizer
— empirically within ~10% on English prose at our 600-token target.
"""

from __future__ import annotations

from uuid import UUID

import tiktoken

from rag.repositories.base import ChunkRecord

_DEFAULT_TARGET_TOKENS = 600
_DEFAULT_OVERLAP_TOKENS = 80

_ENC = tiktoken.get_encoding("cl100k_base")

# Placeholder source_document_id used while the chunker runs; the ingest
# pipeline reassigns each chunk's source_document_id before persistence.
_PLACEHOLDER_DOC_ID = UUID("00000000-0000-0000-0000-000000000000")


def _count_tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _snap_left_to_word(text: str, pos: int) -> int:
    """Move `pos` left until it sits at a whitespace boundary or at 0."""
    if pos <= 0:
        return 0
    if pos >= len(text):
        return len(text)
    # If pos already at whitespace boundary, scan back through whitespace.
    # If pos lands mid-word, walk back to the nearest whitespace.
    while pos > 0 and not text[pos - 1].isspace():
        pos -= 1
    # Now skip any leading whitespace so the chunk starts on a word char.
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _snap_right_to_word(text: str, pos: int) -> int:
    """Move `pos` right until it sits at a whitespace boundary or at len(text)."""
    if pos >= len(text):
        return len(text)
    if pos <= 0:
        return 0
    # If we're inside a word, advance to the next whitespace.
    while pos < len(text) and not text[pos].isspace():
        pos += 1
    return pos


def chunk_page(
    *,
    page_text: str,
    page_number: int,
    target_tokens: int = _DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = _DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkRecord]:
    """Chunk one page's plaintext into page-bounded, word-bounded chunks."""
    page_text = page_text or ""
    if not page_text.strip():
        return []

    total_tokens = _count_tokens(page_text)
    if total_tokens <= target_tokens:
        return [
            ChunkRecord(
                source_document_id=_PLACEHOLDER_DOC_ID,
                page_number=page_number,
                char_offset_start=0,
                char_offset_end=len(page_text),
                raw_text=page_text,
                token_count=total_tokens,
            )
        ]

    # Tokenize once; walk by token indices, mapping back to character offsets.
    token_ids = _ENC.encode(page_text)
    # `step` is how far the next chunk's start advances. Must be >= 1 and
    # strictly less than target_tokens so we make forward progress.
    step = max(1, target_tokens - overlap_tokens)

    records: list[ChunkRecord] = []
    n = len(token_ids)
    cursor = 0
    while cursor < n:
        end = min(cursor + target_tokens, n)
        # Decode the token slice to text, find its char offset in the page.
        chunk_text = _ENC.decode(token_ids[cursor:end])
        # Find chunk_text in page_text starting from a hint position. The hint
        # is a coarse mapping cursor_tokens → cursor_chars; we use the actual
        # `find` to land on the real position.
        hint = 0 if not records else records[-1].char_offset_start
        found = page_text.find(chunk_text, hint)
        if found < 0:
            # Decoded text didn't match exactly (BPE round-trip can normalize
            # whitespace). Fall back to a more forgiving search by the first
            # token's decoded form.
            first_token_text = _ENC.decode([token_ids[cursor]])
            found = page_text.find(first_token_text.strip(), hint)
            if found < 0:
                found = hint
            chunk_text = page_text[found : found + len(chunk_text)]

        char_start = _snap_left_to_word(page_text, found)
        char_end = _snap_right_to_word(page_text, found + len(chunk_text))

        if char_end <= char_start:
            # Pathological — skip rather than emit a zero-length chunk.
            cursor = end
            continue

        raw = page_text[char_start:char_end]
        records.append(
            ChunkRecord(
                source_document_id=_PLACEHOLDER_DOC_ID,
                page_number=page_number,
                char_offset_start=char_start,
                char_offset_end=char_end,
                raw_text=raw,
                token_count=_count_tokens(raw),
            )
        )

        if end >= n:
            break
        cursor += step

    return records


def chunk_pages(
    pages: list[tuple[int, str]],
    *,
    target_tokens: int = _DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = _DEFAULT_OVERLAP_TOKENS,
) -> list[ChunkRecord]:
    """Chunk multiple pages independently. Page boundaries are never crossed."""
    out: list[ChunkRecord] = []
    for page_number, text in pages:
        out.extend(
            chunk_page(
                page_text=text,
                page_number=page_number,
                target_tokens=target_tokens,
                overlap_tokens=overlap_tokens,
            )
        )
    return out
