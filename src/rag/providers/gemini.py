"""Gemini provider: embeddings, generation, and per-page PDF extraction.

Implements :class:`LLMProvider.embed` (gemini-embedding-001, with
`output_dimensionality` pinned to `EMBEDDING_DIM` so the schema column
matches) and :class:`LLMProvider.complete` (Gemini 2.5 Flash). The
`judge` method raises `NotImplementedError` — judges run on the local
OpenAI-compatible endpoint per the Art IV.6 deviation in plan.md.

Also exposes :meth:`GeminiProvider.extract_page_text` for the ingest
pipeline — per research R-010, ingest sends each PDF page individually
to the File API so per-page identity is preserved at the API boundary
and Article II citation drift is impossible.

Transient-error retry: the wrapper retries on 429 (rate limit), 503
(UNAVAILABLE — model overloaded), and 504 (DEADLINE_EXCEEDED) with
exponential backoff. After the retry budget is spent, 429s surface as
:class:`RateLimitedError` so the CLI can produce a quota-aware message;
other transient codes surface as a plain :class:`UpstreamProviderError`.
500 INTERNAL is treated as fatal and propagates immediately.
"""

from __future__ import annotations

import asyncio
import io
import re
import time
from collections.abc import Awaitable, Callable

import pypdf
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from rag.config import Settings
from rag.log import get_logger
from rag.providers.base import (
    ChunkForJudging,
    JudgeVerdict,
    UpstreamProviderError,
)

logger = get_logger(__name__)

# Per-page extraction prompt. R-010: instruct Gemini to return plaintext
# only, preserve reading order, do not summarize / re-format.
_EXTRACTION_PROMPT = (
    "Return the plaintext content of this page exactly as it appears in "
    "reading order. Preserve paragraph breaks (use a blank line between "
    "paragraphs). Do not summarize. Do not infer. Do not add headings, "
    "page numbers, or markdown that are not in the source. If the page is "
    "empty or contains only images with no text, return an empty string."
)

# Retry policy for transient 429 errors.
_MAX_RETRIES = 4
_BASE_BACKOFF_S = 2.0
_MAX_BACKOFF_S = 30.0


class RateLimitedError(UpstreamProviderError):
    """Specialized upstream error for unrecoverable 429s.

    Distinguishes "we exhausted our retry budget on a rate-limited endpoint"
    from a generic upstream failure so the CLI can render an actionable
    message naming quotas / billing / waiting.
    """

    def __init__(self, cause: Exception, retry_hint_s: float | None = None) -> None:
        super().__init__("gemini", cause)
        self.retry_hint_s = retry_hint_s


def _extract_retry_delay_s(error_msg: str) -> float | None:
    """Pull `retryDelay: '8s'` out of a Gemini error blob if present."""
    match = re.search(r"['\"]retryDelay['\"]\s*:\s*['\"](\d+(?:\.\d+)?)s['\"]", error_msg)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _is_rate_limited(exc: Exception) -> bool:
    """True iff the SDK exception looks like a 429 / RESOURCE_EXHAUSTED."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429:
        return True
    msg = str(exc)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg


def _is_retriable(exc: Exception) -> bool:
    """True iff the SDK exception is a transient server-side failure.

    Covers 429 (rate limit), 503 (model overloaded), and 504 (timeout) —
    Google's docs call these out as retry-with-backoff candidates. 500
    INTERNAL is deliberately excluded; it's rare enough that retrying
    blindly tends to mask real bugs.
    """
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int) and code in {429, 503, 504}:
        return True
    msg = str(exc)
    return any(
        token in msg
        for token in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "DEADLINE_EXCEEDED")
    )


async def _with_retry[T](label: str, call: Callable[[], T]) -> T:
    """Run a sync SDK call in a thread, retrying on transient upstream errors.

    Backoff respects the SDK's `retryDelay` hint when present, else falls
    back to exponential backoff capped at `_MAX_BACKOFF_S`. After
    `_MAX_RETRIES` failed attempts, 429s raise :class:`RateLimitedError`
    (the CLI prints a quota-specific message); other transient codes raise
    plain :class:`UpstreamProviderError`. Non-retriable errors propagate
    as :class:`UpstreamProviderError` immediately.
    """
    attempt = 0
    last_exc: Exception | None = None
    while True:
        try:
            return await asyncio.to_thread(call)
        except genai_errors.APIError as exc:
            last_exc = exc
            if not _is_retriable(exc):
                raise UpstreamProviderError("gemini", exc) from exc
            attempt += 1
            if attempt > _MAX_RETRIES:
                hint = _extract_retry_delay_s(str(exc))
                if _is_rate_limited(exc):
                    logger.warning(
                        "gemini_rate_limit_exhausted",
                        extra={
                            "label": label,
                            "attempts": attempt - 1,
                            "retry_hint_s": hint,
                        },
                    )
                    raise RateLimitedError(exc, retry_hint_s=hint) from exc
                logger.warning(
                    "gemini_transient_error_exhausted",
                    extra={
                        "label": label,
                        "attempts": attempt - 1,
                        "code": getattr(exc, "code", None),
                    },
                )
                raise UpstreamProviderError("gemini", exc) from exc
            delay = _extract_retry_delay_s(str(exc))
            if delay is None:
                delay = min(_BASE_BACKOFF_S * (2 ** (attempt - 1)), _MAX_BACKOFF_S)
            logger.info(
                "gemini_transient_retry",
                extra={
                    "label": label,
                    "attempt": attempt,
                    "delay_s": round(delay, 2),
                    "code": getattr(exc, "code", None),
                },
            )
            await asyncio.sleep(delay)
        except Exception as exc:
            raise UpstreamProviderError("gemini", exc) from exc
    # Unreachable: the while loop only exits via return or raise.
    if last_exc is not None:
        raise UpstreamProviderError("gemini", last_exc) from last_exc
    raise RuntimeError("unreachable")


class GeminiProvider:
    """Embedding + generation + page extraction via the official Google SDK."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value())

    # ---- embed -----------------------------------------------------------

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = f"models/{self._settings.EMBEDDING_MODEL}"
        # gemini-embedding-001 defaults to 3072 dims; pass output_dimensionality
        # so the response matches the vector(EMBEDDING_DIM) schema column.
        embed_config = genai_types.EmbedContentConfig(
            output_dimensionality=self._settings.EMBEDDING_DIM,
        )
        # Per-text calls: the singular `contents=str` shape is the only call
        # form both gemini-embedding-001 and gemini-embedding-2 support
        # uniformly. Passing list[str] makes the SDK serialize as parts of one
        # Content for some model versions, returning fewer embeddings than
        # inputs. Bounded concurrency reuses the page-extraction semaphore.
        semaphore = asyncio.Semaphore(self._settings.RAG_GEMINI_CONCURRENCY)

        async def _embed_one(text: str) -> list[float]:
            def _call() -> list[float]:
                resp = self._client.models.embed_content(
                    model=model,
                    contents=text,
                    config=embed_config,
                )
                if not resp.embeddings or len(resp.embeddings) != 1:
                    raise RuntimeError(
                        f"Gemini embed returned {len(resp.embeddings or [])} "
                        f"embeddings for 1 input (model={model})"
                    )
                return list(resp.embeddings[0].values)

            async with semaphore:
                return await _with_retry("embed", _call)

        return await asyncio.gather(*(_embed_one(t) for t in texts))

    # ---- complete --------------------------------------------------------

    async def complete(self, *, system: str, user: str, model: str | None = None) -> str:
        chosen_model = model or self._settings.GENERATION_MODEL

        def _call() -> str:
            resp = self._client.models.generate_content(
                model=chosen_model,
                contents=[user],
                config=genai_types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.0,
                ),
            )
            text = resp.text
            if text is None:
                raise RuntimeError("Gemini returned no text content")
            return text

        return await _with_retry("complete", _call)

    # ---- judge (not implemented here — see openai_compat.py) ------------

    async def judge(
        self,
        *,
        question: str,
        answer: str,
        passages: list[ChunkForJudging],
    ) -> JudgeVerdict:
        raise NotImplementedError(
            "GeminiProvider does not implement judge; the grounding judge "
            "runs on the local OpenAI-compat endpoint (plan.md Art IV.6 deviation)."
        )

    # ---- extract_page_text ----------------------------------------------

    async def extract_page_text(self, pdf_bytes: bytes, page_number: int) -> str:
        """Extract a single page's plaintext via the Gemini File API.

        Per research R-010, this isolates page N into its own single-page
        PDF before uploading so Gemini receives one page at a time and the
        response is unambiguously about that page.
        """
        single_page_bytes = await asyncio.to_thread(_isolate_single_page, pdf_bytes, page_number)

        def _call() -> str:
            pdf_part = genai_types.Part.from_bytes(
                data=single_page_bytes,
                mime_type="application/pdf",
            )
            resp = self._client.models.generate_content(
                model=self._settings.GENERATION_MODEL,
                contents=[pdf_part, _EXTRACTION_PROMPT],
                config=genai_types.GenerateContentConfig(temperature=0.0),
            )
            return (resp.text or "").strip()

        return await _with_retry(f"extract_page_{page_number}", _call)


def _isolate_single_page(pdf_bytes: bytes, page_number: int) -> bytes:
    """Return a new PDF containing only page `page_number` (1-indexed).

    Implementation detail of :meth:`GeminiProvider.extract_page_text`.
    Pulled out as a module-level helper so the test suite can swap
    `GeminiProvider` for a fake without re-implementing this logic.
    """
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    if page_number < 1 or page_number > len(reader.pages):
        raise ValueError(
            f"page_number {page_number} out of range (PDF has {len(reader.pages)} pages, 1-indexed)"
        )
    writer = pypdf.PdfWriter()
    writer.add_page(reader.pages[page_number - 1])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# Avoid an "unused import" warning when `time` is only referenced in
# docstrings; the import is here for callers that monkey-patch the
# module-level clock in tests.
_ = time
# `Awaitable` is re-exported here so tests importing from this module
# can name the type without juggling typing-extensions.
__all__ = ["Awaitable", "GeminiProvider", "RateLimitedError"]
