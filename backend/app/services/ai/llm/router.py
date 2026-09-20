from __future__ import annotations

import logging
from functools import lru_cache
from typing import AsyncIterator, Dict, List, Optional

from app.core.config import Settings, get_settings
from app.services.ai.llm.base import (
    ChatMessage,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
)
from app.services.ai.llm.providers.gemini import GeminiProvider
from app.services.ai.llm.providers.groq import GroqProvider
from app.services.ai.llm.providers.nvidia import NvidiaProvider
from app.services.ai.llm.providers.openrouter import OpenRouterProvider

logger = logging.getLogger(__name__)


def _build_registry(settings: Settings) -> Dict[str, LLMProvider]:
    return {
        "nvidia": NvidiaProvider(settings),
        "openrouter": OpenRouterProvider(settings),
        "groq": GroqProvider(settings),
        "gemini": GeminiProvider(settings),
    }


class LLMRouter:
    """Tries providers in the configured chain, falling back on failure."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._registry = _build_registry(settings)

    def available_providers(self) -> List[str]:
        return [
            name
            for name in self._settings.provider_chain
            if name in self._registry and self._registry[name].is_configured()
        ]

    def _chain(self, preferred: Optional[str]) -> List[LLMProvider]:
        order: List[str] = []
        if preferred:
            order.append(preferred.lower())
        for name in self._settings.provider_chain:
            if name not in order:
                order.append(name)

        chain: List[LLMProvider] = []
        for name in order:
            prov = self._registry.get(name)
            if prov and prov.is_configured():
                chain.append(prov)
        return chain

    async def complete(
        self,
        messages: List[ChatMessage],
        *,
        preferred: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        chain = self._chain(preferred)
        if not chain:
            raise LLMProviderError(
                "router",
                "no LLM providers configured — set at least one *_API_KEY in .env",
            )

        s = self._settings
        mt = max_tokens or s.llm_max_tokens
        temp = s.llm_temperature if temperature is None else temperature

        last_err: Optional[Exception] = None
        for prov in chain:
            try:
                logger.info("llm.complete provider=%s model attempt", prov.name)
                return await prov.complete(
                    messages,
                    max_tokens=mt,
                    temperature=temp,
                    timeout=s.llm_timeout_seconds,
                )
            except LLMProviderError as e:
                logger.warning("llm.complete provider=%s failed: %s", prov.name, e)
                last_err = e
                continue

        raise LLMProviderError(
            "router", f"all providers failed; last error: {last_err}"
        )

    async def stream(
        self,
        messages: List[ChatMessage],
        *,
        preferred: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        chain = self._chain(preferred)
        if not chain:
            raise LLMProviderError(
                "router",
                "no LLM providers configured — set at least one *_API_KEY in .env",
            )

        s = self._settings
        mt = max_tokens or s.llm_max_tokens
        temp = s.llm_temperature if temperature is None else temperature

        last_err: Optional[Exception] = None
        for prov in chain:
            emitted = False
            try:
                logger.info("llm.stream provider=%s attempt", prov.name)
                async for delta in prov.stream(
                    messages,
                    max_tokens=mt,
                    temperature=temp,
                    timeout=s.llm_timeout_seconds,
                ):
                    emitted = True
                    yield delta
                return
            except LLMProviderError as e:
                logger.warning("llm.stream provider=%s failed: %s", prov.name, e)
                last_err = e
                # If tokens were already sent to the client, we can't safely
                # switch providers mid-stream — surface the error.
                if emitted:
                    raise
                continue

        raise LLMProviderError(
            "router", f"all providers failed; last error: {last_err}"
        )


@lru_cache(maxsize=1)
def get_llm_router() -> LLMRouter:
    return LLMRouter(get_settings())
