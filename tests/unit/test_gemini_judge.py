"""Judge JSON parsing tolerance for the GeminiProvider.

Regression test: even with ``response_mime_type="application/json"``, Gemini
occasionally emits a second JSON object (or repeated reasoning) on a new
line after the verdict. Strict ``json.loads`` rejects that with
``JSONDecodeError: Extra data: line 2 column 1`` and surfaces as a spurious
503 in the UI. The provider must accept the first JSON value and ignore
trailing content.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rag.providers.base import ChunkForJudging
from rag.providers.gemini import GeminiProvider


class _FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self._text)


@pytest.mark.asyncio
async def test_judge_tolerates_trailing_json(settings):
    """Raw judge output of '<verdict>\\n<junk>' parses cleanly to the verdict."""
    provider = GeminiProvider(settings)
    raw = '{"entailed": false, "supports": {}, "reason": "ok"}\n{"junk": 1}'
    provider._client = SimpleNamespace(models=_FakeModels(raw))

    passages = [ChunkForJudging(passage_id="p0", sentences=["irrelevant."])]
    verdict = await provider.judge(question="q", answer="a", passages=passages)

    assert verdict.entailed is False
    assert verdict.supports == {}
    assert verdict.reason == "ok"


@pytest.mark.asyncio
async def test_judge_tolerates_leading_whitespace(settings):
    """Leading whitespace shouldn't break parsing — raw_decode needs offset 0."""
    provider = GeminiProvider(settings)
    raw = '   \n  {"entailed": true, "supports": {"p0": [0]}, "reason": "yes"}'
    provider._client = SimpleNamespace(models=_FakeModels(raw))

    passages = [ChunkForJudging(passage_id="p0", sentences=["A fact."])]
    verdict = await provider.judge(question="q", answer="a", passages=passages)

    assert verdict.entailed is True
    assert verdict.supports == {"p0": [0]}
