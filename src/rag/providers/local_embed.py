"""Local embedding provider using fastembed (ONNX-based).

Uses BAAI/bge-base-en-v1.5 (768 dims) to match the default schema.
No API key needed — downloads the model on first use and runs locally.

Replaces the need for an external embedding API when the vLLM/OpenAI
endpoint doesn't provide embedding models.
"""

from __future__ import annotations

from fastembed import TextEmbedding

from rag.config import Settings


class LocalEmbeddingProvider:
    """Embedding-only provider using fastembed (BAAI/bge-base-en-v1.5).

    This is a standalone embedder, not a full LLMProvider. It's used
    alongside OpenAIProvider for the embedding leg of the pipeline.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # Use bge-base-en-v1.5 for 768-dim embeddings matching the schema.
        # bge-small would give 384 and require schema migration.
        self._model = TextEmbedding(
            model_name="BAAI/bge-base-en-v1.5",
            cache_dir=None,  # uses default HF cache
            threads=0,  # auto-detect
        )
        actual_dim = self._model.embedding_size
        if actual_dim != settings.EMBEDDING_DIM:
            raise RuntimeError(
                f"Embedding dimension mismatch: model produces {actual_dim}, "
                f"but EMBEDDING_DIM is set to {settings.EMBEDDING_DIM}. "
                f"Update EMBEDDING_DIM or use a different embedding model."
            )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        if not texts:
            return []
        # fastembed is synchronous; run in thread pool to avoid blocking
        import asyncio

        def _embed() -> list[list[float]]:
            return [list(vec) for vec in self._model.embed(texts)]

        return await asyncio.to_thread(_embed)