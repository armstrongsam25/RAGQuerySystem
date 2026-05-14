"""Test fixtures shared across the unit and integration tiers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest

# A minimal "valid" environment for the Settings model. Tests that exercise
# the missing-key refusal path use ``invalid_env`` instead.
_VALID_ENV: dict[str, str] = {
    "GEMINI_API_KEY": "test-key-please-ignore",
    "DATABASE_URL": "postgresql://rag:rag@db:5432/rag",
    "POSTGRES_USER": "rag",
    "POSTGRES_PASSWORD": "rag",
    "POSTGRES_DB": "rag",
    "EMBEDDING_DIM": "768",
    "LOG_LEVEL": "INFO",
    "EMBEDDING_MODEL": "gemini-embedding-001",
    "GENERATION_MODEL": "gemini-2.5-flash",
    # Feature 002 additions:
    "RAG_TOP_K": "5",
    "RAG_SIM_FLOOR": "0.4",
    "RAG_EMBED_BATCH": "32",
    "RAG_GEMINI_CONCURRENCY": "4",
    "RAG_QUOTED_SPAN_MAX": "400",
    "RAG_QUESTION_MAX_LEN": "1000",
    "GROUNDING_JUDGE_BASE_URL": "http://localhost:1234/v1",
    "GROUNDING_JUDGE_API_KEY": "test-judge-key",
    "GROUNDING_JUDGE_MODEL": "test-judge-model",
}


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every env var the Settings model cares about."""
    for key in _VALID_ENV:
        monkeypatch.delenv(key, raising=False)
    from rag.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def valid_env(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Populate the env with the canonical valid values."""
    for key, value in _VALID_ENV.items():
        monkeypatch.setenv(key, value)
    return dict(_VALID_ENV)


@pytest.fixture
def settings(valid_env: dict[str, str]):
    """A populated Settings instance for feature-002 unit tests."""
    from rag.config import Settings

    return Settings()  # type: ignore[call-arg]


# --- Fake async DB pool for the /health unit test ------------------------


class _FakeCursor:
    def __init__(self, *, raises: Exception | None) -> None:
        self._raises = raises
        self._fetched = False

    async def __aenter__(self) -> _FakeCursor:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None

    async def execute(self, _sql: str, _params: Any = None) -> None:
        if self._raises is not None:
            raise self._raises

    async def fetchone(self) -> tuple[int]:
        self._fetched = True
        return (1,)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor


class _FakeConnectionCM:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConnection:
        return self._conn

    async def __aexit__(self, *_exc: Any) -> None:
        return None


class FakePool:
    """Minimal stand-in for psycopg's :class:`AsyncConnectionPool`."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises

    def connection(self) -> _FakeConnectionCM:
        cursor = _FakeCursor(raises=self._raises)
        return _FakeConnectionCM(_FakeConnection(cursor))

    async def open(self, **_kw: Any) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def fake_pool_ok() -> FakePool:
    return FakePool()


@pytest.fixture
def fake_pool_failing() -> FakePool:
    return FakePool(raises=RuntimeError("simulated database error"))


# --- Feature 002 fakes: LLMProvider + repository ------------------------


class FakeProvider:
    """Scripted in-process LLM provider for hermetic tests.

    Each verb can be:
      * a callable (sync or async — we'll await if it returns a coroutine)
      * a fixed return value
      * an Exception instance (raised when the verb is called)
    None means "the verb is not configured, raise NotImplementedError."
    """

    def __init__(
        self,
        *,
        embed=None,
        complete=None,
        judge=None,
    ) -> None:
        self._embed = embed
        self._complete = complete
        self._judge = judge
        self.embed_calls: list[list[str]] = []
        self.complete_calls: list[dict] = []
        self.judge_calls: list[dict] = []

    @staticmethod
    async def _resolve(scripted, *args, **kwargs):
        if scripted is None:
            raise NotImplementedError("verb not configured on FakeProvider")
        if isinstance(scripted, Exception):
            raise scripted
        if callable(scripted):
            result = scripted(*args, **kwargs)
            # Best-effort awaitable handling
            if hasattr(result, "__await__"):
                return await result
            return result
        return scripted

    async def embed(self, texts):
        self.embed_calls.append(list(texts))
        return await self._resolve(self._embed, texts)

    async def complete(self, *, system, user, model=None):
        self.complete_calls.append({"system": system, "user": user, "model": model})
        return await self._resolve(self._complete, system=system, user=user, model=model)

    async def judge(self, *, question, answer, passages):
        self.judge_calls.append({"question": question, "answer": answer, "passages": passages})
        return await self._resolve(self._judge, question=question, answer=answer, passages=passages)


@pytest.fixture
def memory_repo():
    """A fresh in-memory chunk repository for each test."""
    from rag.repositories import InMemoryChunkRepository

    return InMemoryChunkRepository()


@pytest.fixture
def fixture_doc_id():
    """A stable per-test source_document_id for seeded chunks."""
    return uuid4()


@pytest.fixture
async def seeded_repo(memory_repo, fixture_doc_id):
    """An in-memory repo seeded with three well-known 3-dim fixture chunks.

    Embeddings are tiny (3-dim) for hermetic tests. Callers MUST construct
    a Settings instance with EMBEDDING_DIM=3 (or use the small_dim_settings
    fixture) so the pipeline's dim check passes.
    """
    from rag.repositories.base import ChunkRecord

    chunks = [
        ChunkRecord(
            source_document_id=fixture_doc_id,
            page_number=1,
            char_offset_start=0,
            char_offset_end=31,
            raw_text="The capital of France is Paris.",
            token_count=8,
            embedding=[1.0, 0.0, 0.0],
        ),
        ChunkRecord(
            source_document_id=fixture_doc_id,
            page_number=2,
            char_offset_start=0,
            char_offset_end=31,
            raw_text="Patients must fast for 8 hours.",
            token_count=7,
            embedding=[0.0, 1.0, 0.0],
        ),
        ChunkRecord(
            source_document_id=fixture_doc_id,
            page_number=3,
            char_offset_start=0,
            char_offset_end=41,
            raw_text="Sherlock Holmes is a fictional detective.",
            token_count=7,
            embedding=[0.0, 0.0, 1.0],
        ),
    ]
    await memory_repo.add_chunks(chunks, source_document_id=fixture_doc_id)
    return memory_repo


@pytest.fixture
def small_dim_settings(valid_env, monkeypatch):
    """Settings with EMBEDDING_DIM=3 for hermetic tests using fixture chunks."""
    monkeypatch.setenv("EMBEDDING_DIM", "3")
    monkeypatch.setenv("RAG_SIM_FLOOR", "0.1")
    from rag.config import Settings, get_settings

    get_settings.cache_clear()
    return Settings()  # type: ignore[call-arg]


# --- Feature 003 fakes: pool + connection that pass through to in-memory ---


class _FakeTxn:
    """Async context manager standing in for ``psycopg.AsyncConnection.transaction()``."""

    def __init__(self, conn: _FakeUploadConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeTxn:
        self._conn.txn_depth += 1
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._conn.txn_depth -= 1
        if exc is not None:
            self._conn.rolled_back += 1


class _FakeUploadConn:
    """Connection stand-in for the upload route's transactional block.

    Records transaction enter/exit and whether rollback fired so tests
    can assert the route correctly opened (and on failure, rolled back)
    its transaction. The in-memory repo ignores the connection param,
    so this object's only job is to satisfy the
    ``async with pool.connection() as conn, conn.transaction():`` shape.
    """

    def __init__(self) -> None:
        self.txn_depth = 0
        self.rolled_back = 0

    def transaction(self) -> _FakeTxn:
        return _FakeTxn(self)


class _FakeUploadConnCM:
    def __init__(self, conn: _FakeUploadConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeUploadConn:
        return self._conn

    async def __aexit__(self, *_exc: Any) -> None:
        return None


class FakeUploadPool:
    """``psycopg_pool.AsyncConnectionPool`` stand-in for upload route tests.

    Returns one shared :class:`_FakeUploadConn` so tests can inspect its
    rollback bookkeeping after the request completes.
    """

    def __init__(self) -> None:
        self.conn = _FakeUploadConn()

    def connection(self) -> _FakeUploadConnCM:
        return _FakeUploadConnCM(self.conn)

    async def open(self, **_kw: Any) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def fake_upload_pool() -> FakeUploadPool:
    return FakeUploadPool()


_MINIMAL_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"
"""A tiny byte-string that passes the PDF magic-header check.

Not a structurally valid PDF (no xref, no proper objects), but the route
only checks the first 5 bytes — and the unit tests monkey-patch the
ingest pipeline so the bytes never reach Gemini.
"""


@pytest.fixture
def minimal_pdf_bytes() -> bytes:
    return _MINIMAL_PDF


# Configure logging at INFO for the whole test session. The default
# Python logging level is WARNING, which short-circuits ``logger.info(...)``
# BEFORE the LogRecord is built. That hid a real production bug where
# ``extra={"message": ...}`` collides with LogRecord's reserved ``message``
# attribute and raises KeyError at INFO emission. With logging at INFO
# here, the same code path the user runs in production runs in tests too.
@pytest.fixture(autouse=True, scope="session")
def _configure_test_logging() -> None:
    import logging

    logging.getLogger().setLevel(logging.INFO)


# Sanity: make sure the test process never accidentally connects to a
# real database — if a test forgets to bypass the lifespan, fail loudly.
@pytest.fixture(autouse=True)
def _block_real_db_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.environ.get("RUN_INTEGRATION") == "1":
        return  # integration tier may use the real DB
    import psycopg

    def _refuse(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(
            "Unit tests must not open real DB connections. Did you forget to "
            "use create_app(lifespan=_noop_lifespan) or to mock the call?"
        )

    monkeypatch.setattr(psycopg, "connect", _refuse)
