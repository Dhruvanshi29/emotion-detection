"""Speech-to-text service (plan §7, Addendum §A).

Provider-agnostic, same pattern as the LLM router. Providers implement a
minimal ABC and the router falls back down a configured chain on failure.
Raw audio is NEVER persisted (plan §18).
"""
from app.services.stt.base import (
    STTProvider,
    STTProviderError,
    STTResult,
    STTSegment,
)
from app.services.stt.router import STTRouter, get_stt_router

__all__ = [
    "STTProvider",
    "STTProviderError",
    "STTResult",
    "STTSegment",
    "STTRouter",
    "get_stt_router",
]
