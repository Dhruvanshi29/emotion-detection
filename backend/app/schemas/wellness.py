from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.wellness import EXERCISE_CATEGORIES, GOAL_KINDS

_CATS = set(EXERCISE_CATEGORIES)
_GOALS = set(GOAL_KINDS)


class ExerciseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    title: str
    summary: str
    category: str
    duration_seconds: int
    body: str
    target_emotions: Optional[List[str]] = None
    target_goals: Optional[List[str]] = None
    tags: Optional[List[str]] = None


class ExerciseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    title: str
    summary: str
    category: str
    duration_seconds: int


class Recommendation(BaseModel):
    exercise: ExerciseSummary
    score: float
    reasons: List[str]


class RecommendationList(BaseModel):
    items: List[Recommendation]
    recent_dominant_emotion: Optional[str] = None
    active_goals: List[str] = Field(default_factory=list)


class SessionCreate(BaseModel):
    exercise_slug: str = Field(min_length=1, max_length=64)


class SessionUpdate(BaseModel):
    completed: Optional[bool] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = Field(default=None, max_length=2000)


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exercise_id: str
    exercise_slug: str
    exercise_title: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    rating: Optional[int] = None
    notes: Optional[str] = None


class GoalCreate(BaseModel):
    kind: str

    @field_validator("kind")
    @classmethod
    def _validate(cls, v: str) -> str:
        if v not in _GOALS:
            raise ValueError(f"unknown goal kind: {v}")
        return v


class GoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    is_active: bool
    priority: Optional[float] = None
    created_at: datetime


_ = _CATS  # exercise category set is used by tests
