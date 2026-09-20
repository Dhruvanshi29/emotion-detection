"""Groq Whisper (OpenAI-compatible /audio/transcriptions endpoint).

Docs: https://console.groq.com/docs/speech-text
"""
from __future__ import annotations

from typing import Optional

import httpx

from app.core.config import Settings
from app.services.stt.base import (
    STTProvider,
    STTProviderError,
    STTResult,
    STTSegment,
)


class GroqWhisperProvider(STTProvider):
    name = "groq"

    def __init__(self, settings: Settings):
        self._api_key = settings.groq_api_key
        self._base_url = settings.groq_base_url.rstrip("/")
        self._model = settings.groq_stt_model

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: Optional[str] = None,
        timeout: float = 60.0,
    ) -> STTResult:
        url = f"{self._base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        data = {
            "model": self._model,
            "response_format": "verbose_json",
            "temperature": "0",
        }
        if language:
            data["language"] = language
        files = {"file": (filename, audio, content_type or "application/octet-stream")}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, headers=headers, data=data, files=files)
        except httpx.HTTPError as e:
            raise STTProviderError(
                self.name, f"network error: {type(e).__name__}: {e or repr(e)}"
            ) from e

        if r.status_code >= 400:
            raise STTProviderError(
                self.name,
                f"HTTP {r.status_code}: {r.text[:400]}",
                status=r.status_code,
            )

        try:
            body = r.json()
        except ValueError as e:
            raise STTProviderError(
                self.name, f"invalid JSON response: {e}"
            ) from e

        text = (body.get("text") or "").strip()
        segments_raw = body.get("segments") or []
        segments = []
        for seg in segments_raw:
            try:
                segments.append(
                    STTSegment(
                        start=float(seg.get("start", 0.0)),
                        end=float(seg.get("end", 0.0)),
                        text=str(seg.get("text", "")).strip(),
                    )
                )
            except (TypeError, ValueError):
                continue

        duration: Optional[float] = None
        try:
            if "duration" in body:
                duration = float(body["duration"])
            elif segments:
                duration = segments[-1].end
        except (TypeError, ValueError):
            duration = None

        return STTResult(
            text=text,
            provider=self.name,
            model=self._model,
            language=body.get("language") or None,
            duration_seconds=duration,
            segments=segments,
        )
