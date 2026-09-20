"""LLM router unit tests (Phase 13, plan §4 Addendum §A/§C).

Uses in-process fake providers so we don't hit any real endpoint.
"""
from __future__ import annotations

from typing import AsyncIterator, List

import pytest

from app.services.ai.llm import ChatMessage, LLMResponse
from app.services.ai.llm.base import LLMProvider, LLMProviderError
from app.services.ai.llm.router import LLMRouter


class _FakeProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        *,
        configured: bool = True,
        text: str = "ok",
        raise_on_complete: bool = False,
        chunks: List[str] | None = None,
        raise_on_stream_at: int | None = None,
    ) -> None:
        self.name = name
        self._configured = configured
        self._text = text
        self._raise = raise_on_complete
        self._chunks = chunks or [text]
        self._raise_stream_at = raise_on_stream_at
        self.calls = 0

    def is_configured(self) -> bool:
        return self._configured

    async def complete(self, messages, *, max_tokens, temperature, timeout):
        self.calls += 1
        if self._raise:
            raise LLMProviderError(self.name, "boom")
        return LLMResponse(
            text=self._text, provider=self.name, model=f"{self.name}-model"
        )

    async def stream(
        self, messages, *, max_tokens, temperature, timeout
    ) -> AsyncIterator[str]:
        self.calls += 1
        for i, chunk in enumerate(self._chunks):
            if self._raise_stream_at is not None and i == self._raise_stream_at:
                raise LLMProviderError(self.name, "stream boom")
            yield chunk


def _router_with(providers: dict[str, LLMProvider], chain: List[str]) -> LLMRouter:
    """Build a router whose registry + chain are entirely fake."""

    class _S:
        provider_chain = chain
        llm_max_tokens = 32
        llm_temperature = 0.5
        llm_timeout_seconds = 5.0

    r = LLMRouter.__new__(LLMRouter)
    r._settings = _S()  # type: ignore[attr-defined]
    r._registry = providers  # type: ignore[attr-defined]
    return r


# --------------------------------------------------------------------------- #
# complete()
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_router_falls_back_across_providers():
    a = _FakeProvider("a", raise_on_complete=True)
    b = _FakeProvider("b", text="from-b")
    r = _router_with({"a": a, "b": b}, chain=["a", "b"])

    resp = await r.complete([ChatMessage(role="user", content="hi")])
    assert resp.provider == "b"
    assert resp.text == "from-b"
    assert a.calls == 1
    assert b.calls == 1


@pytest.mark.asyncio
async def test_router_skips_unconfigured_providers():
    a = _FakeProvider("a", configured=False, raise_on_complete=True)
    b = _FakeProvider("b", text="from-b")
    r = _router_with({"a": a, "b": b}, chain=["a", "b"])

    resp = await r.complete([ChatMessage(role="user", content="hi")])
    assert resp.provider == "b"
    assert a.calls == 0  # never invoked because not configured


@pytest.mark.asyncio
async def test_router_raises_when_all_providers_fail():
    a = _FakeProvider("a", raise_on_complete=True)
    b = _FakeProvider("b", raise_on_complete=True)
    r = _router_with({"a": a, "b": b}, chain=["a", "b"])

    with pytest.raises(LLMProviderError):
        await r.complete([ChatMessage(role="user", content="hi")])


@pytest.mark.asyncio
async def test_router_raises_when_chain_is_empty():
    r = _router_with({}, chain=[])
    with pytest.raises(LLMProviderError):
        await r.complete([ChatMessage(role="user", content="hi")])


@pytest.mark.asyncio
async def test_router_preferred_moved_to_front():
    a = _FakeProvider("a", text="from-a")
    b = _FakeProvider("b", text="from-b")
    r = _router_with({"a": a, "b": b}, chain=["a", "b"])

    resp = await r.complete(
        [ChatMessage(role="user", content="hi")], preferred="b"
    )
    assert resp.provider == "b"
    assert a.calls == 0


# --------------------------------------------------------------------------- #
# stream()
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_router_stream_falls_back_when_no_bytes_sent():
    # 'a' fails at chunk 0 (nothing yielded). Router should switch to 'b'.
    a = _FakeProvider("a", chunks=["x"], raise_on_stream_at=0)
    b = _FakeProvider("b", chunks=["hello", " world"])
    r = _router_with({"a": a, "b": b}, chain=["a", "b"])

    got: List[str] = []
    async for chunk in r.stream([ChatMessage(role="user", content="hi")]):
        got.append(chunk)
    assert "".join(got) == "hello world"


@pytest.mark.asyncio
async def test_router_stream_surfaces_error_after_partial_output():
    # 'a' yields one chunk THEN fails at index 1. Because bytes were already
    # sent, the router must NOT fall back — surface the error instead.
    a = _FakeProvider("a", chunks=["partial", "unused"], raise_on_stream_at=1)
    b = _FakeProvider("b", chunks=["fallback"])
    r = _router_with({"a": a, "b": b}, chain=["a", "b"])

    got: List[str] = []
    with pytest.raises(LLMProviderError):
        async for chunk in r.stream([ChatMessage(role="user", content="hi")]):
            got.append(chunk)
    assert got == ["partial"]
    assert b.calls == 0
