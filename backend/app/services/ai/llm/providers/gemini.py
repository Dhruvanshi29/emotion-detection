"""Google Gemini via the Generative Language REST API (aistudio.google.com).

Free tier: https://aistudio.google.com/app/apikey
Docs:     https://ai.google.dev/api/generate-content

Gemini has its own schema (not OpenAI-compatible), so we translate
`ChatMessage[]` -> Gemini `contents` and stream via `streamGenerateContent`
with `alt=sse`.
"""

from __future__ import annotations

import json
from typing import AsyncIterator, Dict, List

import httpx

from app.core.config import Settings
from app.services.ai.llm.base import (
    ChatMessage,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
)


def _to_gemini_contents(messages: List[ChatMessage]) -> Dict:
    system_parts: List[str] = []
    contents: List[Dict] = []
    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
            continue
        role = "user" if m.role == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m.content}]})

    body: Dict = {"contents": contents}
    if system_parts:
        body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return body


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, settings: Settings):
        self._api_key = settings.gemini_api_key
        self._base_url = settings.gemini_base_url.rstrip("/")
        self._model = settings.gemini_model

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _gen_config(self, max_tokens: int, temperature: float) -> Dict:
        return {"maxOutputTokens": max_tokens, "temperature": temperature}

    async def complete(
        self,
        messages: List[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> LLMResponse:
        url = f"{self._base_url}/models/{self._model}:generateContent"
        body = _to_gemini_contents(messages)
        body["generationConfig"] = self._gen_config(max_tokens, temperature)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    url,
                    params={"key": self._api_key},
                    json=body,
                    headers={"Content-Type": "application/json"},
                )
        except httpx.HTTPError as e:
            raise LLMProviderError(self.name, f"network error: {e}") from e

        if r.status_code >= 400:
            raise LLMProviderError(
                self.name,
                f"HTTP {r.status_code}: {r.text[:400]}",
                status=r.status_code,
            )

        try:
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, ValueError) as e:
            raise LLMProviderError(self.name, f"bad response shape: {e}") from e

        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=self._model,
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
        )

    async def stream(
        self,
        messages: List[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> AsyncIterator[str]:
        url = f"{self._base_url}/models/{self._model}:streamGenerateContent"
        body = _to_gemini_contents(messages)
        body["generationConfig"] = self._gen_config(max_tokens, temperature)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    params={"key": self._api_key, "alt": "sse"},
                    json=body,
                    headers={"Content-Type": "application/json"},
                ) as r:
                    if r.status_code >= 400:
                        body_text = (await r.aread()).decode("utf-8", errors="replace")
                        raise LLMProviderError(
                            self.name,
                            f"HTTP {r.status_code}: {body_text[:400]}",
                            status=r.status_code,
                        )
                    async for raw in r.aiter_lines():
                        if not raw or not raw.startswith("data:"):
                            continue
                        data = raw[5:].strip()
                        if not data:
                            continue
                        try:
                            chunk = json.loads(data)
                            parts = chunk["candidates"][0]["content"]["parts"]
                            delta = "".join(p.get("text", "") for p in parts)
                        except (KeyError, IndexError, ValueError):
                            continue
                        if delta:
                            yield delta
        except httpx.HTTPError as e:
            raise LLMProviderError(self.name, f"network error: {e}") from e
