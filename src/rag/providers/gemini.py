"""Gemini provider: embeddings, generation, grounding judge, and per-page PDF extraction.

Implements every verb on :class:`LLMProvider`:
  * :meth:`embed` — `gemini-embedding-001`, with `output_dimensionality`
    pinned to `EMBEDDING_DIM` so the schema column matches.
  * :meth:`complete` — Gemini 2.5 Flash (or whatever `GENERATION_MODEL` is).
  * :meth:`judge` — Gemini 2.5 Flash Lite (or whatever `GROUNDING_JUDGE_MODEL`
    is), using `response_mime_type="application/json"` so the verdict comes
    back as parseable JSON.

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
import json
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

# Per-call timeouts. The SDK has no default request timeout, so a stuck
# upstream (slow response stream, safety-review stall on short input)
# would otherwise block the request thread indefinitely. asyncio.wait_for
# surfaces a hung call as TimeoutError -> retry, and after the retry
# budget is spent, as UpstreamProviderError -> 503.
_TIMEOUT_EMBED_S = 15.0
_TIMEOUT_COMPLETE_S = 30.0
_TIMEOUT_JUDGE_S = 20.0
_TIMEOUT_EXTRACT_S = 60.0


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


async def _with_retry[T](
    label: str, call: Callable[[], T], *, timeout_s: float = _TIMEOUT_COMPLETE_S
) -> T:
    """Run a sync SDK call in a thread, retrying on transient upstream errors.

    Each attempt is bounded by ``timeout_s`` via :func:`asyncio.wait_for`;
    timeouts are treated as retriable (same as 504 DEADLINE_EXCEEDED).
    Backoff respects the SDK's `retryDelay` hint when present, else falls
    back to exponential backoff capped at `_MAX_BACKOFF_S`. After
    `_MAX_RETRIES` failed attempts, 429s raise :class:`RateLimitedError`
    (the CLI prints a quota-specific message); other transient codes raise
    plain :class:`UpstreamProviderError`. Non-retriable errors propagate
    as :class:`UpstreamProviderError` immediately.

    NOTE on cancellation semantics: ``asyncio.wait_for`` cancels the wrapping
    coroutine on timeout, but the inner ``asyncio.to_thread`` call cannot be
    cancelled — the SDK thread keeps running until its socket eventually
    closes. That's acceptable: the user-visible request returns promptly,
    and the orphaned thread costs only its own stack until the underlying
    httpx connection times out at the OS layer.
    """
    attempt = 0
    last_exc: Exception | None = None
    while True:
        try:
            return await asyncio.wait_for(asyncio.to_thread(call), timeout=timeout_s)
        except TimeoutError as exc:
            # Retriable. After exhausting the budget, surface as a plain
            # UpstreamProviderError so the route turns it into a 503.
            last_exc = exc
            attempt += 1
            if attempt > _MAX_RETRIES:
                logger.warning(
                    "gemini_call_timeout_exhausted",
                    extra={
                        "label": label,
                        "attempts": attempt - 1,
                        "timeout_s": timeout_s,
                    },
                )
                raise UpstreamProviderError(
                    "gemini", TimeoutError(f"{label} timed out after {timeout_s}s")
                ) from exc
            delay = min(_BASE_BACKOFF_S * (2 ** (attempt - 1)), _MAX_BACKOFF_S)
            logger.info(
                "gemini_call_timeout_retry",
                extra={
                    "label": label,
                    "attempt": attempt,
                    "delay_s": round(delay, 2),
                    "timeout_s": timeout_s,
                },
            )
            await asyncio.sleep(delay)
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
                return await _with_retry("embed", _call, timeout_s=_TIMEOUT_EMBED_S)

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

        def _call() -> str:
            resp = self._client.models.generate_content(
                model=model,
                contents=[user_msg],
                config=genai_types.GenerateContentConfig(
                    system_instruction=JUDGE_SYSTEM,
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            text = resp.text
            if text is None:
                raise RuntimeError("Gemini judge returned no text content")
            return text

        raw = await _with_retry("judge", _call, timeout_s=_TIMEOUT_JUDGE_S)

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UpstreamProviderError("judge", exc) from exc

        return _parse_verdict(payload, passages)

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

        return await _with_retry(
            f"extract_page_{page_number}", _call, timeout_s=_TIMEOUT_EXTRACT_S
        )


def _parse_verdict(payload: object, passages: list[ChunkForJudging]) -> JudgeVerdict:
    """Validate the judge's JSON and produce a typed JudgeVerdict.

    Per R-015 the expected shape is::

        {entailed: bool, supports: {passage_id: [sentence_idx, ...]}, reason: str}

    Out-of-range or unknown passage_ids and out-of-range sentence indices
    are silently dropped — the judge is allowed to be sloppy at the edges,
    but anything we keep must point at a real sentence in a real passage.
    """
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
