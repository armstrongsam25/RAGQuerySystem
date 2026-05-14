"""HTMX UI on FastAPI per the 2026-05-12 Q1 clarification.

One Jinja2 base template + four partials, two routes on the existing
FastAPI app. No additional compose service.
"""

from rag.ui.routes import register_ui_routes

__all__ = ["register_ui_routes"]
