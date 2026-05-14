"""Small RAG system (boilerplate)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("rag")
except PackageNotFoundError:  # pragma: no cover — happens only in unbuilt source trees
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
