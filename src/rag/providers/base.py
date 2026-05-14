"""LLM provider Protocol + shared data structures.

Per research R-012, a single Protocol with mode-specific raises is
simpler than three separate Protocols (Embedder / Generator / Judge),
and the small risk of a `NotImplementedError` is worth the cleaner DI
surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple, Protocol, runtime_checkable


@dataclass(frozen=True)
class ChunkForJudging:
    """Passage handed to the grounding judge.

    Sentences are pre-split server-side (using the same sentence regex the
    chunker uses) so the judge's returned indices line up 1:1 with what
    citation construction will quote — see research R-015.
    """

    passage_id: str
    sentences: list[str]


@dataclass(frozen=True)
class JudgeVerdict:
    """Structured output of a grounding-judge call.

    `supports` maps `passage_id -> list of sentence indices that support
    the answer`. An empty list (or a missing key) means "this passage
    contributed nothing the judge could pin" — citation construction will
    drop those passages (research R-016).
    """

    entailed: bool
    supports: dict[str, list[int]] = field(default_factory=dict)
    reason: str = ""


class UpstreamProviderError(Exception):
    """Raised when an external SDK / endpoint call fails.

    Per spec FR-016, upstream failures MUST surface as actionable errors
    distinguishable from refusals — the API layer translates this into
    HTTP 503, the CLI into exit 1. The `provider` field names the
    upstream so callers (and log readers) can tell apart "gemini",
    "judge", and any future addition.
    """

    def __init__(self, provider: str, cause: Exception) -> None:
        super().__init__(f"upstream {provider} failure: {cause}")
        self.provider = provider
        self.cause = cause


@runtime_checkable
class LLMProvider(Protocol):
    """The full LLM surface this app needs.

    Concrete implementations implement only the methods they own and
    raise :class:`NotImplementedError` on the rest. The :class:`Providers`
    tuple below wires the right implementation to each verb.
    """

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...

    async def complete(self, *, system: str, user: str, model: str | None = None) -> str:
        """Return a single completion for `(system, user)`."""
        ...

    async def judge(
        self,
        *,
        question: str,
        answer: str,
        passages: list[ChunkForJudging],
    ) -> JudgeVerdict:
        """Decide whether the answer is entailed by the passages."""
        ...


class Providers(NamedTuple):
    """The three live providers, wired by the FastAPI lifespan / CLI startup.

    Used as a single dependency object so call sites take one parameter
    rather than three.
    """

    embedder: LLMProvider
    generator: LLMProvider
    judge: LLMProvider
