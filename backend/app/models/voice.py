from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import EncryptedText
from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VoiceAnalysis(Base):
    """Per-recording voice analysis (plan §9 voice_analysis).

    Raw audio is NEVER stored here (or anywhere) — only the derived signals.
    """

    __tablename__ = "voice_analysis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Free-form: "adhoc" | "journal" | ... plus the id of the linked row when applicable.
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="adhoc")
    source_ref_id: Mapped[Optional[str]] = mapped_column(
        String(36), index=True, nullable=True
    )

    transcript: Mapped[str] = mapped_column(EncryptedText, nullable=False, default="")
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    energy_rms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pause_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speech_rate_wpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    features_available: Mapped[bool] = mapped_column(default=False, nullable=False)

    stt_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    stt_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # Linked emotion_event.id (populated when transcript emotion analysis succeeded).
    emotion_event_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
