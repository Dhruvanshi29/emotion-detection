from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedText
from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Ekman-6 + neutral (plan §13 "signals" language, not diagnosis).
EMOTIONS = ("joy", "sadness", "anger", "fear", "surprise", "disgust", "neutral")

# Where the analyzed text came from — free-form to allow future sources.
EmotionSource = str  # "adhoc" | "chat" | "journal" | ...


class EmotionEvent(Base):
    __tablename__ = "emotion_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source: Mapped[EmotionSource] = mapped_column(String(32), nullable=False)
    source_ref_id: Mapped[Optional[str]] = mapped_column(
        String(36), index=True, nullable=True
    )
    text: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    dominant_emotion: Mapped[str] = mapped_column(String(24), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False)  # positive|neutral|negative
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    signals: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )

    scores: Mapped[List["EmotionScore"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )


class EmotionScore(Base):
    __tablename__ = "emotion_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("emotion_events.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    emotion: Mapped[str] = mapped_column(String(24), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)

    event: Mapped["EmotionEvent"] = relationship(back_populates="scores")
