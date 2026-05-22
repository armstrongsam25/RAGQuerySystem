"""Application configuration via pydantic-settings.

The :class:`Settings` model is the single source of truth for every
environment variable the app reads. Required fields raise a
:class:`pydantic.ValidationError` at startup if missing or empty
(spec FR-003 + feature 002 FR-027/FR-028).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All env-driven configuration for the app."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=True,
    )

    # --- LLM Provider -----------------------------------------------------
    LLM_API_KEY: SecretStr = Field(
        ...,
        min_length=1,
        description="API key for the LLM provider (OpenAI-compatible, e.g. vLLM).",
    )
    GEMINI_API_KEY: SecretStr = Field(
        default=SecretStr(""),
        description="Legacy — only used by GeminiProvider. Kept for test compat.",
    )
    LLM_BASE_URL: str = Field(
        default="https://api.openai.com/v1",
        min_length=1,
        description="Base URL for the OpenAI-compatible API endpoint.",
    )
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-3-small",
        min_length=1,
        description="Embedding model id (must exist at the configured LLM_BASE_URL).",
    )
    GENERATION_MODEL: str = Field(
        default="gpt-4o",
        min_length=1,
        description="Generation (chat completion) model id.",
    )
    GROUNDING_JUDGE_MODEL: str = Field(
        default="gpt-4o-mini",
        min_length=1,
        description="Model id for the grounding judge. Defaults to a cheaper model.",
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
            "`chunk.embedding` column's atttypmod."
        ),
    )

    # --- Retrieval / generation tunables (feature 002) -------------------
    RAG_TOP_K: int = Field(
        default=5,
        gt=0,
        le=20,
        description="Default top-k for retrieval.",
    )
    RAG_SIM_FLOOR: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Cosine-similarity coarse pre-filter.",
    )
    RAG_EMBED_BATCH: int = Field(
        default=32,
        gt=0,
        le=100,
        description="Embedding batch size for ingest.",
    )
    RAG_PROVIDER_CONCURRENCY: int = Field(
        default=2,
        gt=0,
        le=16,
        description="Bounded concurrency for per-page LLM calls.",
    )
    RAG_QUOTED_SPAN_MAX: int = Field(
        default=400,
        gt=0,
        le=1000,
        description="Per-citation quoted-span cap in API responses.",
    )
    RAG_QUESTION_MAX_LEN: int = Field(
        default=1000,
        gt=0,
        le=10000,
        description="Question length cap.",
    )
    RAG_MAX_UPLOAD_BYTES: int = Field(
        default=104857600,  # 100 MiB
        gt=0,
        le=1073741824,  # 1 GiB sanity bound
        description="Maximum size of an uploaded PDF in bytes.",
    )
    RAG_PDF_STORAGE_DIR: Path = Field(
        default=Path("data/pdfs"),
        description="Directory where ingested PDF bytes are persisted.",
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