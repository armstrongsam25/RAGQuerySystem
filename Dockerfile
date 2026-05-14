# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

# Install uv from the official image (no compilation, pinned).
COPY --from=ghcr.io/astral-sh/uv:0.4.30 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy application source.
COPY src/ src/
COPY migrations/ migrations/

# Install the project itself (now that the source is present).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8000

# Entry point goes through the `rag` console script (registered in
# pyproject.toml). `rag serve` wraps uvicorn so the same surface a
# developer uses locally (`uv run rag serve`) is what the container runs.
CMD ["rag", "serve", "--host", "0.0.0.0", "--port", "8000"]
