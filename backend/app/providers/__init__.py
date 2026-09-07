"""Provider abstraction.

Every LLM and embedding call in the system goes through the interfaces defined
here. Pipeline code never imports a provider SDK or an HTTP client directly.
Swapping Groq for Ollama or a frontier key is a change in configuration, never
in code.
"""

from app.providers.base import (
    CompletionRequest,
    CompletionResult,
    EmbeddingProvider,
    LLMProvider,
    ProviderError,
)
from app.providers.factory import get_embedding_provider, get_llm_provider

__all__ = [
    "CompletionRequest",
    "CompletionResult",
    "EmbeddingProvider",
    "LLMProvider",
    "ProviderError",
    "get_embedding_provider",
    "get_llm_provider",
]
