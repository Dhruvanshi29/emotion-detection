from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, List, Literal, Optional


Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class LLMProviderError(Exception):
    """Raised when a provider fails. Router catches this to fall back."""

    def __init__(self, provider: str, message: str, *, status: Optional[int] = None):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.status = status


class LLMProvider(ABC):
    """Base class for all LLM providers."""

    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """True if this provider has the credentials it needs."""

    @abstractmethod
    async def complete(
        self,
        messages: List[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> LLMResponse:
        """Return a full completion."""

    @abstractmethod
    def stream(
        self,
        messages: List[ChatMessage],
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> AsyncIterator[str]:
        """Yield incremental text deltas."""
