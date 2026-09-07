"""A single embedding per document: the mean of a sample of its chunk texts."""

from __future__ import annotations

from collections.abc import Sequence

from app.models.constants import EMBEDDING_DIM
from app.providers import get_embedding_provider
from app.providers.base import EmbeddingProvider

_MAX_SAMPLE_CHUNKS = 48
_CHARS_PER_CHUNK = 500


async def compute_document_embedding(
    chunk_texts: Sequence[str],
    *,
    provider: EmbeddingProvider | None = None,
) -> list[float]:
    provider = provider or get_embedding_provider()
    texts = [t.strip()[:_CHARS_PER_CHUNK] for t in chunk_texts if t and t.strip()]
    texts = texts[:_MAX_SAMPLE_CHUNKS]
    if not texts:
        return [0.0] * EMBEDDING_DIM

    vectors = await provider.embed(texts)
    dim = len(vectors[0])
    mean = [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]
    norm = sum(x * x for x in mean) ** 0.5
    return [x / norm for x in mean] if norm else mean
