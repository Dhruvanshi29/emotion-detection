from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class JournalCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    content: str = Field(min_length=1, max_length=20000)
    mood: Optional[int] = Field(default=None, ge=1, le=5)
    tags: Optional[List[str]] = Field(default=None, max_length=20)
    # If true (default), an AI reflection is generated in the background.
    analyze: bool = True


class JournalUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1, max_length=20000)
    mood: Optional[int] = Field(default=None, ge=1, le=5)
    tags: Optional[List[str]] = Field(default=None, max_length=20)


class JournalAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary: str
    themes: Optional[List[str]] = None
    reflection_prompt: str
    key_feelings: Optional[List[str]] = None
    dominant_emotion: Optional[str] = None
    sentiment: Optional[str] = None
    confidence: Optional[float] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    created_at: datetime


class JournalEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: Optional[str] = None
    content: str
    mood: Optional[int] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime
    analysis: Optional[JournalAnalysisRead] = None


class JournalEntryList(BaseModel):
    """Compact list-row without full content (kept for the /journal listing)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: Optional[str] = None
    mood: Optional[int] = None
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime
    has_analysis: bool = False
    preview: str = ""
