"""Live /health test against a running `make up` stack.

Skipped silently unless ``RUN_INTEGRATION=1`` (the pytest ``addopts`` in
:file:`pyproject.toml` filters this out of the default ``make test`` run).
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.integration

_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000")


@pytest.mark.asyncio
async def test_health_live_returns_documented_payload() -> None:
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=5.0) as client:
        resp = await client.get("/health")

    assert resp.status_code == 200, f"unexpected status {resp.status_code}: {resp.text!r}"
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["schema_version"] == "0001_init_vector_store.sql"
    assert body["embedding_dim"] == 768
    assert body["embedding_model"] == "gemini-embedding-001"
