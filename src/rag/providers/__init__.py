"""LLM provider abstraction layer.

One Protocol, one implementation: :class:`GeminiProvider` covers every
verb (`embed`, `complete`, `judge`) plus per-page PDF extraction via the
Gemini File API. The DI layer (lifespan / CLI) wires the single provider
into all three slots of the :class:`Providers` tuple.
"""

from rag.providers.base import (
    ChunkForJudging,
    JudgeVerdict,
    LLMProvider,
    Providers,
    UpstreamProviderError,
)
from rag.providers.gemini import GeminiProvider, RateLimitedError

__all__ = [
    "ChunkForJudging",
    "GeminiProvider",
    "JudgeVerdict",
    "LLMProvider",
    "Providers",
    "RateLimitedError",
    "UpstreamProviderError",
]
