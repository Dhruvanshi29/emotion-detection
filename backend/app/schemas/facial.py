from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.emotion import EMOTIONS

_ALLOWED = set(EMOTIONS)
_SENTIMENTS = {"positive", "neutral", "negative"}


class FacialAnalyzeRequest(BaseModel):
    """Client-derived facial signals submitted by the browser after opt-in
    on-device inference. Never accepts raw pixels, frames, embeddings, or
    landmark coordinates."""

    source: str = Field(default="adhoc", max_length=32)
    source_ref_id: Optional[str] = Field(default=None, max_length=36)

    sample_count: int = Field(ge=1, le=10_000)
    duration_seconds: Optional[float] = Field(default=None, ge=0.0, le=3600.0)
    faces_detected_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    scores: Dict[str, float] = Field(default_factory=dict)
    signals: List[str] = Field(default_factory=list, max_length=8)
    model_provider: Optional[str] = Field(default=None, max_length=32)
    model_name: Optional[str] = Field(default=None, max_length=120)

    @field_validator("scores")
    @classmethod
    def _validate_scores(cls, v: Dict[str, float]) -> Dict[str, float]:
        if not v:
            raise ValueError("scores must not be empty")
        unknown = set(v) - _ALLOWED
        if unknown:
            raise ValueError(f"unknown emotion keys: {sorted(unknown)}")
        for k, s in v.items():
            if not (0.0 <= float(s) <= 1.0):
                raise ValueError(f"score for {k} must be in [0,1]")
        return {k: float(v.get(k, 0.0)) for k in EMOTIONS}

    @field_validator("signals")
    @classmethod
    def _validate_signals(cls, v: List[str]) -> List[str]:
        return [s.strip()[:80] for s in v if s and s.strip()]


class FacialAnalyzeResponse(BaseModel):
    facial_analysis_id: str
    emotion_event_id: Optional[str] = None

    sample_count: int
    duration_seconds: Optional[float] = None
    faces_detected_ratio: Optional[float] = None

    dominant_emotion: str
    sentiment: str
    confidence: float
    scores: Dict[str, float]
    signals: List[str]

    model_provider: Optional[str] = None
    model_name: Optional[str] = None


class FacialAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    source_ref_id: Optional[str] = None
    sample_count: int
    duration_seconds: Optional[float] = None
    faces_detected_ratio: Optional[float] = None
    dominant_emotion: str
    sentiment: str
    confidence: float
    scores: Optional[Dict[str, float]] = None
    signals: Optional[List[str]] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    emotion_event_id: Optional[str] = None
    created_at: datetime


def normalize_scores(scores: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, v) for v in scores.values())
    if total <= 0:
        out = {k: 0.0 for k in EMOTIONS}
        out["neutral"] = 1.0
        return out
    return {k: max(0.0, scores.get(k, 0.0)) / total for k in EMOTIONS}


def dominant_and_sentiment(scores: Dict[str, float]) -> tuple[str, str, float]:
    dom = max(scores, key=lambda k: scores[k])
    conf = float(scores[dom])
    if dom in ("joy",):
        sent = "positive"
    elif dom == "neutral":
        sent = "neutral"
    else:
        sent = "negative"
    return dom, sent, conf


_SENTIMENT_ALLOWED = _SENTIMENTS  # keeps _SENTIMENTS referenced for tooling
