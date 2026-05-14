"""Unit tests for the Settings model (spec FR-003, FR-004; clarification Q3)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError


def test_valid_env_loads(valid_env: dict[str, str]) -> None:
    from rag.config import Settings

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert isinstance(settings.GEMINI_API_KEY, SecretStr)
    assert settings.GEMINI_API_KEY.get_secret_value() == valid_env["GEMINI_API_KEY"]
    assert settings.EMBEDDING_DIM == 768
    assert settings.LOG_LEVEL == "INFO"
    assert str(settings.DATABASE_URL).startswith("postgresql://")


def test_missing_gemini_key_raises_with_field_name(clean_env: None) -> None:
    from rag.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]

    # Spec FR-003: the error MUST name the missing variable.
    errors = exc_info.value.errors()
    fields = {tuple(e["loc"]) for e in errors}
    assert ("GEMINI_API_KEY",) in fields, f"GEMINI_API_KEY missing from {fields!r}"


def test_empty_gemini_key_raises(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from rag.config import Settings

    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "postgresql://rag:rag@db:5432/rag")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]

    errors = exc_info.value.errors()
    fields = {tuple(e["loc"]) for e in errors}
    assert ("GEMINI_API_KEY",) in fields


# Note on env-var typo detection: pydantic-settings reads env vars by
# looking up declared field names. An unknown name (e.g., GEMINY_API_KEY)
# is silently ignored rather than rejected — `extra="forbid"` only catches
# extras in direct kwargs, not in the env-loading path. This is standard
# behavior and not worth a defensive scan; it is documented here so a
# reader doesn't expect protection that doesn't exist.


def test_invalid_log_level_rejected(
    valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from rag.config import Settings

    monkeypatch.setenv("LOG_LEVEL", "TRACE")  # not in the Literal set

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_embedding_dim_default(valid_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Constitution Art IV pins 768; default MUST be 768 when unset."""
    from rag.config import Settings

    monkeypatch.delenv("EMBEDDING_DIM", raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.EMBEDDING_DIM == 768
