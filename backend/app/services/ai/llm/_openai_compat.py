"""Shared implementation for OpenAI-compatible chat providers.

NVIDIA NIM, OpenRouter, and Groq all speak the OpenAI Chat Completions
protocol, so they share transport/parsing and only differ in base URL,
model, auth headers, and any provider-specific extra params.

Reasoning models (e.g. Kimi-K3 on NVIDIA) often exceed the non-stream
server-side timeout, so `complete()` always streams internally and
aggregates the deltas.
"""

from __future__ import annotations

import json
from typing import AsyncIterator, Dict, List, Optional

import httpx

from .base import ChatMessage, LLMProvider, LLMProviderError, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        base_url: str,
        model: str,
        extra_headers: Optional[Dict[str, str]] = None,
        extra_body: Optional[Dict[str, object]] = None,
    ):
        self.name = name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._extra_headers = extra_headers or {}
        self._extra_body = {k: v for k, v in (extra_body or {}).items() if v is not None}

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _headers(self, stream: bool) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
        }
        h.update(self._extra_headers)
        return h

    def _payload(
        self,
        messages: List[ChatMessage],
        max_tokens: int,
        temperature: float,
        stream: bool,
    ) -> Dict:
        body: Dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        body.update(self._extra_body)
        return body

    async def complete(
        self,
        messages: List[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> LLMResponse:
        chunks: List[str] = []
        async for delta in self.stream(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        ):
            chunks.append(delta)
        return LLMResponse(
            text="".join(chunks),
            provider=self.name,
            model=self._model,
        )

    async def stream(
        self,
        messages: List[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> AsyncIterator[str]:
        url = f"{self._base_url}/chat/completions"
        payload = self._payload(messages, max_tokens, temperature, stream=True)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", url, headers=self._headers(stream=True), json=payload
                ) as r:
                    if r.status_code >= 400:
                        body = (await r.aread()).decode("utf-8", errors="replace")
                        raise LLMProviderError(
                            self.name,
                            f"HTTP {r.status_code}: {body[:400]}",
                            status=r.status_code,
                        )
                    async for raw in r.aiter_lines():
                        if not raw or not raw.startswith("data:"):
                            continue
                        data = raw[5:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta") or {}
                        except (KeyError, IndexError, ValueError):
                            continue
                        # `reasoning_content` is the model's internal chain-of-thought; not shown to the user.
                        content = delta.get("content")
                        if content:
                            yield content
        except httpx.HTTPError as e:
            raise LLMProviderError(
                self.name, f"network error: {type(e).__name__}: {e or repr(e)}"
            ) from e
