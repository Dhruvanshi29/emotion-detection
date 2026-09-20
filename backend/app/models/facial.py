"""Per-session facial analysis (plan §9 facial_analysis).

Only derived, opt-in signals are stored — no raw frames, thumbnails, embeddings
or landmark coordinates. The classifier itself runs client-side (plan §13,
§addendum) so pixels never leave the user's device.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FacialAnalysis(Base):
    __tablename__ = "facial_analysis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="adhoc")
    source_ref_id: Mapped[Optional[str]] = mapped_column(
        String(36), index=True, nullable=True
    )

    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    faces_detected_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    dominant_emotion: Mapped[str] = mapped_column(String(24), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    scores: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    signals: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    model_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    emotion_event_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
