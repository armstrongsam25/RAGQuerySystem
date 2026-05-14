"""`rag eval` — stub (spec FR-007).

Function is named ``eval_cmd`` so we don't shadow the Python builtin
``eval``; the user-facing Typer command name is still ``eval``.
"""

from __future__ import annotations

import sys

import typer

from rag.log import get_logger

logger = get_logger(__name__)

_FEATURE_ID = "00X-eval-harness"


def eval_cmd() -> None:
    """Run the eval set and emit metrics. Not yet implemented."""
    logger.info(
        "cli_stub_invoked",
        extra={"event": "cli_stub_invoked", "command": "eval", "feature": _FEATURE_ID},
    )
    sys.stderr.write(f"rag eval: not yet implemented — delivered by feature {_FEATURE_ID}\n")
    raise typer.Exit(code=2)
