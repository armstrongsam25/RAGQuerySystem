"""DOCX text extractor — produces the same `list[tuple[int, str]]` interface
as pdf.py so the ingest pipeline works without changes.

Uses `python-docx` for .docx files. Each page is emulated as ~55 lines
of text (roughly one printed page) since DOCX has no inherent page breaks.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

_DOCX_PAGE_BREAK_LINES = 55  # ~one printed page
_EXECUTOR = ThreadPoolExecutor(max_workers=4)


def _extract_docx_text_raw(pdf_bytes: bytes) -> list[str]:
    """Extract paragraphs from a .docx file. Runs in a thread pool.

    Each paragraph becomes its own "line"; empty paragraphs are skipped.
    """
    try:
        from docx import Document
        from io import BytesIO
    except ImportError:
        raise ImportError(
            "python-docx is required for DOCX support. "
            "Install with: pip install python-docx"
        )

    doc = Document(BytesIO(pdf_bytes))
    paragraphs: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _paragraphs_to_pages(paragraphs: list[str], lines_per_page: int = _DOCX_PAGE_BREAK_LINES) -> list[tuple[int, str]]:
    """Group paragraphs into page-like chunks."""
    if not paragraphs:
        return []

    pages: list[tuple[int, str]] = []
    current_lines: list[str] = []
    line_count = 0

    for para in paragraphs:
        # Estimate paragraph lines at ~80 chars per line
        para_lines = max(1, (len(para) + 79) // 80)
        if line_count + para_lines > lines_per_page and current_lines:
            pages.append((len(pages) + 1, "\n\n".join(current_lines)))
            current_lines = []
            line_count = 0
        current_lines.append(para)
        line_count += para_lines

    if current_lines:
        pages.append((len(pages) + 1, "\n\n".join(current_lines)))

    return pages


async def extract_docx_pages(
    pdf_bytes: bytes,
    *,
    concurrency: int = 2,
) -> list[tuple[int, str]]:
    """Async wrapper for DOCX extraction — matches the pdf.extract_pages signature.

    ``concurrency`` is accepted for interface compatibility but unused
    (DOCX extraction is single-threaded I/O on the bytes).
    """
    loop = asyncio.get_running_loop()
    paragraphs = await loop.run_in_executor(_EXECUTOR, _extract_docx_text_raw, pdf_bytes)
    return _paragraphs_to_pages(paragraphs)