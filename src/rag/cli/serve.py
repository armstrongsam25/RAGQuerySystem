"""`rag serve` — wrap uvicorn so the container entry point matches the CLI surface."""

from __future__ import annotations

import typer
import uvicorn


def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host."),
    port: int = typer.Option(8000, "--port", help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Enable uvicorn auto-reload (dev)."),
) -> None:
    """Run the FastAPI service via uvicorn."""
    uvicorn.run(
        "rag.api:app",
        host=host,
        port=port,
        reload=reload,
        log_config=None,  # let our own log config take effect via lifespan
    )
