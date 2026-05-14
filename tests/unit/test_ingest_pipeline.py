"""Ingest-pipeline tests with stubbed Gemini provider + in-memory repo."""

from __future__ import annotations

import io
from pathlib import Path

import pypdf
import pytest

from rag.ingest.pipeline import ingest_pdf
from rag.providers.base import UpstreamProviderError


class _FakeGemini:
    """Stub for GeminiProvider — embeds via repeating pattern, extracts canned text."""

    def __init__(
        self,
        *,
        page_texts: dict[int, str],
        embed_dim: int = 3,
        extract_raises_on_page: int | None = None,
    ) -> None:
        self._page_texts = page_texts
        self._embed_dim = embed_dim
        self._extract_raises_on_page = extract_raises_on_page
        self.embed_calls: list[list[str]] = []
        self.extract_calls: list[int] = []

    async def embed(self, texts):
        self.embed_calls.append(list(texts))
        # Deterministic non-zero vectors per text — content doesn't matter for ingest.
        return [[0.1 * (i + 1)] * self._embed_dim for i in range(len(texts))]

    async def extract_page_text(self, pdf_bytes: bytes, page_number: int) -> str:
        self.extract_calls.append(page_number)
        if self._extract_raises_on_page == page_number:
            raise UpstreamProviderError("gemini", RuntimeError(f"boom on page {page_number}"))
        return self._page_texts.get(page_number, "")


def _make_minimal_pdf(num_pages: int) -> bytes:
    """Construct a minimal valid PDF in-memory with `num_pages` blank pages."""
    writer = pypdf.PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_happy_path_ingests_chunks(tmp_path: Path, memory_repo, small_dim_settings):
    pdf_bytes = _make_minimal_pdf(2)
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(pdf_bytes)

    gemini = _FakeGemini(
        page_texts={1: "Page one text here.", 2: "Page two text here."},
        embed_dim=small_dim_settings.EMBEDDING_DIM,
    )
    outcome = await ingest_pdf(
        pdf_path,
        gemini=gemini,  # type: ignore[arg-type]
        repo=memory_repo,
        settings=small_dim_settings,
        trace_id="ingest-happy",
    )
    assert outcome.status == "ingested"
    assert outcome.pages == 2
    assert outcome.chunks_inserted >= 2  # at least one per page (page-bounded)
    assert await memory_repo.has_any_chunks() is True


@pytest.mark.asyncio
async def test_force_reingest_overwrites_prior_state(
    tmp_path: Path, memory_repo, small_dim_settings
):
    pdf_bytes = _make_minimal_pdf(2)
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(pdf_bytes)

    gemini = _FakeGemini(
        page_texts={1: "First version of page one.", 2: "First version of page two."},
        embed_dim=small_dim_settings.EMBEDDING_DIM,
    )

    first = await ingest_pdf(
        pdf_path,
        gemini=gemini,  # type: ignore[arg-type]
        repo=memory_repo,
        settings=small_dim_settings,
        trace_id="t-first",
    )
    assert first.status == "ingested"
    first_doc_id = first.source_document_id
    first_chunks = [c for c in memory_repo._chunks if c.source_document_id == first_doc_id]
    assert len(first_chunks) >= 2

    # Without force, a second ingest is a no-op.
    repeat = await ingest_pdf(
        pdf_path,
        gemini=gemini,  # type: ignore[arg-type]
        repo=memory_repo,
        settings=small_dim_settings,
        trace_id="t-repeat",
    )
    assert repeat.status == "already_done"

    # With force, the prior source_document is dropped and re-ingested from
    # scratch. The new source_document_id is fresh; the prior chunks are gone.
    forced = await ingest_pdf(
        pdf_path,
        gemini=gemini,  # type: ignore[arg-type]
        repo=memory_repo,
        settings=small_dim_settings,
        trace_id="t-force",
        force=True,
    )
    assert forced.status == "reingested"
    assert forced.source_document_id != first_doc_id
    assert forced.chunks_inserted >= 2
    # The old chunks must be gone.
    assert all(c.source_document_id != first_doc_id for c in memory_repo._chunks)


@pytest.mark.asyncio
async def test_force_on_never_ingested_pdf_is_normal_ingest(
    tmp_path: Path, memory_repo, small_dim_settings
):
    pdf_bytes = _make_minimal_pdf(1)
    pdf_path = tmp_path / "new.pdf"
    pdf_path.write_bytes(pdf_bytes)

    gemini = _FakeGemini(
        page_texts={1: "Brand new content."},
        embed_dim=small_dim_settings.EMBEDDING_DIM,
    )
    outcome = await ingest_pdf(
        pdf_path,
        gemini=gemini,  # type: ignore[arg-type]
        repo=memory_repo,
        settings=small_dim_settings,
        trace_id="t-force-fresh",
        force=True,
    )
    # No prior state to overwrite → normal "ingested", not "reingested".
    assert outcome.status == "ingested"


@pytest.mark.asyncio
async def test_re_ingest_is_no_op(tmp_path: Path, memory_repo, small_dim_settings):
    pdf_bytes = _make_minimal_pdf(1)
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(pdf_bytes)

    gemini = _FakeGemini(
        page_texts={1: "Page text."},
        embed_dim=small_dim_settings.EMBEDDING_DIM,
    )

    first = await ingest_pdf(
        pdf_path,
        gemini=gemini,  # type: ignore[arg-type]
        repo=memory_repo,
        settings=small_dim_settings,
        trace_id="ingest-1",
    )
    second = await ingest_pdf(
        pdf_path,
        gemini=gemini,  # type: ignore[arg-type]
        repo=memory_repo,
        settings=small_dim_settings,
        trace_id="ingest-2",
    )
    assert first.status == "ingested"
    assert second.status == "already_done"
    assert second.chunks_inserted == 0


@pytest.mark.asyncio
async def test_upstream_failure_propagates(tmp_path: Path, memory_repo, small_dim_settings):
    pdf_bytes = _make_minimal_pdf(3)
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(pdf_bytes)

    gemini = _FakeGemini(
        page_texts={1: "ok", 2: "ok", 3: "ok"},
        embed_dim=small_dim_settings.EMBEDDING_DIM,
        extract_raises_on_page=2,
    )
    with pytest.raises(UpstreamProviderError):
        await ingest_pdf(
            pdf_path,
            gemini=gemini,  # type: ignore[arg-type]
            repo=memory_repo,
            settings=small_dim_settings,
            trace_id="ingest-fail",
        )


@pytest.mark.asyncio
async def test_missing_file_raises(memory_repo, small_dim_settings):
    gemini = _FakeGemini(page_texts={}, embed_dim=small_dim_settings.EMBEDDING_DIM)
    with pytest.raises(FileNotFoundError):
        await ingest_pdf(
            Path("/definitely/not/a/real/path.pdf"),
            gemini=gemini,  # type: ignore[arg-type]
            repo=memory_repo,
            settings=small_dim_settings,
            trace_id="ingest-missing",
        )


@pytest.mark.asyncio
async def test_non_pdf_extension_raises(tmp_path: Path, memory_repo, small_dim_settings):
    txt_path = tmp_path / "not_a.pdf.txt"
    txt_path.write_text("hello")
    gemini = _FakeGemini(page_texts={}, embed_dim=small_dim_settings.EMBEDDING_DIM)
    with pytest.raises(ValueError):
        await ingest_pdf(
            txt_path,
            gemini=gemini,  # type: ignore[arg-type]
            repo=memory_repo,
            settings=small_dim_settings,
            trace_id="ingest-not-pdf",
        )
