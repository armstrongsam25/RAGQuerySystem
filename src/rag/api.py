"""FastAPI app + routes.

Routes:
  * `GET /health`     — feature 001 health endpoint (SELECT 1 + schema_version).
  * `POST /query`     — feature 002 JSON query path.
  * `GET /`           — feature 002 HTMX UI page shell.
  * `POST /ui/query`  — feature 002 HTMX form-submit endpoint.

The factory pattern (:func:`create_app`) lets tests build an app with a
no-op lifespan and inject fakes via ``app.state``; production code calls
``create_app()`` with the real lifespan from :mod:`rag.lifespan`.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from rag.config import Settings
from rag.db import Pool, ping
from rag.lifespan import lifespan as default_lifespan
from rag.log import get_logger
from rag.providers.base import Providers, UpstreamProviderError
from rag.query.pipeline import answer_question
from rag.query.responses import (
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)
from rag.repositories.base import ChunkRepository
from rag.trace import TRACE_LOG_KEY, new_trace_id

logger = get_logger(__name__)


# --- Health response models (unchanged from feature 001) -----------------


class HealthOk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    schema_version: str
    db: Literal["ok"] = "ok"
    embedding_model: str
    embedding_dim: int


class HealthUnhealthy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["unhealthy"] = "unhealthy"
    schema_version: str
    db: Literal["error"] = "error"
    error: str


# --- Dependency providers ------------------------------------------------


def get_pool(request: Request) -> Pool:
    return request.app.state.pool


def get_schema_version(request: Request) -> str:
    return request.app.state.schema_version


def get_settings_state(request: Request) -> Settings:
    return request.app.state.settings


def get_chunk_repo(request: Request) -> ChunkRepository:
    return request.app.state.chunk_repo


def get_providers(request: Request) -> Providers:
    return request.app.state.providers


# --- App factory ---------------------------------------------------------


@asynccontextmanager
async def _noop_lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Test lifespan: yields immediately. State is injected by the test."""
    yield


LifespanFn = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(*, lifespan: LifespanFn = default_lifespan) -> FastAPI:
    """Build a FastAPI app. Default uses the real lifespan."""
    app = FastAPI(
        title="RAG Query Service",
        version="0.2.0",
        lifespan=lifespan,
    )

    # ---- /health (feature 001) -----------------------------------------

    @app.get(
        "/health",
        responses={
            200: {"model": HealthOk},
            503: {"model": HealthUnhealthy},
        },
    )
    async def health(
        response: Response,
        pool: Annotated[Pool, Depends(get_pool)],
        schema_version: Annotated[str, Depends(get_schema_version)],
        settings: Annotated[Settings, Depends(get_settings_state)],
    ) -> HealthOk | HealthUnhealthy:
        started = time.perf_counter()
        try:
            await ping(pool)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 — /health MUST turn any failure into a 503
            duration_ms = (time.perf_counter() - started) * 1000.0
            logger.warning(
                "health_check",
                extra={
                    "event": "health_check",
                    "status": "error",
                    "duration_ms": round(duration_ms, 2),
                    "error": str(exc),
                },
            )
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return HealthUnhealthy(schema_version=schema_version, error=str(exc))

        duration_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "health_check",
            extra={
                "event": "health_check",
                "status": "ok",
                "duration_ms": round(duration_ms, 2),
            },
        )
        return HealthOk(
            schema_version=schema_version,
            embedding_model=settings.EMBEDDING_MODEL,
            embedding_dim=settings.EMBEDDING_DIM,
        )

    # ---- POST /query (feature 002) -------------------------------------

    @app.post(
        "/query",
        responses={
            200: {"model": QueryResponse},
            400: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def query(
        body: QueryRequest,
        response: Response,
        repo: Annotated[ChunkRepository, Depends(get_chunk_repo)],
        providers: Annotated[Providers, Depends(get_providers)],
        settings: Annotated[Settings, Depends(get_settings_state)],
    ) -> QueryResponse | ErrorResponse:
        trace_id = new_trace_id()
        response.headers["X-RAG-Trace-Id"] = trace_id
        try:
            result = await answer_question(
                body.question,
                repo=repo,
                providers=providers,
                settings=settings,
                trace_id=trace_id,
                top_k_override=body.top_k,
            )
        except ValueError as exc:
            error_code = (
                "empty_question"
                if "non-empty" in str(exc)
                else "question_too_long"
                if "exceeds" in str(exc)
                else "bad_request"
            )
            logger.info(
                # NB: ``error_message`` not ``message`` — ``message`` is a
                # reserved attribute on ``LogRecord`` and the stdlib
                # raises KeyError at INFO emission time otherwise.
                "query_bad_request",
                extra={TRACE_LOG_KEY: trace_id, "error": error_code, "error_message": str(exc)},
            )
            return JSONResponse(  # type: ignore[return-value]
                status_code=400,
                content=ErrorResponse(
                    error=error_code,
                    message=str(exc),
                    trace_id=trace_id,
                ).model_dump(),
                headers={"X-RAG-Trace-Id": trace_id},
            )
        except UpstreamProviderError as exc:
            logger.warning(
                "query_upstream_failure",
                extra={
                    TRACE_LOG_KEY: trace_id,
                    "provider": exc.provider,
                    "cause": str(exc.cause),
                },
            )
            return JSONResponse(  # type: ignore[return-value]
                status_code=503,
                content=ErrorResponse(
                    error=f"upstream_{exc.provider}",
                    message=str(exc.cause),
                    trace_id=trace_id,
                ).model_dump(),
                headers={"X-RAG-Trace-Id": trace_id},
            )

        return result

    # ---- HTMX UI routes -------------------------------------------------

    from rag.ui import register_ui_routes

    register_ui_routes(app)

    return app


# Module-level instance for `uvicorn rag.api:app`.
app = create_app()
