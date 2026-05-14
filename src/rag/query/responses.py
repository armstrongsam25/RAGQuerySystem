"""Pydantic v2 response models matching contracts/query.yaml.

The discriminated union + `extra="forbid"` make spec FR-013's invariant
("answered ↔ ≥1 citation, refused ↔ 0 citations") a *type-level*
guarantee — a refused response cannot carry a citations field, period.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Refusal causes — three values, including the degenerate-judge recovery
# `judge_no_supporting_spans` per spec FR-015 + research R-016.
RefusalCause = Literal[
    "low_similarity",
    "failed_grounding_check",
    "judge_no_supporting_spans",
]


# ---- User-facing message constants (spec FR-014 + Phase 5 / T037) ----

REFUSAL_MESSAGE_LOW_SIMILARITY = (
    "I don't know — no passage in the ingested document was a close enough "
    "match to your question to ground an answer."
)
REFUSAL_MESSAGE_FAILED_GROUNDING = (
    "I don't know — the retrieved passages do not directly support an answer to your question."
)
REFUSAL_MESSAGE_JUDGE_NO_SPANS = (
    "I don't know — I couldn't pin the supporting evidence on a specific passage."
)
NO_DOCUMENTS_MESSAGE = (
    "No documents have been ingested. Run `rag ingest <path-to-pdf>` to load a PDF before querying."
)


# ---- Models ------------------------------------------------------------


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    source_document_id: UUID
    page_number: int = Field(ge=1)
    quoted_span: str = Field(min_length=1, max_length=401)  # 400 + ellipsis
    truncated: bool = False


class QueryAnswered(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["answered"] = "answered"
    answer: str = Field(min_length=1)
    citations: list[Citation] = Field(min_length=1)
    model: str
    trace_id: str


class QueryRefused(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["refused"] = "refused"
    message: str
    refusal_cause: RefusalCause
    model: str
    trace_id: str
    # No `citations` field — extra="forbid" enforces its absence.


class QueryNoDocuments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["no_documents"] = "no_documents"
    message: str
    trace_id: str


QueryResponse = Annotated[
    QueryAnswered | QueryRefused | QueryNoDocuments,
    Field(discriminator="status"),
]


class ErrorResponse(BaseModel):
    """Body shape for 400 / 503 responses (matches contracts/query.yaml Error)."""

    model_config = ConfigDict(extra="forbid")

    error: str
    message: str | None = None
    trace_id: str


class QueryRequest(BaseModel):
    """Body shape for `POST /query`."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    top_k: int | None = Field(default=None, ge=1, le=20)
