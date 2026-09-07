"""Local sentence-transformers embedding provider.

The model is loaded lazily on first use and reused for the process lifetime.
Encoding runs in a worker thread so it never blocks the event loop.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from app.providers.base import EmbeddingProvider, ProviderError

if TYPE_CHECKING:  # pragma: no cover
    from sentence_transformers import SentenceTransformer

# Known output dimensions for the models named in .env.example, so callers
# (and migrations) can size the vector column before the model is downloaded.
_KNOWN_DIMENSIONS = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "nomic-ai/nomic-embed-text-v1.5": 768,
}


class LocalEmbeddingProvider(EmbeddingProvider):
    name = "sentence-transformers"

    def __init__(self, *, model_name: str, device: str) -> None:
        self._model_name = model_name
        self._device = device
        self._model: SentenceTransformer | None = None
        self._load_lock = threading.Lock()
        self.dimension = _KNOWN_DIMENSIONS.get(model_name, 0)

    def _ensure_model(self) -> SentenceTransformer:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:  # pragma: no cover
                    raise ProviderError(
                        "sentence-transformers is not installed; embeddings are required"
                    ) from exc
                model = SentenceTransformer(self._model_name, device=self._device)
                self.dimension = model.get_sentence_embedding_dimension()
                self._model = model
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        def _encode() -> list[list[float]]:
            model = self._ensure_model()
            vectors = model.encode(
                texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return vectors.tolist()

        return await asyncio.to_thread(_encode)
