"""Grounding judge over a local OpenAI-API-compatible endpoint.

Art IV.6 deviation per plan.md Complexity Tracking: the judge runs against
a configurable OpenAI-compatible server (LM Studio / Ollama-with-/v1 /
llama.cpp / vLLM). The deviation justification is in spec.md.
"""

from __future__ import annotations

import json

from openai import AsyncOpenAI

from rag.config import Settings
from rag.providers.base import (
    ChunkForJudging,
    JudgeVerdict,
    UpstreamProviderError,
)


class OpenAICompatJudgeProvider:
    """LLM-as-judge against the configured `GROUNDING_JUDGE_*` endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            base_url=settings.GROUNDING_JUDGE_BASE_URL,
            api_key=settings.GROUNDING_JUDGE_API_KEY.get_secret_value(),
            timeout=60.0,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "OpenAICompatJudgeProvider does not implement embed; "
            "use GeminiProvider for embeddings (constitution Art IV.5)."
        )

    async def complete(self, *, system: str, user: str, model: str | None = None) -> str:
        raise NotImplementedError(
            "OpenAICompatJudgeProvider does not implement complete; "
            "use GeminiProvider for generation (constitution Art IV.6 first sentence)."
        )

    async def judge(
        self,
        *,
        question: str,
        answer: str,
        passages: list[ChunkForJudging],
    ) -> JudgeVerdict:
        from rag.query.prompts import JUDGE_SYSTEM, build_judge_user_prompt

        user_msg = build_judge_user_prompt(question, answer, passages)

        try:
            resp = await self._client.chat.completions.create(
                model=self._settings.GROUNDING_JUDGE_MODEL,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
        except Exception as exc:
            raise UpstreamProviderError("judge", exc) from exc

        if not resp.choices or resp.choices[0].message.content is None:
            raise UpstreamProviderError(
                "judge",
                RuntimeError("judge returned empty response"),
            )
        raw = resp.choices[0].message.content

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UpstreamProviderError("judge", exc) from exc

        return _parse_verdict(payload, passages)


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
