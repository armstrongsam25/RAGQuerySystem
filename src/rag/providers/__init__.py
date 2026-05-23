"""LLM provider abstraction layer.

Multiple provider implementations for different backends:

- :class:`OpenAIProvider`: generation + judge via any OpenAI-compatible API.
- :class:`GeminiProvider`: full provider via Google Gemini SDK (legacy).
- :class:`LocalEmbeddingProvider`: local CPU embedding via fastembed.
- :class:`LocalEmbeddingProviderEmbedder`: adapter that makes
  ``LocalEmbeddingProvider`` implement the ``embed`` verb on ``LLMProvider``
  so it can be plugged into the ``Providers`` tuple.

The DI layer (lifespan / CLI) wires the correct combination based on
environment config. By default, embedding is local (no API key needed)
and generation/judge use the configured LLM_BASE_URL.
"""

from rag.providers.base import (
    ChunkForJudging,
    JudgeVerdict,
    LLMProvider,
    Providers,
    UpstreamProviderError,
)
from rag.providers.gemini import GeminiProvider, RateLimitedError
from rag.providers.local_embed import LocalEmbeddingProvider
from rag.providers.openai import OpenAIProvider


class LocalEmbeddingProviderEmbedder:
    """Adapter: exposes the ``embed`` verb from LocalEmbeddingProvider as an LLMProvider.

    Only ``embed`` is implemented; ``complete`` and ``judge`` raise
    NotImplementedError (they're handled by the other slots in Providers).
    """

    def __init__(self, embedder: LocalEmbeddingProvider) -> None:
        self._embedder = embedder

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._embedder.embed(texts)

    async def extract_page_text(self, pdf_bytes: bytes, page_number: int) -> str:
        """Extract a single page's plaintext using pypdf (local, no API).

        Delegates to pypdf's built-in text extraction. Useful when the
        CLIIngest pipeline passes a LocalEmbeddingProviderEmbedder as the
        ``gemini`` parameter.
        """
        import asyncio

        import pypdf
        import io

        def _extract() -> str:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            if page_number < 1 or page_number > len(reader.pages):
                return ""
            text = reader.pages[page_number - 1].extract_text()
            return text or ""

        return await asyncio.to_thread(_extract)

    async def complete(self, *, system: str, user: str, model: str | None = None) -> str:
        raise NotImplementedError("LocalEmbeddingProviderEmbedder only supports embed")

    async def judge(
        self,
        *,
        question: str,
        answer: str,
        passages: list[ChunkForJudging],
    ) -> JudgeVerdict:
        raise NotImplementedError("LocalEmbeddingProviderEmbedder only supports embed")


__all__ = [
    "ChunkForJudging",
    "GeminiProvider",
    "JudgeVerdict",
    "LLMProvider",
    "LocalEmbeddingProvider",
    "LocalEmbeddingProviderEmbedder",
    "OpenAIProvider",
    "Providers",
    "RateLimitedError",
    "UpstreamProviderError",
]