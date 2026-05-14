"""Refusal-path tests (Art VI.2 + FR-025 + spec FR-010/FR-012/FR-014).

Covers all four "non-answered" outcomes:
  * no_documents (FR-014)
  * refused / low_similarity (FR-010)
  * refused / failed_grounding_check (FR-012)
  * refused / judge_no_supporting_spans (R-016 degenerate recovery)
"""

from __future__ import annotations

import pytest

from rag.providers.base import JudgeVerdict, Providers
from rag.query.pipeline import answer_question
from rag.query.responses import QueryAnswered, QueryNoDocuments, QueryRefused
from tests.conftest import FakeProvider


@pytest.mark.asyncio
async def test_empty_corpus_returns_no_documents(memory_repo, small_dim_settings):
    embedder = FakeProvider(embed=lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    generator = FakeProvider(complete="should not be called")
    judge = FakeProvider(judge=lambda **_kw: JudgeVerdict(entailed=True, supports={}))
    providers = Providers(embedder=embedder, generator=generator, judge=judge)

    response = await answer_question(
        "What is the capital of France?",
        repo=memory_repo,
        providers=providers,
        settings=small_dim_settings,
        trace_id="trace-empty",
    )
    assert isinstance(response, QueryNoDocuments)
    assert response.status == "no_documents"
    assert "rag ingest" in response.message
    # Embedder should NOT have been called when the corpus is empty.
    assert embedder.embed_calls == []
    assert generator.complete_calls == []


@pytest.mark.asyncio
async def test_low_similarity_short_circuits_before_generation(
    seeded_repo, small_dim_settings, monkeypatch
):
    # Force RAG_SIM_FLOOR=0.99 so no fixture chunk clears the floor.
    monkeypatch.setenv("RAG_SIM_FLOOR", "0.99")
    from rag.config import Settings, get_settings

    get_settings.cache_clear()
    settings = Settings()  # type: ignore[call-arg]

    embedder = FakeProvider(embed=lambda texts: [[0.5, 0.5, 0.5] for _ in texts])
    generator = FakeProvider(complete="should not be called")
    judge = FakeProvider(judge=lambda **_kw: JudgeVerdict(entailed=True, supports={"p0": [0]}))
    providers = Providers(embedder=embedder, generator=generator, judge=judge)

    response = await answer_question(
        "Nothing in scope here.",
        repo=seeded_repo,
        providers=providers,
        settings=settings,
        trace_id="trace-low-sim",
    )
    assert isinstance(response, QueryRefused)
    assert response.refusal_cause == "low_similarity"
    # Critical: generation MUST NOT have been called (FR-010).
    assert generator.complete_calls == []
    assert judge.judge_calls == []


@pytest.mark.asyncio
async def test_failed_grounding_check_refuses(seeded_repo, small_dim_settings):
    embedder = FakeProvider(embed=lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    generator = FakeProvider(complete="A fabricated answer.")
    judge = FakeProvider(
        judge=lambda **_kw: JudgeVerdict(entailed=False, supports={}, reason="drift")
    )
    providers = Providers(embedder=embedder, generator=generator, judge=judge)

    response = await answer_question(
        "Tell me something.",
        repo=seeded_repo,
        providers=providers,
        settings=small_dim_settings,
        trace_id="trace-failed-grounding",
    )
    assert isinstance(response, QueryRefused)
    assert response.refusal_cause == "failed_grounding_check"
    assert generator.complete_calls  # generation WAS called (judge gates after)
    assert judge.judge_calls


@pytest.mark.asyncio
async def test_judge_no_supporting_spans_degenerate_recovery(seeded_repo, small_dim_settings):
    """R-016: entailed=True but supports={} → recover as refused."""
    embedder = FakeProvider(embed=lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    generator = FakeProvider(complete="Paris is the capital of France.")
    judge = FakeProvider(
        judge=lambda **_kw: JudgeVerdict(entailed=True, supports={}, reason="vague")
    )
    providers = Providers(embedder=embedder, generator=generator, judge=judge)

    response = await answer_question(
        "What is the capital of France?",
        repo=seeded_repo,
        providers=providers,
        settings=small_dim_settings,
        trace_id="trace-no-spans",
    )
    assert isinstance(response, QueryRefused)
    assert response.refusal_cause == "judge_no_supporting_spans"


@pytest.mark.asyncio
async def test_refused_response_has_no_citations_field(seeded_repo, small_dim_settings):
    """Pydantic-level enforcement of FR-013's 'refused → no citations'."""
    embedder = FakeProvider(embed=lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    generator = FakeProvider(complete="Some answer.")
    judge = FakeProvider(judge=lambda **_kw: JudgeVerdict(entailed=False, supports={}))
    providers = Providers(embedder=embedder, generator=generator, judge=judge)

    response = await answer_question(
        "Question.",
        repo=seeded_repo,
        providers=providers,
        settings=small_dim_settings,
        trace_id="trace-no-cit-field",
    )
    assert isinstance(response, QueryRefused)
    dumped = response.model_dump()
    assert "citations" not in dumped


@pytest.mark.asyncio
async def test_empty_question_raises_value_error(memory_repo, small_dim_settings):
    providers = Providers(
        embedder=FakeProvider(),
        generator=FakeProvider(),
        judge=FakeProvider(),
    )
    with pytest.raises(ValueError):
        await answer_question(
            "   \n\n  ",
            repo=memory_repo,
            providers=providers,
            settings=small_dim_settings,
            trace_id="trace-empty-q",
        )


@pytest.mark.asyncio
async def test_question_too_long_raises_value_error(memory_repo, small_dim_settings):
    providers = Providers(
        embedder=FakeProvider(),
        generator=FakeProvider(),
        judge=FakeProvider(),
    )
    too_long = "x" * (small_dim_settings.RAG_QUESTION_MAX_LEN + 1)
    with pytest.raises(ValueError):
        await answer_question(
            too_long,
            repo=memory_repo,
            providers=providers,
            settings=small_dim_settings,
            trace_id="trace-too-long",
        )


@pytest.mark.asyncio
async def test_answered_response_imports_correctly(seeded_repo, small_dim_settings):
    """Sanity check that the happy-path glue from US1 also lights up."""
    embedder = FakeProvider(embed=lambda texts: [[1.0, 0.0, 0.0] for _ in texts])
    generator = FakeProvider(complete="The capital of France is Paris.")
    judge = FakeProvider(judge=lambda **_kw: JudgeVerdict(entailed=True, supports={"p0": [0]}))
    providers = Providers(embedder=embedder, generator=generator, judge=judge)

    response = await answer_question(
        "What is the capital of France?",
        repo=seeded_repo,
        providers=providers,
        settings=small_dim_settings,
        trace_id="trace-happy",
    )
    assert isinstance(response, QueryAnswered)
    assert len(response.citations) >= 1
    assert response.answer == "The capital of France is Paris."
    assert response.model == small_dim_settings.GENERATION_MODEL
