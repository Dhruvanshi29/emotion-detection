from __future__ import annotations

from app.core.config import Settings
from app.services.ai.llm._openai_compat import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter (openrouter.ai) — OpenAI-compatible, many `:free` models."""

    def __init__(self, settings: Settings):
        # OpenRouter recommends these headers for attribution / rate-limit tiers.
        extra = {
            "HTTP-Referer": settings.openrouter_app_url,
            "X-Title": settings.openrouter_app_name,
        }
        super().__init__(
            name="openrouter",
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.openrouter_model,
            extra_headers=extra,
        )
