"""Dashboard response schemas (plan §10 Dashboard, Phase 10).

The frontend renders "signals" and "patterns" — never diagnoses (plan §13).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    window_days: int
    total_chat_messages: int
    total_conversations: int
    total_journal_entries: int
    total_wellness_sessions: int
    total_emotion_events: int
    total_voice_analyses: int
    total_facial_analyses: int
    active_reminders: int
    active_goals: int
    unread_notifications: int
    dominant_emotion: Optional[str]
    dominant_emotion_percent: float
    sentiment_positive_pct: float
    sentiment_neutral_pct: float
    sentiment_negative_pct: float
    average_journal_mood: Optional[float]
    average_exercise_rating: Optional[float]
    current_streak_days: int
    longest_streak_days: int
    latest_risk_level: Optional[str]
    generated_at: datetime


class EmotionBucket(BaseModel):
    date: date
    counts: Dict[str, int]


class EmotionsBreakdown(BaseModel):
    window_days: int
    by_emotion: Dict[str, int]
    by_source: Dict[str, int]
    by_sentiment: Dict[str, int]
    daily: List[EmotionBucket]
    total: int


class TrendPoint(BaseModel):
    date: date
    mood_score: Optional[float]  # -1..1 weighted average
    events: int
    journal_entries: int
    exercise_sessions: int
    journal_mood_avg: Optional[float]
    exercise_rating_avg: Optional[float]


class DashboardTrends(BaseModel):
    window_days: int
    granularity: str
    points: List[TrendPoint]
    rolling_mood_7d: Optional[float]
    momentum: str  # "up" | "down" | "steady" | "insufficient_data"


class DashboardInsights(BaseModel):
    window_days: int
    highlights: List[str]
    top_emotion: Optional[str]
    top_exercise_category: Optional[str]


__all__ = [
    "DashboardSummary",
    "EmotionBucket",
    "EmotionsBreakdown",
    "TrendPoint",
    "DashboardTrends",
    "DashboardInsights",
]
