"""Provider-agnostic LLM adapters.

Public API: `get_llm_router()` returns an `LLMRouter` that tries providers
in the configured fallback chain (see LLM_PROVIDER_CHAIN in .env).
"""

from .base import ChatMessage, LLMProvider, LLMProviderError, LLMResponse
from .router import LLMRouter, get_llm_router

__all__ = [
    "ChatMessage",
    "LLMProvider",
    "LLMProviderError",
    "LLMResponse",
    "LLMRouter",
    "get_llm_router",
]
