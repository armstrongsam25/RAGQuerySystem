"""LLM provider abstraction layer.

One Protocol, two implementations:
  * :class:`GeminiProvider` — embedding (`gemini-embedding-001`) + generation
    (Gemini 2.5 Flash) + per-page PDF extraction (Gemini File API).
  * :class:`OpenAICompatJudgeProvider` — the grounding judge, talking to a
    local OpenAI-API-compatible endpoint per the Art IV.6 deviation
    declared in plan.md Complexity Tracking.

Each implementation raises :class:`NotImplementedError` on the verbs it
does not own; the DI layer (lifespan) wires the right provider to each
slot in the :class:`Providers` tuple.
"""

from rag.providers.base import (
    ChunkForJudging,
    JudgeVerdict,
    LLMProvider,
    Providers,
    UpstreamProviderError,
)
from rag.providers.gemini import GeminiProvider, RateLimitedError
from rag.providers.openai_compat import OpenAICompatJudgeProvider

__all__ = [
    "ChunkForJudging",
    "GeminiProvider",
    "JudgeVerdict",
    "LLMProvider",
    "OpenAICompatJudgeProvider",
    "Providers",
    "RateLimitedError",
    "UpstreamProviderError",
]
