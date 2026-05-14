"""Application configuration via pydantic-settings.

The :class:`Settings` model is the single source of truth for every
environment variable the app reads. Required fields raise a
:class:`pydantic.ValidationError` at startup if missing or empty
(spec FR-003 + feature 002 FR-027/FR-028).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All env-driven configuration for the app.

    `extra="forbid"` makes typo'd direct-kwarg construction fail loudly
    (see notes on env-var-typo behavior in research R-003 from feature 001).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=True,
    )

    # --- Gemini -----------------------------------------------------------
    GEMINI_API_KEY: SecretStr = Field(
        ...,
        min_length=1,
        description=(
            "Gemini API key. Required. Used for PDF extraction (File API), "
            "embeddings (gemini-embedding-001), and generation (Gemini 2.5 Flash)."
        ),
    )
    EMBEDDING_MODEL: str = Field(
        default="gemini-embedding-001",
        min_length=1,
        description=(
            "Gemini embedding model id (constitution Art IV.5 v1.0.3 — bumped "
            "from text-embedding-004 on 2026-05-12 after Google retired that "
            "model id from the v1beta API). Output dimensionality is forced to "
            "EMBEDDING_DIM (768) to match the vector(768) schema column."
        ),
    )
    GENERATION_MODEL: str = Field(
        default="gemini-2.5-flash",
        min_length=1,
        description=(
            "Gemini generation model id. Constitution v1.0.2 Art IV.6 pins "
            "`gemini-2.5-flash` (bumped from 2.0 on 2026-05-12 after Google "
            "retired the 2.0 ID for new keys). Override via env if needed."
        ),
    )

    # --- Database ---------------------------------------------------------
    DATABASE_URL: PostgresDsn = Field(
        ...,
        description="Postgres DSN. Inside docker compose this points at the `db` service.",
    )

    POSTGRES_USER: str = Field(default="rag", min_length=1)
    POSTGRES_PASSWORD: SecretStr = Field(default=SecretStr("rag"), min_length=1)
    POSTGRES_DB: str = Field(default="rag", min_length=1)

    # --- Embedding --------------------------------------------------------
    EMBEDDING_DIM: int = Field(
        default=768,
        gt=0,
        description=(
            "Pgvector dimensionality. Verified at startup against the "
            "`chunk.embedding` column's atttypmod (feature 001 R-004). Also "
            "passed to `gemini-embedding-001` as `output_dimensionality` so "
            "the embedding response matches the schema column."
        ),
    )

    # --- Retrieval / generation tunables (feature 002) -------------------
    RAG_TOP_K: int = Field(
        default=5,
        gt=0,
        le=20,
        description="Default top-k for retrieval. Per spec FR-009 + plan defaults.",
    )
    RAG_SIM_FLOOR: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description=(
            "Cosine-similarity coarse pre-filter (spec FR-010). The LLM-as-judge "
            "from FR-012 is the real refusal gate; this is just the obvious-miss filter."
        ),
    )
    RAG_EMBED_BATCH: int = Field(
        default=32,
        gt=0,
        le=100,
        description="Embedding batch size for ingest. Plan §Technical Context.",
    )
    RAG_GEMINI_CONCURRENCY: int = Field(
        default=2,
        gt=0,
        le=16,
        description=(
            "Bounded concurrency for per-page Gemini File API calls (research R-017). "
            "Default 2 keeps free-tier rate limits comfortable; bump to 4-8 if you've "
            "enabled billing and want faster ingest."
        ),
    )
    RAG_QUOTED_SPAN_MAX: int = Field(
        default=400,
        gt=0,
        le=1000,
        description="Per-citation quoted-span cap in API responses (spec FR-008 + research R-016).",
    )
    RAG_QUESTION_MAX_LEN: int = Field(
        default=1000,
        gt=0,
        le=10000,
        description="Question length cap; matches contracts/query.yaml maxLength.",
    )
    RAG_MAX_UPLOAD_BYTES: int = Field(
        default=104857600,  # 100 MiB
        gt=0,
        le=1073741824,  # 1 GiB sanity bound
        description=(
            "Maximum size of an uploaded PDF in bytes (feature 003 spec FR-015). "
            "Default 100 MiB. Enforced before any extraction or embedding work; "
            "exceeded uploads return HTTP 413 with the cap surfaced in the error "
            "message in both bytes and MB for reviewer-readable rejection."
        ),
    )

    # --- Grounding judge (Art IV.6 deviation — see spec.md Assumptions) --
    GROUNDING_JUDGE_BASE_URL: str = Field(
        default="http://host.docker.internal:1234/v1",
        min_length=1,
        description=(
            "OpenAI-API-compatible endpoint URL for the grounding judge "
            "(LM Studio / Ollama-with-/v1 / llama.cpp / vLLM)."
        ),
    )
    GROUNDING_JUDGE_API_KEY: SecretStr = Field(
        default=SecretStr("local-no-auth"),
        min_length=1,
        description="API key for the judge endpoint. Most local servers ignore it.",
    )
    GROUNDING_JUDGE_MODEL: str = Field(
        default="llama-3.1-8b-instruct",
        min_length=1,
        description="Model identifier as exposed by the local judge server.",
    )

    # --- Logging ----------------------------------------------------------
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Root logger level.",
    )

    @property
    def database_dsn(self) -> str:
        """psycopg-compatible DSN string."""
        return str(self.DATABASE_URL)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings factory."""
    return Settings()  # type: ignore[call-arg]
