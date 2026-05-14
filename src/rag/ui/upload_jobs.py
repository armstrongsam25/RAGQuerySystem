"""In-process upload-job registry for the feature-003 background-task model.

The upload route spawns the actual ingest work in an ``asyncio.Task`` so
the POST response can return immediately with an in-progress partial.
The browser then polls ``GET /ui/upload/status/{task_id}`` every ~500ms
to refresh the status; when the task completes (or errors / cancels),
the status endpoint returns the final partial and polling stops.

State lives on ``app.state.upload_jobs`` so it's process-local; multi-
worker deployments would need a Postgres-backed queue instead, but
that's out of scope per the single-worker demo deployment.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

UploadStatus = Literal["pending", "running", "complete", "error", "cancelled"]


@dataclass
class UploadJob:
    """One in-flight or completed upload.

    The route's POST handler creates the job and spawns the background
    task; the task updates ``stage``/``stage_message`` as it progresses
    and sets ``status`` + ``result_html`` when it terminates. The polling
    status endpoint reads these fields and the cancel endpoint sets
    ``cancel_event``.
    """

    task_id: str
    filename: str
    status: UploadStatus = "pending"
    stage: str = "pending"
    stage_message: str = "Starting upload…"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # When status flips to complete/error/cancelled, result_html holds the
    # fully-rendered HTML fragment the status endpoint will return.
    result_html: str | None = None
    # The status endpoint can return a non-200 HTTP code for terminal
    # error states; capture it here so the rendered HTML and the response
    # status code line up.
    result_status_code: int = 200
    # Signal set by `/ui/upload/cancel/{task_id}`; polled by the
    # background task's ``cancel_check`` so the open transaction rolls back.
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    # Strong reference to the background ``asyncio.Task`` so it isn't
    # garbage-collected while running. Populated by the route after
    # ``asyncio.create_task``.
    task: asyncio.Task | None = None

    def set_progress(self, stage: str, message: str) -> None:
        """Update the job's stage + reviewer-readable message."""
        self.stage = stage
        self.stage_message = message
        # Once any progress reports come in, the job is running.
        if self.status == "pending":
            self.status = "running"

    def finish_complete(self, result_html: str) -> None:
        self.status = "complete"
        self.stage = "complete"
        self.stage_message = "Upload complete."
        self.result_html = result_html
        self.result_status_code = 200

    def finish_error(self, result_html: str, *, status_code: int = 503) -> None:
        self.status = "error"
        self.stage = "error"
        self.stage_message = "Upload failed."
        self.result_html = result_html
        self.result_status_code = status_code

    def finish_cancelled(self, result_html: str) -> None:
        self.status = "cancelled"
        self.stage = "cancelled"
        self.stage_message = "Upload cancelled."
        self.result_html = result_html
        self.result_status_code = 200

    @property
    def is_terminal(self) -> bool:
        return self.status in ("complete", "error", "cancelled")
