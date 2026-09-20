from __future__ import annotations

from app.core.config import Settings
from app.services.ai.llm._openai_compat import OpenAICompatibleProvider


class NvidiaProvider(OpenAICompatibleProvider):
    """NVIDIA NIM (build.nvidia.com) — OpenAI-compatible, free tier available."""

    def __init__(self, settings: Settings):
        extra_body = {}
        if settings.nvidia_reasoning_effort:
            extra_body["reasoning_effort"] = settings.nvidia_reasoning_effort
        super().__init__(
            name="nvidia",
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            model=settings.nvidia_model,
            extra_body=extra_body or None,
        )
