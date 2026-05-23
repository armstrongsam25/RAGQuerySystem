"""Unit tests for the /health endpoint (spec FR-002; clarification Q2)."""

from __future__ import annotations

import httpx
import pytest

from rag.api import _noop_lifespan, create_app
from rag.config import Settings
from tests.conftest import FakePool


def _build_app(pool: FakePool) -> object:
    app = create_app(lifespan=_noop_lifespan)
    app.state.pool = pool
    app.state.schema_version = "0001_init_vector_store.sql"
    app.state.settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        LLM_API_KEY="test-key-please-ignore",
        DATABASE_URL="postgresql://rag:rag@db:5432/rag",
    )
    return app


@pytest.mark.asyncio
async def test_health_ok_returns_documented_payload(fake_pool_ok: FakePool) -> None:
    app = _build_app(fake_pool_ok)
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    # Shape MUST match contracts/health.yaml HealthOk.
    assert set(body) == {"status", "schema_version", "db", "embedding_model", "embedding_dim"}
    # Default EMBEDDING_MODEL is "text-embedding-3-small"
    assert body == {
        "status": "ok",
        "schema_version": "0001_init_vector_store.sql",
        "db": "ok",
        "embedding_model": "text-embedding-3-small",
        "embedding_dim": 768,
    }


@pytest.mark.asyncio
async def test_health_returns_503_on_db_failure(fake_pool_failing: FakePool) -> None:
    app = _build_app(fake_pool_failing)
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 503
    body = resp.json()
    # Shape MUST match contracts/health.yaml HealthUnhealthy.
    assert set(body) == {"status", "schema_version", "db", "error"}
    assert body["status"] == "unhealthy"
    assert body["db"] == "error"
    assert body["schema_version"] == "0001_init_vector_store.sql"
    assert "simulated database error" in body["error"]