from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedJSON, EncryptedText
from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    content: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    # Optional self-reported mood on a 1-5 scale (1=awful, 5=great).
    mood: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tags: Mapped[Optional[Any]] = mapped_column(EncryptedJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )

    analysis: Mapped[Optional["JournalAnalysis"]] = relationship(
        back_populates="entry", uselist=False, cascade="all, delete-orphan"
    )


class JournalAnalysis(Base):
    """Latest AI reflection for a journal entry. Re-analyzing replaces the row."""

    __tablename__ = "journal_analysis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    themes: Mapped[Optional[Any]] = mapped_column(EncryptedJSON, nullable=True)
    reflection_prompt: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    key_feelings: Mapped[Optional[Any]] = mapped_column(EncryptedJSON, nullable=True)
    dominant_emotion: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    sentiment: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )

    entry: Mapped["JournalEntry"] = relationship(back_populates="analysis")
