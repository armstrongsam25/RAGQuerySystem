"""Retry / 429 handling tests for the GeminiProvider wrapper."""

from __future__ import annotations

from typing import Any

import pytest
from google.genai import errors as genai_errors

from rag.providers.gemini import (
    RateLimitedError,
    _extract_retry_delay_s,
    _is_rate_limited,
    _is_retriable,
    _with_retry,
)


class _FakeAPIError(genai_errors.APIError):
    """Construct an APIError without the SDK's network response machinery."""

    def __init__(self, *, code: int, message: str) -> None:
        # genai_errors.APIError's normal constructor expects an SDK response
        # object; we bypass it for tests by setting attributes directly.
        Exception.__init__(self, message)
        self.code = code
        self.message = message
        self.status = "RESOURCE_EXHAUSTED" if code == 429 else "INTERNAL"

    def __str__(self) -> str:  # type: ignore[override]
        return self.message


def test_extract_retry_delay_pulls_seconds_from_blob():
    msg = "429 RESOURCE_EXHAUSTED. {'error': {...}, '@type': 'RetryInfo', 'retryDelay': '8s', ...}"
    assert _extract_retry_delay_s(msg) == 8.0


def test_extract_retry_delay_handles_fractional():
    msg = "{'retryDelay': '2.5s'}"
    assert _extract_retry_delay_s(msg) == 2.5


def test_extract_retry_delay_none_when_absent():
    assert _extract_retry_delay_s("just some error message") is None


def test_is_rate_limited_detects_429_attribute():
    exc = _FakeAPIError(code=429, message="too many requests")
    assert _is_rate_limited(exc) is True


def test_is_rate_limited_detects_429_in_message():
    exc = RuntimeError("some 429 RESOURCE_EXHAUSTED happened")
    assert _is_rate_limited(exc) is True


def test_is_rate_limited_false_on_other_codes():
    exc = _FakeAPIError(code=500, message="server error")
    assert _is_rate_limited(exc) is False


@pytest.mark.asyncio
async def test_with_retry_returns_value_on_first_success():
    calls = {"n": 0}

    def _ok() -> str:
        calls["n"] += 1
        return "ok"

    result = await _with_retry("test", _ok)
    assert result == "ok"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_with_retry_recovers_from_transient_429(monkeypatch):
    """Two 429s, then success → returns the success value."""
    # Speed up the test by patching asyncio.sleep to a no-op.
    import rag.providers.gemini as gemini_mod

    async def _noop_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(gemini_mod.asyncio, "sleep", _noop_sleep)

    calls = {"n": 0}

    def _flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeAPIError(code=429, message="429 RESOURCE_EXHAUSTED")
        return "finally"

    result = await _with_retry("test", _flaky)
    assert result == "finally"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_with_retry_raises_rate_limited_after_exhausting_budget(monkeypatch):
    import rag.providers.gemini as gemini_mod

    async def _noop_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(gemini_mod.asyncio, "sleep", _noop_sleep)

    def _always_429() -> str:
        raise _FakeAPIError(
            code=429,
            message="429 RESOURCE_EXHAUSTED. {'retryDelay': '5s'}",
        )

    with pytest.raises(RateLimitedError) as excinfo:
        await _with_retry("test", _always_429)
    assert excinfo.value.retry_hint_s == 5.0
    assert excinfo.value.provider == "gemini"


@pytest.mark.asyncio
async def test_with_retry_passes_through_non_429_errors():
    def _server_error() -> str:
        raise _FakeAPIError(code=500, message="internal")

    from rag.providers.base import UpstreamProviderError

    with pytest.raises(UpstreamProviderError) as excinfo:
        await _with_retry("test", _server_error)
    # Should be the generic UpstreamProviderError, not the rate-limit subclass.
    assert not isinstance(excinfo.value, RateLimitedError)


@pytest.mark.asyncio
async def test_with_retry_wraps_generic_exceptions(monkeypatch):
    """Non-APIError exceptions (e.g. network glitches) wrap as UpstreamProviderError."""
    from rag.providers.base import UpstreamProviderError

    def _boom() -> Any:
        raise RuntimeError("unexpected boom")

    with pytest.raises(UpstreamProviderError):
        await _with_retry("test", _boom)


def test_is_retriable_detects_503_unavailable():
    exc = _FakeAPIError(code=503, message="503 UNAVAILABLE. model overloaded")
    assert _is_retriable(exc) is True


def test_is_retriable_detects_504_deadline_exceeded():
    exc = _FakeAPIError(code=504, message="504 DEADLINE_EXCEEDED")
    assert _is_retriable(exc) is True


def test_is_retriable_still_covers_429():
    exc = _FakeAPIError(code=429, message="429 RESOURCE_EXHAUSTED")
    assert _is_retriable(exc) is True


def test_is_retriable_false_on_500_internal():
    # 500 INTERNAL deliberately left out of the retriable set — see _is_retriable docstring.
    exc = _FakeAPIError(code=500, message="500 INTERNAL")
    assert _is_retriable(exc) is False


@pytest.mark.asyncio
async def test_with_retry_recovers_from_transient_503(monkeypatch):
    """Two 503s, then success → returns the success value."""
    import rag.providers.gemini as gemini_mod

    async def _noop_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(gemini_mod.asyncio, "sleep", _noop_sleep)

    calls = {"n": 0}

    def _flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeAPIError(
                code=503,
                message="503 UNAVAILABLE. This model is currently experiencing high demand.",
            )
        return "recovered"

    result = await _with_retry("test", _flaky)
    assert result == "recovered"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_with_retry_raises_upstream_error_after_503_exhaustion(monkeypatch):
    """Persistent 503 → UpstreamProviderError (NOT RateLimitedError)."""
    import rag.providers.gemini as gemini_mod
    from rag.providers.base import UpstreamProviderError

    async def _noop_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(gemini_mod.asyncio, "sleep", _noop_sleep)

    def _always_503() -> str:
        raise _FakeAPIError(code=503, message="503 UNAVAILABLE")

    with pytest.raises(UpstreamProviderError) as excinfo:
        await _with_retry("test", _always_503)
    # The CLI keys off RateLimitedError specifically — 503 should NOT trigger
    # the quota-exhaustion message.
    assert not isinstance(excinfo.value, RateLimitedError)
    assert excinfo.value.provider == "gemini"
