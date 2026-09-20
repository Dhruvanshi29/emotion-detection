"""Memory schemas (Phase 11)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.memory import MEMORY_KINDS, MEMORY_SOURCES


class MemoryBase(BaseModel):
    kind: str = "custom"
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=4000)
    source: str = "manual"
    source_ref_id: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    pinned: bool = False

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in MEMORY_KINDS:
            raise ValueError(f"kind must be one of {MEMORY_KINDS}")
        return v

    @field_validator("source")
    @classmethod
    def _src(cls, v: str) -> str:
        if v not in MEMORY_SOURCES:
            raise ValueError(f"source must be one of {MEMORY_SOURCES}")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        cleaned = [t.strip().lower() for t in v if t and t.strip()]
        return cleaned[:16] or None


class MemoryCreate(MemoryBase):
    pass


class MemoryUpdate(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    content: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    tags: Optional[List[str]] = None
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pinned: Optional[bool] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in MEMORY_KINDS:
            raise ValueError(f"kind must be one of {MEMORY_KINDS}")
        return v


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    title: str
    content: str
    source: str
    source_ref_id: Optional[str]
    tags: Optional[List[str]]
    importance: float
    pinned: bool
    is_active: bool
    embedding_model: Optional[str]
    created_at: datetime
    updated_at: datetime


class MemoryList(BaseModel):
    items: List[MemoryRead]
    total: int


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    k: int = Field(default=5, ge=1, le=25)
    kinds: Optional[List[str]] = None


class MemorySearchHit(BaseModel):
    memory: MemoryRead
    score: float
    reasons: List[str]


class MemorySearchResult(BaseModel):
    query: str
    hits: List[MemorySearchHit]


class MemoryExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    source: str = "chat"

    @field_validator("source")
    @classmethod
    def _src(cls, v: str) -> str:
        if v not in MEMORY_SOURCES:
            raise ValueError(f"source must be one of {MEMORY_SOURCES}")
        return v


class MemoryCandidate(BaseModel):
    kind: str
    title: str
    content: str
    confidence: float


class MemoryExtractResult(BaseModel):
    candidates: List[MemoryCandidate]


class ConversationSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    summary: str
    key_points: Optional[List[str]]
    message_count: int
    last_message_id: Optional[str]
    embedding_model: Optional[str]
    provider: Optional[str]
    model: Optional[str]
    created_at: datetime
    updated_at: datetime


class BulkDeleteResult(BaseModel):
    deleted: int


__all__ = [
    "MemoryCreate",
    "MemoryUpdate",
    "MemoryRead",
    "MemoryList",
    "MemorySearchRequest",
    "MemorySearchResult",
    "MemorySearchHit",
    "MemoryExtractRequest",
    "MemoryCandidate",
    "MemoryExtractResult",
    "ConversationSummaryRead",
    "BulkDeleteResult",
]
