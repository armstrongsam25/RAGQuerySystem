"""PDF page enumeration + per-page text extraction.

Supports two extraction backends:

- Gemini File API (GeminiProvider.extract_page_text): vision-based,
  works for scanned PDFs but requires a Gemini API key.
- pypdf local extraction (OpenAIProvider.extract_page_text): text-native
  PDFs only, no API key needed. Falls back to pypdf for any provider
  that isn't GeminiProvider.

The ingest pipeline passes whatever provider it receives; the module
picks the right backend at call time based on the provider type.
"""

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
    """Extract every page's plaintext via Gemini File API, bounded-concurrent."""
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


async def extract_pages(
    pdf_bytes: bytes,
    *,
    provider: object,
    concurrency: int,
) -> list[tuple[int, str]]:
    """Extract every page's plaintext using the best available backend.

    If ``provider`` is a GeminiProvider, delegates to
    ``extract_pages_via_gemini`` for vision-based extraction.
    Otherwise falls back to pypdf local extraction (text-native PDFs only).
    """
    if isinstance(provider, GeminiProvider):
        return await extract_pages_via_gemini(
            pdf_bytes, gemini=provider, concurrency=concurrency
        )

    # Local pypdf-based extraction for OpenAI-compatible providers.
    # Works well for text-native PDFs; won't OCR scanned pages.
    n_pages = enumerate_pages(pdf_bytes)
    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[int, str]] = [(0, "")] * n_pages

    async def _one(idx: int) -> None:
        page_no = idx + 1
        async with sem:
            text = await provider.extract_page_text(pdf_bytes, page_no)
        results[idx] = (page_no, text)

    await asyncio.gather(*(_one(i) for i in range(n_pages)))
    return results