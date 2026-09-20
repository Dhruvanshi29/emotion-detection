from __future__ import annotations

import logging
from functools import lru_cache
from typing import Dict, List, Optional

from app.core.config import Settings, get_settings
from app.services.stt.base import STTProvider, STTProviderError, STTResult
from app.services.stt.providers.groq_whisper import GroqWhisperProvider

logger = logging.getLogger(__name__)


def _build_registry(settings: Settings) -> Dict[str, STTProvider]:
    return {"groq": GroqWhisperProvider(settings)}


class STTRouter:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._registry = _build_registry(settings)

    def available_providers(self) -> List[str]:
        return [
            name
            for name in self._settings.stt_provider_chain_list
            if name in self._registry and self._registry[name].is_configured()
        ]

    def _chain(self, preferred: Optional[str]) -> List[STTProvider]:
        order: List[str] = []
        if preferred:
            order.append(preferred.lower())
        for name in self._settings.stt_provider_chain_list:
            if name not in order:
                order.append(name)
        chain: List[STTProvider] = []
        for name in order:
            prov = self._registry.get(name)
            if prov and prov.is_configured():
                chain.append(prov)
        return chain

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: Optional[str] = None,
        preferred: Optional[str] = None,
    ) -> STTResult:
        chain = self._chain(preferred)
        if not chain:
            raise STTProviderError(
                "router",
                "no STT providers configured — set at least one STT key (e.g. GROQ_API_KEY)",
            )

        last_err: Optional[Exception] = None
        for prov in chain:
            try:
                logger.info("stt.transcribe provider=%s attempt", prov.name)
                return await prov.transcribe(
                    audio,
                    filename=filename,
                    content_type=content_type,
                    language=language,
                    timeout=self._settings.stt_timeout_seconds,
                )
            except STTProviderError as e:
                logger.warning("stt.transcribe provider=%s failed: %s", prov.name, e)
                last_err = e
                continue

        raise STTProviderError(
            "router", f"all providers failed; last error: {last_err}"
        )


@lru_cache(maxsize=1)
def get_stt_router() -> STTRouter:
    return STTRouter(get_settings())
