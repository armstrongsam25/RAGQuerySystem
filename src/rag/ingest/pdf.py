"""PDF page enumeration + per-page Gemini File API extraction (R-010)."""

from __future__ import annotations

import asyncio
import io

import pypdf

from rag.providers.gemini import GeminiProvider


def enumerate_pages(pdf_bytes: bytes) -> int:
    """Return the page count of a PDF."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages)


async def extract_pages_via_gemini(
    pdf_bytes: bytes,
    *,
    gemini: GeminiProvider,
    concurrency: int,
) -> list[tuple[int, str]]:
    """Extract every page's plaintext via Gemini File API, bounded-concurrent.

    Returns `[(page_number, text), ...]` in page order, even though calls
    are issued concurrently. Page numbers are 1-indexed (matching the chunk
    table's `page_number CHECK > 0` from feature 001).
    """
    n_pages = enumerate_pages(pdf_bytes)
    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[int, str]] = [(0, "")] * n_pages

    async def _one(idx: int) -> None:
        page_no = idx + 1
        async with sem:
            text = await gemini.extract_page_text(pdf_bytes, page_no)
        results[idx] = (page_no, text)

    await asyncio.gather(*(_one(i) for i in range(n_pages)))
    return results
