"""Trace-ID helpers.

Per research R-019, every query carries a `trace_id` (uuid4 hex) passed as
an explicit kwarg through retrieve → generate → judge → respond. We do NOT
use `ContextVar` — explicit kwargs are grep-able and visible at every call
site, which matters for the demo-narratable codebase Art VIII.2 calls for.
"""

from __future__ import annotations

import uuid

# Log-record extra key used everywhere a trace_id is attached to a structured
# log line. Centralized so a future search for "trace_id" finds every site.
TRACE_LOG_KEY = "trace_id"


def new_trace_id() -> str:
    """Return a fresh trace id (uuid4 hex, no dashes)."""
    return uuid.uuid4().hex
