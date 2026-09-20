from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class VoiceAnalyzeResponse(BaseModel):
    voice_analysis_id: str
    emotion_event_id: Optional[str] = None

    transcript: str
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    word_count: Optional[int] = None
    speech_rate_wpm: Optional[float] = None

    features_available: bool
    energy_rms: Optional[float] = None
    pause_ratio: Optional[float] = None

    stt_provider: Optional[str] = None
    stt_model: Optional[str] = None

    dominant_emotion: Optional[str] = None
    sentiment: Optional[str] = None
    confidence: Optional[float] = None
    scores: Dict[str, float] = Field(default_factory=dict)
    signals: List[str] = Field(default_factory=list)
    emotion_provider: Optional[str] = None
    emotion_model: Optional[str] = None


class VoiceAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    source_ref_id: Optional[str] = None
    transcript: str
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    word_count: Optional[int] = None
    speech_rate_wpm: Optional[float] = None
    features_available: bool
    energy_rms: Optional[float] = None
    pause_ratio: Optional[float] = None
    stt_provider: Optional[str] = None
    stt_model: Optional[str] = None
    emotion_event_id: Optional[str] = None
    created_at: datetime


class STTProvidersStatus(BaseModel):
    chain: List[str]
    available: List[str]
