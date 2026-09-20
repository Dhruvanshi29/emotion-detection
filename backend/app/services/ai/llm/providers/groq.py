from __future__ import annotations

from app.core.config import Settings
from app.services.ai.llm._openai_compat import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    """Groq (console.groq.com) — OpenAI-compatible, free tier, very low latency."""

    def __init__(self, settings: Settings):
        super().__init__(
            name="groq",
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=settings.groq_model,
        )
