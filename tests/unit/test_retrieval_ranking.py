"""Retrieval-ranking tests (Art VI.2 + FR-025)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_ranking_orders_by_descending_similarity(seeded_repo):
    # Query vector closest to chunk 1 (cosine 1.0), then chunk 2 (0.0).
    results = await seeded_repo.search([1.0, 0.0, 0.0], k=3, sim_floor=0.0)
    sims = [r.similarity for r in results]
    assert sims == sorted(sims, reverse=True)
    assert results[0].record.page_number == 1
    assert results[0].similarity == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_sim_floor_excludes_below_threshold(seeded_repo):
    # Query closest to chunk 1; threshold 0.5 should exclude chunks 2 and 3 (sim 0).
    results = await seeded_repo.search([1.0, 0.0, 0.0], k=10, sim_floor=0.5)
    assert len(results) == 1
    assert results[0].record.page_number == 1


@pytest.mark.asyncio
async def test_k_caps_returned_count(memory_repo, fixture_doc_id):
    from rag.repositories.base import ChunkRecord

    chunks = []
    for i in range(10):
        chunks.append(
            ChunkRecord(
                source_document_id=fixture_doc_id,
                page_number=i + 1,
                char_offset_start=0,
                char_offset_end=10,
                raw_text=f"chunk{i}",
                token_count=1,
                embedding=[1.0, 0.0, 0.0],
            )
        )
    await memory_repo.add_chunks(chunks, source_document_id=fixture_doc_id)
    results = await memory_repo.search([1.0, 0.0, 0.0], k=3, sim_floor=0.0)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_null_embeddings_excluded(memory_repo, fixture_doc_id):
    from rag.repositories.base import ChunkRecord

    chunks = [
        ChunkRecord(
            source_document_id=fixture_doc_id,
            page_number=1,
            char_offset_start=0,
            char_offset_end=10,
            raw_text="with-emb",
            token_count=1,
            embedding=[1.0, 0.0, 0.0],
        ),
        ChunkRecord(
            source_document_id=fixture_doc_id,
            page_number=2,
            char_offset_start=0,
            char_offset_end=10,
            raw_text="without-emb",
            token_count=1,
            embedding=None,
        ),
    ]
    await memory_repo.add_chunks(chunks, source_document_id=fixture_doc_id)
    results = await memory_repo.search([1.0, 0.0, 0.0], k=10, sim_floor=0.0)
    assert len(results) == 1
    assert results[0].record.raw_text == "with-emb"


@pytest.mark.asyncio
async def test_empty_corpus_returns_nothing(memory_repo):
    results = await memory_repo.search([1.0, 0.0, 0.0], k=5, sim_floor=0.0)
    assert results == []
    assert await memory_repo.has_any_chunks() is False


@pytest.mark.asyncio
async def test_has_any_chunks_true_after_insert(seeded_repo):
    assert await seeded_repo.has_any_chunks() is True


@pytest.mark.asyncio
async def test_add_chunks_is_idempotent(memory_repo, fixture_doc_id):
    from rag.repositories.base import ChunkRecord

    chunk = ChunkRecord(
        source_document_id=fixture_doc_id,
        page_number=1,
        char_offset_start=0,
        char_offset_end=10,
        raw_text="dup",
        token_count=1,
        embedding=[1.0, 0.0, 0.0],
    )
    first = await memory_repo.add_chunks([chunk], source_document_id=fixture_doc_id)
    second = await memory_repo.add_chunks([chunk], source_document_id=fixture_doc_id)
    assert first == 1
    assert second == 0
