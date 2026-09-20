from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class STTSegment:
    start: float
    end: float
    text: str


@dataclass
class STTResult:
    text: str
    provider: str
    model: str
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    segments: List[STTSegment] = field(default_factory=list)


class STTProviderError(Exception):
    """Raised when a provider fails. Router catches this to fall back."""

    def __init__(self, provider: str, message: str, *, status: Optional[int] = None):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.status = status


class STTProvider(ABC):
    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: Optional[str] = None,
        timeout: float = 60.0,
    ) -> STTResult:
        ...
