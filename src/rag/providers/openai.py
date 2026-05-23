"""OpenAI-compatible provider: embeddings, generation, and grounding judge.

Implements every verb on :class:`LLMProvider` via the OpenAI SDK pointed
at an OpenAI-compatible API (e.g. vLLM, llama.cpp server).

Provides:
  * :meth:`embed` — uses the configured EMBEDDING_MODEL via the
    /v1/embeddings endpoint.
  * :meth:`complete` — uses the configured GENERATION_MODEL via
    /v1/chat/completions.
  * :meth:`judge` — uses the configured GROUNDING_JUDGE_MODEL with
    response_format json_object.

Transient-error retry covers 429, 503, and connection errors with
exponential backoff. PDF extraction is not provided — the ingest pipeline
must use a separate mechanism for page-level text extraction when using
this provider.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable

from openai import APIError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import SecretStr

from rag.config import Settings
from rag.log import get_logger
from rag.providers.base import (
    ChunkForJudging,
    JudgeVerdict,
    UpstreamProviderError,
)

logger = get_logger(__name__)

_MAX_RETRIES = 4
_BASE_BACKOFF_S = 2.0
_MAX_BACKOFF_S = 30.0

_TIMEOUT_EMBED_S = 60.0
_TIMEOUT_COMPLETE_S = 60.0
_TIMEOUT_JUDGE_S = 30.0


def _is_retriable(exc: Exception) -> bool:
    """True if the exception is a transient server-side failure worth retrying."""
    if isinstance(exc, APITimeoutError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in {429, 502, 503, 504}
    msg = str(exc)
    return any(
        token in msg.lower()
        for token in ("connection", "timeout", "reset", "refused", "unreachable")
    )


async def _with_retry[T](
    label: str, call: Callable[[], T], *, timeout_s: float = _TIMEOUT_COMPLETE_S
) -> T:
    """Run an async call, retrying on transient upstream errors."""
    attempt = 0
    last_exc: Exception | None = None
    while True:
        try:
            return await asyncio.wait_for(
                asyncio.ensure_future(call()), timeout=timeout_s
            )
        except TimeoutError as exc:
            last_exc = exc
            attempt += 1
            if attempt > _MAX_RETRIES:
                logger.warning(
                    "openai_call_timeout_exhausted",
                    extra={"label": label, "attempts": attempt - 1, "timeout_s": timeout_s},
                )
                raise UpstreamProviderError(
                    "openai", TimeoutError(f"{label} timed out after {timeout_s}s")
                ) from exc
            delay = min(_BASE_BACKOFF_S * (2 ** (attempt - 1)), _MAX_BACKOFF_S)
            logger.info(
                "openai_call_timeout_retry",
                extra={"label": label, "attempt": attempt, "delay_s": round(delay, 2)},
            )
            await asyncio.sleep(delay)
        except (APIStatusError, APITimeoutError) as exc:
            last_exc = exc
            if not _is_retriable(exc):
                raise UpstreamProviderError("openai", exc) from exc
            attempt += 1
            if attempt > _MAX_RETRIES:
                logger.warning(
                    "openai_retry_exhausted",
                    extra={
                        "label": label,
                        "attempts": attempt - 1,
                        "status": getattr(exc, "status_code", None),
                    },
                )
                raise UpstreamProviderError("openai", exc) from exc
            delay = min(_BASE_BACKOFF_S * (2 ** (attempt - 1)), _MAX_BACKOFF_S)
            logger.info(
                "openai_transient_retry",
                extra={
                    "label": label,
                    "attempt": attempt,
                    "delay_s": round(delay, 2),
                    "status": getattr(exc, "status_code", None),
                },
            )
            await asyncio.sleep(delay)
        except APIError as exc:
            raise UpstreamProviderError("openai", exc) from exc
        except Exception as exc:
            raise UpstreamProviderError("openai", exc) from exc
    if last_exc is not None:
        raise UpstreamProviderError("openai", last_exc) from last_exc
    raise RuntimeError("unreachable")


class OpenAIProvider:
    """Embedding + generation + judge via OpenAI-compatible API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY.get_secret_value(),
            timeout=60.0,
            max_retries=0,  # we do our own retry
        )

    # ---- embed -----------------------------------------------------------

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        async def _call() -> list[list[float]]:
            resp = await self._client.embeddings.create(
                model=self._settings.EMBEDDING_MODEL,
                input=texts,
            )
            # Sort by index to preserve order
            result = [None] * len(texts)  # type: ignore[var-annotated]
            for item in resp.data:
                result[item.index] = item.embedding
            return result  # type: ignore[return-value]

        return await _with_retry("embed", _call, timeout_s=_TIMEOUT_EMBED_S)

    # ---- complete --------------------------------------------------------

    async def complete(self, *, system: str, user: str, model: str | None = None) -> str:
        chosen_model = model or self._settings.GENERATION_MODEL

        async def _call() -> str:
            resp = await self._client.chat.completions.create(
                model=chosen_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
            )
            content = resp.choices[0].message.content
            if content is None:
                raise RuntimeError("OpenAI returned no text content")
            return content

        return await _with_retry("complete", _call, timeout_s=_TIMEOUT_COMPLETE_S)

    # ---- judge -----------------------------------------------------------

    async def judge(
        self,
        *,
        question: str,
        answer: str,
        passages: list[ChunkForJudging],
    ) -> JudgeVerdict:
        from rag.query.prompts import JUDGE_SYSTEM, build_judge_user_prompt

        user_msg = build_judge_user_prompt(question, answer, passages)
        model = self._settings.GROUNDING_JUDGE_MODEL

        async def _call() -> str:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
            if content is None:
                raise RuntimeError("OpenAI judge returned no text content")
            return content

        raw = await _with_retry("judge", _call, timeout_s=_TIMEOUT_JUDGE_S)

        try:
            payload, _ = json.JSONDecoder().raw_decode(raw.strip())
        except json.JSONDecodeError as exc:
            raise UpstreamProviderError("judge", exc) from exc

        return _parse_verdict(payload, passages)

    # ---- extract_page_text (not supported) -------------------------------

    async def extract_page_text(self, pdf_bytes: bytes, page_number: int) -> str:
        """Extract a single page's plaintext using pypdf (no remote API).

        When using OpenAI-compatible providers, PDF extraction falls back
        to pypdf's built-in text extraction rather than a vision-capable
        LLM. This works well for text-native PDFs but won't OCR scanned pages.
        """
        import io

        import pypdf

        return await asyncio.to_thread(
            _extract_page_text_local, pdf_bytes, page_number
        )


def _parse_verdict(payload: object, passages: list[ChunkForJudging]) -> JudgeVerdict:
    """Validate the judge's JSON and produce a typed JudgeVerdict."""
    if not isinstance(payload, dict):
        raise UpstreamProviderError(
            "judge",
            RuntimeError(f"judge JSON is not an object: {type(payload).__name__}"),
        )

    entailed = bool(payload.get("entailed", False))
    raw_supports = payload.get("supports", {})
    reason = str(payload.get("reason", ""))[:500]

    sentence_counts = {p.passage_id: len(p.sentences) for p in passages}
    cleaned_supports: dict[str, list[int]] = {}

    if isinstance(raw_supports, dict):
        for passage_id, indices in raw_supports.items():
            pid = str(passage_id)
            if pid not in sentence_counts:
                continue
            if not isinstance(indices, list):
                continue
            valid_indices: list[int] = []
            for idx in indices:
                if not isinstance(idx, int):
                    continue
                if 0 <= idx < sentence_counts[pid]:
                    valid_indices.append(idx)
            if valid_indices:
                cleaned_supports[pid] = sorted(set(valid_indices))

    return JudgeVerdict(entailed=entailed, supports=cleaned_supports, reason=reason)


def _extract_page_text_local(pdf_bytes: bytes, page_number: int) -> str:
    """Extract text from one page using pypdf (local, no API key needed)."""
    import io

    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    if page_number < 1 or page_number > len(reader.pages):
        raise ValueError(
            f"page_number {page_number} out of range (PDF has {len(reader.pages)} pages)"
        )
    return (reader.pages[page_number - 1].extract_text() or "").strip()