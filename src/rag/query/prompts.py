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
    "You are a careful question-answering assistant specializing in legal "
    "and medical documents. You will be given a question and a numbered "
    "list of passages from a single source document.\n\n"
    "Your primary task is to extract and summarize **medical history "
    "timelines** — chronological sequences of medical events, diagnoses, "
    "treatments, symptoms, procedures, medications, and clinical findings.\n\n"
    "Rules:\n"
    "1. **Timeline focus:** When the question relates to a person's medical "
    "history, structure your answer as a chronological timeline. List events "
    "in date order (earliest first). For each event, include: the date or "
    "approximate date, what happened (diagnosis, treatment, symptom, finding), "
    "and any relevant context (who, where, outcome).\n"
    "2. **Cite every factual claim:** At the end of each sentence or factual "
    "claim, place a citation marker in square brackets referencing the "
    "passage number, like [1] or [2, 3]. Every single factual statement MUST "
    "have at least one citation.\n"
    "3. **Source-only:** Use ONLY information stated explicitly in the "
    "passages. Do not guess, do not fill in from general knowledge. If the "
    "passages do not contain enough information, say so plainly.\n"
    "4. **Be thorough:** When summarizing a large document, be comprehensive. "
    "Include all relevant medical events found in the passages. Do not "
    "abbreviate or skip clinically significant details.\n"
    "5. **Format:** Use clear section headers (e.g., 'Medical History "
    "Timeline', 'Diagnoses', 'Medications', 'Procedures') to organize "
    "the summary. Use numbered citation markers [N] for every factual claim."
)


def build_generation_user_prompt(
    question: str,
    retrieved: list[RetrievedChunk],
) -> str:
    """Format retrieved chunks as numbered passages with page labels.

    Passage numbers [1], [2], ... correspond to citation markers the LLM
    must use in its answer. Each passage is labeled with its page number
    so the LLM can reference page context when appropriate.
    """
    lines = ["PASSAGES:", ""]
    for i, rc in enumerate(retrieved):
        lines.append(f"[{i + 1}] (page {rc.record.page_number})")
        lines.append(rc.record.raw_text.strip())
        lines.append("")
    lines.append("QUESTION:")
    lines.append(question.strip())
    lines.append("")
    lines.append(
        "Remember: Place citation markers [N] after EVERY factual claim, "
        "using the passage numbers shown above. If multiple passages support "
        "a claim, list them all: [1, 3, 5]."
    )
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
