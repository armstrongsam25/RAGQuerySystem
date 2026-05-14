"""Generation and judge prompt templates.

Source-controlled per spec FR-011 — these are constants, not runtime
configuration. A reviewer can read them and reproduce the demo's
grounding behavior.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from rag.providers.base import ChunkForJudging
from rag.repositories.base import RetrievedChunk

# Sentence splitter — same regex as the chunker, kept duplicated here
# (rather than imported) so the prompts module has no reverse dep on the
# chunker module. Cheap to maintain in lockstep.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


# -- Generation -----------------------------------------------------------

GENERATION_SYSTEM = (
    "You are a careful question-answering assistant. You will be given a "
    "question and a numbered list of passages from a single source document. "
    "Answer the question using ONLY information stated explicitly in the "
    "passages.\n\n"
    "Rules:\n"
    "1. If the passages do not contain enough information to answer, say so "
    "plainly. Do not guess, do not fill in from general knowledge.\n"
    "2. Quote or paraphrase tightly. Do not introduce facts that are not in "
    "the passages.\n"
    "3. Keep the answer concise — one or two short paragraphs maximum.\n"
    "4. Do not include passage numbers, citations, or page references in "
    "your answer text. The system will attach citations separately."
)


def build_generation_user_prompt(
    question: str,
    retrieved: list[RetrievedChunk],
) -> str:
    """Format retrieved chunks as numbered passages with page labels."""
    lines = ["PASSAGES:", ""]
    for i, rc in enumerate(retrieved):
        lines.append(f"[{i + 1}] (page {rc.record.page_number})")
        lines.append(rc.record.raw_text.strip())
        lines.append("")
    lines.append("QUESTION:")
    lines.append(question.strip())
    return "\n".join(lines)


# -- Judge ----------------------------------------------------------------

JUDGE_SYSTEM = (
    "You are a grounding verifier. You will be given a question, a proposed "
    "answer, and a set of source passages. Each passage is broken into "
    "numbered sentences (0-indexed).\n\n"
    "Decide whether every factual claim in the answer is supported by at "
    "least one of the passages. For each passage that supports the answer, "
    "list the sentence indices (0-indexed) that contain the supporting "
    "evidence.\n\n"
    "Respond with valid JSON only, in this exact shape:\n"
    '{"entailed": <true|false>, '
    '"supports": {"<passage_id>": [<sentence_idx>, ...], ...}, '
    '"reason": "<short explanation, max 200 chars>"}\n\n'
    "If a passage contributes nothing to supporting the answer, omit it "
    "from `supports` (or set its list to []). If the answer is not "
    "supported by the passages, set entailed=false and supports={}."
)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences using the chunker's heuristic.

    Imperfect on abbreviations; documented in chunker.py.
    """
    text = text.strip()
    if not text:
        return []
    sentences: list[str] = []
    last_end = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        sentences.append(text[last_end : match.end()].strip())
        last_end = match.end()
    if last_end < len(text):
        sentences.append(text[last_end:].strip())
    return [s for s in sentences if s]


def chunks_for_judging(retrieved: Iterable[RetrievedChunk]) -> list[ChunkForJudging]:
    """Pre-split each retrieved chunk's text into sentences for the judge."""
    out: list[ChunkForJudging] = []
    for i, rc in enumerate(retrieved):
        passage_id = f"p{i}"
        out.append(
            ChunkForJudging(
                passage_id=passage_id,
                sentences=split_sentences(rc.record.raw_text),
            )
        )
    return out


def build_judge_user_prompt(
    question: str,
    answer: str,
    passages: list[ChunkForJudging],
) -> str:
    lines = [
        "QUESTION:",
        question.strip(),
        "",
        "ANSWER:",
        answer.strip(),
        "",
        "PASSAGES:",
    ]
    for p in passages:
        lines.append(f"\nPassage {p.passage_id}:")
        for j, sent in enumerate(p.sentences):
            lines.append(f"  [{j}] {sent}")
    return "\n".join(lines)
