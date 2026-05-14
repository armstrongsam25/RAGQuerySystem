"""Query orchestrator.

One async function, four branches that map to four `status` values:

    answered          — happy path: retrieved, generated, judge said entailed.
    no_documents      — corpus is empty (spec FR-014).
    refused (low_similarity)            — sim-floor pre-filter caught it.
    refused (failed_grounding_check)    — judge said not entailed.
    refused (judge_no_supporting_spans) — judge said entailed but pointed
                                          at no sentences (R-016 recovery).
"""

from __future__ import annotations

import time

from rag.config import Settings
from rag.log import get_logger
from rag.providers.base import LLMProvider, Providers, UpstreamProviderError
from rag.query.citations import build_citations
from rag.query.prompts import (
    GENERATION_SYSTEM,
    build_generation_user_prompt,
    chunks_for_judging,
)
from rag.query.responses import (
    NO_DOCUMENTS_MESSAGE,
    REFUSAL_MESSAGE_FAILED_GROUNDING,
    REFUSAL_MESSAGE_JUDGE_NO_SPANS,
    REFUSAL_MESSAGE_LOW_SIMILARITY,
    QueryAnswered,
    QueryNoDocuments,
    QueryRefused,
    QueryResponse,
)
from rag.repositories.base import ChunkRepository
from rag.trace import TRACE_LOG_KEY

logger = get_logger(__name__)


async def answer_question(
    question: str,
    *,
    repo: ChunkRepository,
    providers: Providers,
    settings: Settings,
    trace_id: str,
    top_k_override: int | None = None,
) -> QueryResponse:
    """Run the query pipeline. Returns one of the three QueryResponse variants.

    Raises:
        ValueError: question was empty / too long (API → 400).
        UpstreamProviderError: a provider call failed (API → 503).
    """
    started = time.perf_counter()

    # 1. Validate.
    q = (question or "").strip()
    if not q:
        raise ValueError("question must be non-empty")
    if len(q) > settings.RAG_QUESTION_MAX_LEN:
        raise ValueError(f"question exceeds {settings.RAG_QUESTION_MAX_LEN} chars (got {len(q)})")

    logger.info(
        "query_received",
        extra={
            TRACE_LOG_KEY: trace_id,
            "question_len": len(q),
            "question_preview": q[:120],
        },
    )

    # 2. Corpus emptiness check (spec FR-014).
    if not await repo.has_any_chunks():
        logger.info("query_no_documents", extra={TRACE_LOG_KEY: trace_id})
        return QueryNoDocuments(message=NO_DOCUMENTS_MESSAGE, trace_id=trace_id)

    # 3. Embed.
    embeddings = await providers.embedder.embed([q])
    if not embeddings or len(embeddings[0]) != settings.EMBEDDING_DIM:
        raise UpstreamProviderError(
            "gemini",
            RuntimeError(
                f"embedding dim mismatch on question (got {len(embeddings[0]) if embeddings else 0})"
            ),
        )
    query_vec = embeddings[0]

    # 4. Retrieve.
    k = top_k_override or settings.RAG_TOP_K
    retrieved = await repo.search(query_vec, k=k, sim_floor=settings.RAG_SIM_FLOOR)
    top_sims = [round(rc.similarity, 4) for rc in retrieved]
    logger.info(
        "retrieval_complete",
        extra={
            TRACE_LOG_KEY: trace_id,
            "retrieved_count": len(retrieved),
            "top_similarities": top_sims,
            "chunk_ids": [str(rc.record.id) for rc in retrieved],
        },
    )

    # 5. Sim-floor short-circuit refusal (spec FR-010).
    if not retrieved:
        logger.info(
            "query_refused",
            extra={
                TRACE_LOG_KEY: trace_id,
                "refusal_cause": "low_similarity",
                "top_similarities": top_sims,
                "elapsed_s": round(time.perf_counter() - started, 3),
            },
        )
        return QueryRefused(
            message=REFUSAL_MESSAGE_LOW_SIMILARITY,
            refusal_cause="low_similarity",
            model=settings.EMBEDDING_MODEL,
            trace_id=trace_id,
        )

    # 6. Generate.
    gen_user = build_generation_user_prompt(q, retrieved)
    answer_text = await providers.generator.complete(
        system=GENERATION_SYSTEM,
        user=gen_user,
        model=settings.GENERATION_MODEL,
    )
    answer_text = answer_text.strip()
    logger.info(
        "generation_complete",
        extra={
            TRACE_LOG_KEY: trace_id,
            "answer_len": len(answer_text),
            "model": settings.GENERATION_MODEL,
        },
    )

    # 7. Judge.
    passages = chunks_for_judging(retrieved)
    verdict = await providers.judge.judge(
        question=q,
        answer=answer_text,
        passages=passages,
    )
    logger.info(
        "judge_complete",
        extra={
            TRACE_LOG_KEY: trace_id,
            "entailed": verdict.entailed,
            "support_passages": list(verdict.supports.keys()),
            "judge_model": settings.GROUNDING_JUDGE_MODEL,
        },
    )

    # 8. Refusal: judge said not entailed.
    if not verdict.entailed:
        logger.info(
            "query_refused",
            extra={
                TRACE_LOG_KEY: trace_id,
                "refusal_cause": "failed_grounding_check",
                "judge_reason": verdict.reason,
                "elapsed_s": round(time.perf_counter() - started, 3),
            },
        )
        return QueryRefused(
            message=REFUSAL_MESSAGE_FAILED_GROUNDING,
            refusal_cause="failed_grounding_check",
            model=settings.GROUNDING_JUDGE_MODEL,
            trace_id=trace_id,
        )

    # 9. Build citations.
    citations = build_citations(
        verdict=verdict,
        retrieved=retrieved,
        span_max=settings.RAG_QUOTED_SPAN_MAX,
    )

    # 10. Degenerate-judge recovery: entailed=True but no supporting spans (R-016).
    if not citations:
        logger.info(
            "query_refused",
            extra={
                TRACE_LOG_KEY: trace_id,
                "refusal_cause": "judge_no_supporting_spans",
                "judge_reason": verdict.reason,
                "elapsed_s": round(time.perf_counter() - started, 3),
            },
        )
        return QueryRefused(
            message=REFUSAL_MESSAGE_JUDGE_NO_SPANS,
            refusal_cause="judge_no_supporting_spans",
            model=settings.GROUNDING_JUDGE_MODEL,
            trace_id=trace_id,
        )

    # 11. Answered.
    logger.info(
        "query_answered",
        extra={
            TRACE_LOG_KEY: trace_id,
            "citation_count": len(citations),
            "elapsed_s": round(time.perf_counter() - started, 3),
        },
    )
    return QueryAnswered(
        answer=answer_text,
        citations=citations,
        model=settings.GENERATION_MODEL,
        trace_id=trace_id,
    )


# Convenience alias to keep callers' annotations clean.
__all__ = ["LLMProvider", "answer_question"]
