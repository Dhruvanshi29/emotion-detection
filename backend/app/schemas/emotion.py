from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EmotionAnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    source: Literal["adhoc", "chat", "journal"] = "adhoc"
    source_ref_id: Optional[str] = Field(default=None, max_length=64)


class EmotionScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    emotion: str
    score: float


class EmotionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    source_ref_id: Optional[str] = None
    dominant_emotion: str
    sentiment: str
    confidence: float
    signals: Optional[List[str]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    created_at: datetime
    scores: List[EmotionScoreRead] = []


class EmotionAnalyzeResponse(BaseModel):
    event_id: str
    dominant_emotion: str
    sentiment: str
    confidence: float
    scores: Dict[str, float]
    signals: List[str] = []
    provider: Optional[str] = None
    model: Optional[str] = None
